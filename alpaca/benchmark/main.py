from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK
from alpaca.benchmark.scripts import (
    LIVE_SOURCE, STORED_SOURCE, build_benchmark_plan, build_benchmark_targets, format_benchmark_plan
)
from alpaca.benchmark.executor import run_benchmark_targets
from alpaca.benchmark.comparison import build_comparison_reports, resolve_relative_tolerance
from alpaca.benchmark.report import build_report_text, run_name, write_report
from alpaca.benchmark.s3_baseline import (
    download_baseline, resolve_stored_versions, upload_baseline, validate_s3_baseline_config
)
from alpaca.benchmark.timing import fastest_result, resolve_model_runtime, sort_results_by_speed
from alpaca.config import load_config
from alpaca.exceptions import OasisAlpacaError
from pathlib import Path

import logging

logger = logging.getLogger(__name__)


def main(config_file):
    """Load and validate a benchmark configuration, run its targets and report on them.

    Every combination of REPO_LOCATIONS and OASISLMF_VERSIONS/OASISLMF_BRANCHES is a target,
    and all of them are peers: there's no designated baseline. Each one runs as an ordinary
    'alpaca model' run (reusing alpaca.model.main.main for its EC2 lifecycle) unless its
    version already has a stored baseline in BENCHMARK_BUCKET, in which case that is
    downloaded instead of paying for the run again. The fastest successful target then
    becomes the reference every other one is timed and diffed against, and a combined report
    (per-target status/runtime, a timing comparison per other target, and the output
    comparison or why it was skipped) is printed and saved alongside the result directories.

    Args:
        config_file: Path to the JSON configuration file for the benchmark run.

    Returns:
        dict: 'results' (one dict per target, in target order, see
            alpaca.benchmark.executor._run_target), 'comparison' (the report from
            build_comparison_reports, or None if comparison was skipped) and 'report_path'
            (where the combined report was written).
    """
    config = load_config(config_file, REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK)
    relative_tolerance = resolve_relative_tolerance(config)
    validate_s3_baseline_config(config)

    targets = build_benchmark_targets(config, resolve_stored_versions(config))
    plan = build_benchmark_plan(config, targets)
    print(format_benchmark_plan(plan))

    results = _resolve_targets(config, targets, plan["execution_mode"])
    if config.get("PUBLISH_BASELINE", False):
        _publish_baselines(config, targets, results)
    comparison_report, skip_reason = _compare_targets(targets, results, relative_tolerance)

    print(build_report_text(results, comparison_report, skip_reason, colour=True))
    report_text = build_report_text(results, comparison_report, skip_reason)
    result_directory = Path(targets[0]["run_config"]["RESULT_DIRECTORY"]).parent
    report_path = write_report(report_text, result_directory)
    logger.info(f"Benchmark report written to {report_path}")

    return {"results": results, "comparison": comparison_report, "report_path": report_path}


def _resolve_targets(config, targets, execution_mode):
    """Produce a result for every target, running the live ones and downloading the stored ones.

    Args:
        config: Validated benchmark configuration dictionary.
        targets: List of targets as returned by build_benchmark_targets.
        execution_mode: 'parallel' or 'sequential', see run_benchmark_targets.

    Returns:
        list[dict]: One result per target, in targets order, so a caller can pair the two up
            by position.
    """
    live_targets = [target for target in targets if target["source"] == LIVE_SOURCE]
    live_results = run_benchmark_targets(live_targets, execution_mode) if live_targets else []

    results = dict(zip((target["label"] for target in live_targets), live_results))
    for target in targets:
        if target["source"] == STORED_SOURCE:
            results[target["label"]] = _download_stored_target(config, target)
    return [results[target["label"]] for target in targets]


