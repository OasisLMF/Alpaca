from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK
from alpaca.config import load_config

import logging

logger = logging.getLogger(__name__)


def main(config_file):
    """Load and validate a benchmark configuration file.

    Model execution for benchmark runs (spinning up REPO_LOCATION and REPO_LOCATION_COMPARISON
    on separate instances and comparing results) is not implemented yet. This only parses and
    validates the config so that 'alpaca benchmark <config.json>' can be wired up ahead of that.

    Args:
        config_file: Path to the JSON configuration file for the benchmark run.

    Returns:
        dict: The loaded and validated benchmark configuration.
    """
    config = load_config(config_file, REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK)
    logger.info(f"Benchmark config {config_file} is valid")
    return config


if __name__ == "__main__":
    main()
