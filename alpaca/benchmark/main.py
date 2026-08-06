from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK
from alpaca.benchmark.scripts import (
    build_benchmark_plan, build_execution_plan, build_model_run_configs, format_benchmark_plan
)
from alpaca.benchmark.executor import run_benchmark_targets
from alpaca.benchmark.comparison import build_comparison_report, format_comparison_report
from alpaca.config import load_config

import logging

logger = logging.getLogger(__name__)


def main(config_file):
    """Load and validate a benchmark configuration, run both targets and compare their results.

    Reuses alpaca.model.main.main for each target's EC2 lifecycle (upload, run, download,
    terminate) rather than duplicating it, running the baseline and comparison targets
    according to EXECUTION_MODE. If both targets succeed, their output directories are
    compared and the comparison report is printed; comparison is skipped, with a warning,
    if either target failed.

    Args:
        config_file: Path to the JSON configuration file for the benchmark run.

    Returns:
        dict: 'results' (one dict per target, each with 'model', 'version', 'status' and
            'runtime_seconds') and 'comparison' (the report from build_comparison_report,
            or None if comparison was skipped).
    """
    config = load_config(config_file, REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK)
    plan = build_benchmark_plan(config)
    print(format_benchmark_plan(plan))
    execution_plan = build_execution_plan(config)
    logger.debug(f"Benchmark execution plan: {execution_plan}")
    run_configs = build_model_run_configs(config)
    results = run_benchmark_targets(run_configs, plan["execution_mode"])

    comparison_report = None
    if all(result["status"] == "success" for result in results):
        baseline_config, comparison_config = run_configs
        comparison_report = build_comparison_report(
            baseline_config["run_config"]["RESULT_DIRECTORY"], comparison_config["run_config"]["RESULT_DIRECTORY"]
        )
        print(format_comparison_report(comparison_report))
    else:
        logger.warning("Skipping result comparison because at least one target failed")

    return {"results": results, "comparison": comparison_report}


if __name__ == "__main__":
    main()
