from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK
from alpaca.benchmark.scripts import (
    build_benchmark_plan, build_execution_plan, build_model_run_configs, format_benchmark_plan
)
from alpaca.benchmark.executor import run_benchmark_targets
from alpaca.benchmark.comparison import build_comparison_report, resolve_relative_tolerance
from alpaca.benchmark.report import build_report_text, write_report
from alpaca.benchmark.s3_baseline import validate_s3_baseline_config, download_baseline, upload_baseline
from alpaca.benchmark.timing import resolve_model_runtime
from alpaca.config import load_config
from pathlib import Path

import logging

logger = logging.getLogger(__name__)


def main(config_file):
    """Load and validate a benchmark configuration, run its targets and report on them.

    Reuses alpaca.model.main.main for each target's EC2 lifecycle (upload, run, download,
    terminate) rather than duplicating it. When REPO_LOCATION_COMPARISON is set, both
    baseline and comparison targets run (according to EXECUTION_MODE) and are diffed
    against each other. When it's omitted (single-run mode), only REPO_LOCATION runs, and
    it may optionally be diffed against a stored S3 baseline (see
    _compare_single_run_against_s3_baseline) and/or publish its own results as a new
    stored baseline (see alpaca.benchmark.s3_baseline.upload_baseline). Either way, a
    combined report (per-target status/runtime, a step-by-step timing comparison when two
    results are available, and the output comparison or why it was skipped) is printed
    and saved alongside the targets' result directories.

    Args:
        config_file: Path to the JSON configuration file for the benchmark run.

    Returns:
        dict: 'results' (one dict per target, see alpaca.benchmark.executor._run_target,
            plus a synthetic entry for a downloaded S3 baseline where applicable),
            'comparison' (the report from build_comparison_report, or None if comparison
            was skipped) and 'report_path' (where the combined report was written).
    """
    config = load_config(config_file, REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK)
    plan = build_benchmark_plan(config)
    print(format_benchmark_plan(plan))
    execution_plan = build_execution_plan(config)
    logger.debug(f"Benchmark execution plan: {execution_plan}")
    relative_tolerance = resolve_relative_tolerance(config)
    validate_s3_baseline_config(config)
    run_configs = build_model_run_configs(config)
    results = run_benchmark_targets(run_configs, plan["execution_mode"])

    comparison_report = None
    skip_reason = "at least one target failed"
    if len(run_configs) == 1:
        comparison_report, skip_reason = _compare_single_run_against_s3_baseline(
            config, run_configs[0]["run_config"], results, relative_tolerance
        )
    elif all(result["status"] == "success" for result in results):
        baseline_config, comparison_config = run_configs
        comparison_report = build_comparison_report(
            baseline_config["run_config"]["RESULT_DIRECTORY"],
            comparison_config["run_config"]["RESULT_DIRECTORY"],
            relative_tolerance,
        )
    else:
        logger.warning("Skipping result comparison because at least one target failed")

    report_text = build_report_text(results, comparison_report, skip_reason)
    print(report_text)
    result_directory = Path(run_configs[0]["run_config"]["RESULT_DIRECTORY"]).parent
    report_path = write_report(report_text, result_directory)
    logger.info(f"Benchmark report written to {report_path}")

    return {"results": results, "comparison": comparison_report, "report_path": report_path}


def _compare_single_run_against_s3_baseline(config, target_run_config, results, relative_tolerance):
    """Handle single-run mode's optional S3 baseline compare/publish steps.

    Args:
        config: Validated benchmark configuration dictionary.
        target_run_config: The single target's 'run_config' dict (from
            build_model_run_configs).
        results: The single-entry list from run_benchmark_targets. Mutated in place to
            append a synthetic second entry representing the downloaded S3 baseline (when
            a comparison is performed), so build_report_text renders its timing table and
            summary lines exactly as it would for a live dual-target run.
        relative_tolerance: Relative tolerance for numeric CSV cells.

    Returns:
        tuple[dict or None, str]: (comparison_report, skip_reason). skip_reason is only
            used by the caller when comparison_report is None.
    """
    target_result = results[0]
    if target_result["status"] != "success":
        logger.warning("Skipping S3 baseline comparison because the target failed")
        return None, "the target failed"

    bucket = config.get("BENCHMARK_BUCKET")
    baseline_version = config.get("OASISLMF_VERSION_COMPARISON")

    comparison_report = None
    skip_reason = "no baseline comparison configured (set OASISLMF_VERSION_COMPARISON and BENCHMARK_BUCKET)"
    if baseline_version and bucket:
        s3_baseline_dir = Path(target_run_config["RESULT_DIRECTORY"]).parent / "s3_baseline"
        download_baseline(bucket, baseline_version, s3_baseline_dir, config)
        comparison_report = build_comparison_report(
            target_run_config["RESULT_DIRECTORY"], s3_baseline_dir, relative_tolerance
        )
        baseline_runtime_seconds, baseline_step_timings = resolve_model_runtime(s3_baseline_dir, 0)
        results.append({
            "model": target_result["model"],
            "version": f"{baseline_version} (S3 baseline)",
            "status": "success",
            "runtime_seconds": round(baseline_runtime_seconds),
            "total_runtime_seconds": round(baseline_runtime_seconds),
            "step_timings": baseline_step_timings,
        })

    if str(config.get("PUBLISH_BASELINE", "False")).lower() == "true":
        upload_baseline(bucket, config["OASISLMF_VERSION"], target_run_config["RESULT_DIRECTORY"], config)

    return comparison_report, skip_reason


if __name__ == "__main__":
    main()