def _download_stored_target(config, target):
    """Download a target's stored baseline and describe it like a run that just finished.

    Args:
        config: Validated benchmark configuration dictionary.
        target: The stored target, as returned by build_benchmark_targets.

    Returns:
        dict: A result in run_benchmark_targets' shape, with the version marked as an S3
            baseline and the runtime read from the stored performance metrics (None when the
            baseline was published without any). A failed download is reported as a failed
            target rather than raised, so the targets that did run are still reported on.
    """
    result_directory = target["run_config"]["RESULT_DIRECTORY"]
    result = {
        "label": target["label"],
        "model": target["model"],
        "version": f"{target['version']} (S3 baseline)",
        "status": "success",
        "runtime_seconds": None,
        "total_runtime_seconds": None,
        "step_timings": {},
    }
    try:
        download_baseline(config["BENCHMARK_BUCKET"], target["version"], result_directory, config)
    except Exception:
        logger.exception(f"Downloading the stored baseline for target '{target['label']}' failed")
        return {**result, "status": "failed"}

    runtime_seconds, step_timings = resolve_model_runtime(result_directory, None)
    if runtime_seconds is not None:
        runtime_seconds = round(runtime_seconds)
    return {
        **result,
        "runtime_seconds": runtime_seconds,
        "total_runtime_seconds": runtime_seconds,
        "step_timings": step_timings,
    }


def _compare_targets(targets, results, relative_tolerance):
    """Diff every successful target's output against the fastest one's.

    Args:
        targets: List of targets as returned by build_benchmark_targets.
        results: The matching results, in the same order (see _resolve_targets).
        relative_tolerance: Relative tolerance for numeric CSV cells.

    Returns:
        tuple[dict or None, str]: (comparison_report, skip_reason), with the compared targets
            ordered quickest first to match the report's timing table. Outputs are worth
            diffing even when nothing can be ranked (every target a stored baseline with no
            recorded runtime, say), so the first target stands in as the reference there. The
            report is None when fewer than two targets succeeded, since there's then nothing
            to compare against, or when a target's output couldn't be read; skip_reason is
            only used by the caller in that case. A run's timings are still worth reporting
            when its outputs can't be diffed, so a missing output directory is reported
            rather than raised.
    """
    successful = [(target, result) for target, result in zip(targets, results) if result["status"] == "success"]
    if len(successful) < 2:
        if len(targets) < 2:
            skip_reason = "only one target was configured (add OASISLMF_VERSIONS, OASISLMF_BRANCHES or REPO_LOCATIONS entries)"
        else:
            skip_reason = "fewer than two targets succeeded"
        logger.warning(f"Skipping result comparison: {skip_reason}")
        return None, skip_reason

    reference_result = fastest_result([result for _, result in successful])
    if reference_result is None:
        logger.warning("No target reported a runtime, so the first one is compared against instead of the quickest")
        reference_result = successful[0][1]
    reference = next(pair for pair in successful if pair[1] is reference_result)
    by_speed = {result["label"]: index for index, result in enumerate(sort_results_by_speed([r for _, r in successful]))}
    compared = sorted((pair for pair in successful if pair is not reference), key=lambda pair: by_speed[pair[1]["label"]])

    try:
        report = build_comparison_reports(
            (run_name(reference[1]), reference[0]["run_config"]["RESULT_DIRECTORY"]),
            [(run_name(result), target["run_config"]["RESULT_DIRECTORY"]) for target, result in compared],
            relative_tolerance,
        )
    except OasisAlpacaError as error:
        logger.warning(f"Skipping result comparison: {error}")
        return None, str(error)
    return report, ""


def _publish_baselines(config, targets, results):
    """Publish each successful version target's results as that version's stored baseline.

    Branch targets are skipped: a baseline is stored under an OasisLMF version, and a branch
    has none to store it under.

    Args:
        config: Validated benchmark configuration dictionary.
        targets: List of targets as returned by build_benchmark_targets.
        results: The matching results, in the same order (see _resolve_targets).
    """
    for target, result in zip(targets, results):
        version = target["run_config"].get("OASISLMF_VERSION")
        if not version or result["status"] != "success" or target["source"] == STORED_SOURCE:
            continue
        upload_baseline(
            config["BENCHMARK_BUCKET"], version, target["run_config"]["RESULT_DIRECTORY"], config
        )
