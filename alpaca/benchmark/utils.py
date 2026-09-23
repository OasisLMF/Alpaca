from alpaca.exceptions import OasisAlpacaConfigError
from alpaca.inputs import (
    AMI_ID, SECURITY_GROUP_ID, SUBNET_ID, IAM_INSTANCE_PROFILE, REPO_LOCATIONS, PATH_TO_OASISLMF_JSON, AWS_REGION,
    BENCHMARK_BUCKET, COMPARISON_TOLERANCE, OASISLMF_VERSIONS, OASISLMF_BRANCHES, INSTANCE_TYPE, DISK_GB, LOG_LEVEL,
    EC2_NAME, EXECUTION_MODE, MAX_LIFETIME_HOURS, PUBLISH_BASELINE, RUN_TEST_SUITE, SSH_MAX_RETRIES, AWS_PROFILE,
    DEBUG, RESULT_DIRECTORY
)


REQUIRED_CONFIG_BENCHMARK = [
    AMI_ID, SECURITY_GROUP_ID, SUBNET_ID, IAM_INSTANCE_PROFILE, REPO_LOCATIONS
]
OPTIONAL_CONFIG_BENCHMARK = [
    AWS_REGION, BENCHMARK_BUCKET, COMPARISON_TOLERANCE, OASISLMF_VERSIONS, OASISLMF_BRANCHES, INSTANCE_TYPE,
    DISK_GB, LOG_LEVEL, EC2_NAME, EXECUTION_MODE, MAX_LIFETIME_HOURS, PATH_TO_OASISLMF_JSON, PUBLISH_BASELINE,
    RUN_TEST_SUITE, SSH_MAX_RETRIES, AWS_PROFILE, DEBUG, RESULT_DIRECTORY
]


def validate_test_suite_config(config):
    """Validate PATH_TO_OASISLMF_JSON/RUN_TEST_SUITE combinations before any EC2 spend.

    PATH_TO_OASISLMF_JSON is required for an ordinary model-run target, but a RUN_TEST_SUITE
    target discovers its own tests/*/oasislmf.json configs instead (via pytest, on whatever
    test harness the target's own repository provides) and never reads it.

    Args:
        config: Validated benchmark configuration dictionary.

    Raises:
        OasisAlpacaConfigError: If RUN_TEST_SUITE is not set and PATH_TO_OASISLMF_JSON is
            missing, since an ordinary target would then have no model config to run.
    """
    if config.get("RUN_TEST_SUITE", False):
        return
    if not config.get("PATH_TO_OASISLMF_JSON"):
        raise OasisAlpacaConfigError("PATH_TO_OASISLMF_JSON is required unless RUN_TEST_SUITE is set")
