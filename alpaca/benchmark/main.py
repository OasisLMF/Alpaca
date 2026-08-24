from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK
from alpaca.benchmark.scripts import (
    build_benchmark_plan, build_execution_plan, build_model_run_configs, format_benchmark_plan
)
from alpaca.benchmark.executor import run_benchmark_targets
from alpaca.benchmark.comparison import build_comparison_report, resolve_relative_tolerance
from alpaca.benchmark.report import build_report_text, write_report
from alpaca.config import load_config
from pathlib import Path

import logging

logger = logging.getLogger(__name__)


def main(config_file):
    """Load and validate a benchmark configuration, run both targets and report on them.

    Reuses alpaca.model.main.main for each target's EC2 lifecycle (upload, run, download,
    terminate) rather than duplicating it, running the baseline and comparison targets
    according to EXECUTION_MODE. If both targets succeed, their output directories are
    compared. Either way, a combined report (per-target status/runtime, a step-by-step
    timing comparison when both succeeded, and the output comparison or why it was
    skipped) is printed and saved alongside the targets' result directories.

    Args:
        config_file: Path to the JSON configuration file for the benchmark run.

    Returns:
        dict: 'results' (one dict per target, see alpaca.benchmark.executor._run_target),
            'comparison' (the report from build_comparison_report, or None if comparison
            was skipped) and 'report_path' (where the combined report was written).
    """
    config = load_config(config_file, REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK)
    plan = build_benchmark_plan(config)
    print(format_benchmark_plan(plan))
    execution_plan = build_execution_plan(config)
    logger.debug(f"Benchmark execution plan: {execution_plan}")
    relative_tolerance = resolve_relative_tolerance(config)
    run_configs = build_model_run_configs(config)
    results = run_benchmark_targets(run_configs, plan["execution_mode"])

    comparison_report = None
    if all(result["status"] == "success" for result in results):
        baseline_config, comparison_config = run_configs
        comparison_report = build_comparison_report(
            baseline_config["run_config"]["RESULT_DIRECTORY"],
            comparison_config["run_config"]["RESULT_DIRECTORY"],
            relative_tolerance,
        )
    else:
        logger.warning("Skipping result comparison because at least one target failed")

    report_text = build_report_text(results, comparison_report)
    print(report_text)
    result_directory = Path(run_configs[0]["run_config"]["RESULT_DIRECTORY"]).parent
    report_path = write_report(report_text, result_directory)
    logger.info(f"Benchmark report written to {report_path}")

    return {"results": results, "comparison": comparison_report, "report_path": report_path}


if __name__ == "__main__":
    main()
