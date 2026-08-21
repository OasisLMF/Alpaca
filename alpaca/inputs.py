# Config: (name, description, default)
AMI_ID = ("AMI_ID", "Amazon Machine ID", "ami-09079da11cd2861fa")
AWS_PROFILE = ("AWS_PROFILE", "Named AWS CLI profile to use for AWS calls and the SSM session tunnel (optional)", "")
AWS_REGION = ("AWS_REGION", "region of EC2 instance to create", "eu-west-1")
BENCHMARK_BUCKET = (
    "BENCHMARK_BUCKET",
    "S3 bucket (s3://bucket-name) storing versioned OasisLMF baseline outputs and performance metrics. In "
    "single-run mode (REPO_LOCATION_COMPARISON omitted), used to fetch OASISLMF_VERSION_COMPARISON's stored "
    "baseline for comparison, and/or as the publish target for PUBLISH_BASELINE",
    ""
)
COMPARISON_TOLERANCE = (
    "COMPARISON_TOLERANCE",
    "Relative tolerance for numeric differences when comparing benchmark run outputs (e.g. 1e-6), "
    "since OasisLMF's Monte Carlo sampling means two runs rarely produce byte-identical loss tables",
    "1e-6"
)
DEBUG = ("DEBUG", "Run using debug mode (must be True to enable)", "False")
DISK_GB = ("DISK_GB", "How many GB your EC2 needs to store your data", "50")
EC2_NAME = ("EC2_NAME", "Name of EC2 Instance", "Alpaca")
EXECUTION_MODE = ("EXECUTION_MODE", "How to run a benchmark's comparison models relative to each other: 'parallel' or 'sequential'",
                  "parallel")
IAM_INSTANCE_PROFILE = (
    "IAM_INSTANCE_PROFILE",
    "Instance profile used to allow S3 access and SSM connectivity (must include SSM Agent permissions, "
    "e.g. AmazonSSMManagedInstanceCore)",
    "ProfileName"
)
INSTANCE_TYPE = ("INSTANCE_TYPE", "Server configuration, amount of resources:", "t3.medium")
LOG_LEVEL = ("LOG_LEVEL", "Verbosity of logging", "INFO")
MAX_LIFETIME_HOURS = ("MAX_LIFETIME_HOURS", "Max lifetime of EC2 instance in hours", "2")
OASISLMF_BRANCH = ("OASISLMF_BRANCH", "Branch of the OasisLMF repo to install from source, used in place of OASISLMF_VERSION", "")
OASISLMF_VERSION = ("OASISLMF_VERSION", "Specific version of OasisLMF to use", "")
OASISLMF_VERSION_COMPARISON = ("OASISLMF_VERSION_COMPARISON", "Specific version of OasisLMF to benchmark against", "")
PATH_TO_DOCKER_COMPOSE = ("PATH_TO_DOCKER_COMPOSE", "Path from base of REPO_LOCATION to docker-compose file (or bash script)",
                          "./docker-compose.yml")
PATH_TO_OASISLMF_JSON = ("PATH_TO_OASISLMF_JSON", "Path from base of REPO_LOCATION to OASISLMF.JSON file", "./oasislmf.json")
PUBLISH_BASELINE = (
    "PUBLISH_BASELINE",
    "When 'True' and BENCHMARK_BUCKET is set, publish this run's OasisLMF output and performance metrics to "
    "BENCHMARK_BUCKET under OASISLMF_VERSION as that version's new stored baseline (single-run mode only, "
    "requires a specific OASISLMF_VERSION rather than 'latest')",
    "False"
)
PYTEST_ARGS = ("PYTEST_ARGS", "Arguments to pass to PyTest (already uses -vv flag)", "")
REPO_LOCATION = ("REPO_LOCATION", "S3 location (s3://bucket) or link to GitHub repo (https://github.com/name/repo) with data",
                 "https://github.com/OasisLMF/OasisPiWind")
REPO_LOCATION_COMPARISON = (
    "REPO_LOCATION_COMPARISON",
    "S3 location (s3://bucket) or link to GitHub repo (https://github.com/name/repo) to benchmark against. "
    "Omit for single-run mode, where only REPO_LOCATION runs and OASISLMF_VERSION_COMPARISON (if set) is "
    "instead fetched from BENCHMARK_BUCKET",
    ""
)
RESULT_DIRECTORY = ("RESULT_DIRECTORY", "Where to store results, s3 (s3://bucket) or local (./path/to/local)", "./runs")
SECURITY_GROUP_ID = ("SECURITY_GROUP_ID", "Security group id of EC2 instance", "MySecurityGroup")
SSH_MAX_RETRIES = ("SSH_MAX_RETRIES", "Maximum number of SSH-over-SSM connection attempts before timeout", "60")
SUBNET_ID = ("SUBNET_ID", "Subnet id of EC2 instance", "MySubnetID")
