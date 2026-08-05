# Config: (name, description, default)
AMI_ID = ("AMI_ID", "Amazon Machine ID", "ami-09079da11cd2861fa")
AWS_PROFILE = ("AWS_PROFILE", "Named AWS CLI profile to use for AWS calls and the SSM session tunnel (optional)", "")
AWS_REGION = ("AWS_REGION", "region of EC2 instance to create", "eu-west-1")
DISK_GB = ("DISK_GB", "How many GB your EC2 needs to store your data", "50")
EC2_NAME = ("EC2_NAME", "Name of EC2 Instance", "Alpaca")
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
PATH_TO_DOCKER_COMPOSE = ("PATH_TO_DOCKER_COMPOSE", "Path from base of REPO_LOCATION to docker-compose file (or bash script)",
                          "./docker-compose.yml")
PATH_TO_OASISLMF_JSON = ("PATH_TO_OASISLMF_JSON", "Path from base of REPO_LOCATION to OASISLMF.JSON file", "./oasislmf.json")
PYTEST_ARGS = ("PYTEST_ARGS", "Arguments to pass to PyTest (already uses -vv flag)", "")
REPO_LOCATION = ("REPO_LOCATION", "S3 location (s3://bucket) or link to GitHub repo (https://github.com/name/repo) with data",
                 "https://github.com/OasisLMF/OasisPiWind")
RESULT_DIRECTORY = ("RESULT_DIRECTORY", "Where to store results, s3 (s3://bucket) or local (./path/to/local)", "./runs")
SECURITY_GROUP_ID = ("SECURITY_GROUP_ID", "Security group id of EC2 instance", "MySecurityGroup")
SSH_MAX_RETRIES = ("SSH_MAX_RETRIES", "Maximum number of SSH-over-SSM connection attempts before timeout", "60")
SUBNET_ID = ("SUBNET_ID", "Subnet id of EC2 instance", "MySubnetID")
