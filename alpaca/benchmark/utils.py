from alpaca.exceptions import OasisAlpacaConfigError
from alpaca.inputs import (
    AMI_ID, SECURITY_GROUP_ID, SUBNET_ID, IAM_INSTANCE_PROFILE, REPO_LOCATIONS, PATH_TO_OASISLMF_JSON, AWS_REGION,
    BENCHMARK_BUCKET, COMPARISON_TOLERANCE, OASISLMF_VERSIONS, OASISLMF_BRANCHES, INSTANCE_TYPE, DISK_GB, LOG_LEVEL,
    EC2_NAME, EXECUTION_MODE, MAX_LIFETIME_HOURS, PUBLISH_BASELINE, SSH_MAX_RETRIES, AWS_PROFILE, DEBUG,
    RESULT_DIRECTORY, TESTS
)


REQUIRED_CONFIG_BENCHMARK = [
    AMI_ID, SECURITY_GROUP_ID, SUBNET_ID, IAM_INSTANCE_PROFILE, REPO_LOCATIONS
]
OPTIONAL_CONFIG_BENCHMARK = [
    AWS_REGION, BENCHMARK_BUCKET, COMPARISON_TOLERANCE, OASISLMF_VERSIONS, OASISLMF_BRANCHES, INSTANCE_TYPE,
    DISK_GB, LOG_LEVEL, EC2_NAME, EXECUTION_MODE, MAX_LIFETIME_HOURS, PATH_TO_OASISLMF_JSON, PUBLISH_BASELINE,
    SSH_MAX_RETRIES, AWS_PROFILE, DEBUG, RESULT_DIRECTORY, TESTS
]


def validate_tests_config(config):
    """Validate PATH_TO_OASISLMF_JSON/TESTS combinations before any EC2 spend.

    Every target needs exactly one oasislmf.json to run: either the one PATH_TO_OASISLMF_JSON
    names, or tests/<name>/oasislmf.json for each TESTS entry (see
    alpaca.benchmark.scripts.oasislmf_json_path). Setting both would leave it unclear which one
    a target runs, so that's rejected rather than one quietly winning.

    Args:
        config: Validated benchmark configuration dictionary.

    Raises:
        OasisAlpacaConfigError: If neither PATH_TO_OASISLMF_JSON nor TESTS is set, if both
            are, or if a TESTS entry isn't a single directory name.
    """
    tests = config.get("TESTS") or []
    if tests and config.get("PATH_TO_OASISLMF_JSON"):
        raise OasisAlpacaConfigError("Set either PATH_TO_OASISLMF_JSON or TESTS, not both")
    if not tests and not config.get("PATH_TO_OASISLMF_JSON"):
        raise OasisAlpacaConfigError("PATH_TO_OASISLMF_JSON or TESTS is required")
    for test in tests:
        if "/" in test or test in (".", ".."):
            raise OasisAlpacaConfigError(
                f"Every TESTS entry must be a directory name under tests/ (e.g. 'test_1'), got '{test}'"
            )
