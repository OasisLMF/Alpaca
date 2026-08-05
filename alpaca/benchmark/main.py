from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK
from alpaca.benchmark.scripts import build_benchmark_plan, format_benchmark_plan
from alpaca.config import load_config

import logging

logger = logging.getLogger(__name__)


def main(config_file):
    """Load, validate and print the plan for a benchmark configuration.

    Model execution for benchmark runs (spinning up REPO_LOCATION and REPO_LOCATION_COMPARISON
    on separate instances and comparing results) is not implemented yet. This only parses,
    validates and prints the plan Alpaca would run.

    Args:
        config_file: Path to the JSON configuration file for the benchmark run.

    Returns:
        dict: The loaded and validated benchmark configuration.
    """
    config = load_config(config_file, REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK)
    plan = build_benchmark_plan(config)
    print(format_benchmark_plan(plan))
    return config


if __name__ == "__main__":
    main()
