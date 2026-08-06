from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK
from alpaca.benchmark.scripts import (
    build_benchmark_plan, build_execution_plan, build_model_run_configs, format_benchmark_plan
)
from alpaca.benchmark.executor import run_benchmark_targets
from alpaca.config import load_config

import logging

logger = logging.getLogger(__name__)


def main(config_file):
    """Load and validate a benchmark configuration, then run both targets and report results.

    Reuses alpaca.model.main.main for each target's EC2 lifecycle (upload, run, download,
    terminate) rather than duplicating it, running the baseline and comparison targets
    according to EXECUTION_MODE. Result comparison is not implemented yet; this only runs
    both targets and reports each one's status and runtime.

    Args:
        config_file: Path to the JSON configuration file for the benchmark run.

    Returns:
        list[dict]: One result per target, each with 'model', 'version', 'status' and
            'runtime_seconds'.
    """
    config = load_config(config_file, REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK)
    plan = build_benchmark_plan(config)
    print(format_benchmark_plan(plan))
    execution_plan = build_execution_plan(config)
    logger.debug(f"Benchmark execution plan: {execution_plan}")
    run_configs = build_model_run_configs(config)
    return run_benchmark_targets(run_configs, plan["execution_mode"])


if __name__ == "__main__":
    main()
