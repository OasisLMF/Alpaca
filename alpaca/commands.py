from alpaca.exceptions import OasisAlpacaConfigError
from urllib.parse import urlparse
import re


OASISLMF_REPO = "https://github.com/OasisLMF/OasisLMF.git"
OASISLMF_CLONE_DIR = "/tmp/oasislmf"


def setup_python_commands(oasislmf_version=None, oasislmf_branch=None):
    """Generate commands to install Python, pip, AWS CLI, and OasisLMF.

    Args:
        oasislmf_version: Specific released version of OasisLMF to install (e.g., '2.0.0').
            Ignored when oasislmf_branch is given.
        oasislmf_branch: Branch of the OasisLMF repository to install from source.

    Returns:
        list[str]: Shell commands to execute in sequence.
    """
    commands = [
        "sudo apt-get update -y",
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip unzip curl",
        "curl \"https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip\" -o \"awscliv2.zip\"",
        "unzip awscliv2.zip",
        "sudo ./aws/install",
    ]
    commands.extend(oasislmf_install_commands(oasislmf_version, oasislmf_branch))
    return commands


def oasislmf_install_commands(oasislmf_version=None, oasislmf_branch=None):
    """Generate commands to install OasisLMF from a branch, a released version or latest.

    A branch takes priority over a version, and if neither is given the latest release on
    PyPI is installed.

    Args:
        oasislmf_version: Specific released version of OasisLMF to install (e.g., '2.0.0').
            Ignored when oasislmf_branch is given. If both are None, installs the latest.
        oasislmf_branch: Branch of the OasisLMF repository to install from source.

    Returns:
        list[str]: Shell commands to execute in sequence.
    """
    if oasislmf_branch:
        return [
            "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential python3-dev",
            "sudo pip install --upgrade pip setuptools wheel -qq",
            f"git clone --depth 1 --branch {oasislmf_branch} {OASISLMF_REPO} {OASISLMF_CLONE_DIR}",
            f"sudo pip install '{OASISLMF_CLONE_DIR}[extra]'",
            "oasislmf version",  # <- ensures errors on faulty download
        ]

    version = f"=={oasislmf_version}" if oasislmf_version else ""
    return [
        f"sudo pip install oasislmf{version} -qq",
        f"sudo pip install 'oasislmf[extra]{version}' -qq",
        "oasislmf version",
    ]


def download_from_s3_commands(s3_link):
    """Generate commands to download a model from an S3 bucket.
    Requires the EC2 instance to have an IAM role with S3 read permissions.

    Args:
        s3_link: S3 URI of the model (e.g., 's3://bucket-name/path/to/model').

    Returns:
        list[str]: Shell commands to execute.
    """
    commands = [
        f"aws s3 cp --recursive {s3_link} /home/ubuntu"
    ]
    return commands


def download_from_github_commands(github_link):
    """Generate commands to clone a model repository from GitHub.

    Clones the repository and moves its contents to the current directory.
    Only works with public repositories (no authentication).

    Args:
        github_link: GitHub repository URL (e.g., 'https://github.com/org/repo').

    Returns:
        list[str]: Shell commands to execute.

    Raises:
        OasisAlpacaConfigError: If no repository name can be read from the link.
    """
    segments = [segment for segment in urlparse(github_link).path.split("/") if segment]
    if len(segments) < 2:
        raise OasisAlpacaConfigError(f"Could not read a repository name from REPO_LOCATION '{github_link}'")
    folder_name = re.sub(r"\.git$", "", segments[-1])
    commands = [
        f"git clone {github_link}",
        f"find {folder_name} -mindepth 1 -maxdepth 1 -exec mv -t . {{}} +"
    ]
    return commands


def upload_to_s3_commands(remote_link, s3_link):
    """Generate commands to upload model results to an S3 bucket, creating it if it doesn't exist.
    Requires IAM_INSTANCE_PROFILE config with a suitable role.

    Args:
        remote_link: Path on the EC2 instance containing results (e.g., '/home/ubuntu/runs').
        s3_link: Destination S3 URI (e.g., 's3://bucket-name/results').

    Returns:
        list[str]: Shell commands to execute.
    """
    bucket = s3_link.replace("s3://", "").split("/", 1)[0]

    commands = [
        f"aws s3 ls s3://{bucket} >/dev/null 2>&1 || aws s3 mb s3://{bucket}",  # noqa: E231
        download_only_important_command(remote_link, s3_link)
    ]
    return commands


def download_only_important_command(loc_from, loc_to):
    """Generate an S3 copy command to attain run files.

    Excluded directories:
        - */fifo/*
        - */static/*
        - */work/*
        - */input/*

    Included despite exclusions:
        - */input/keys.csv
        - */input/keys-errors.csv

    Args:
        loc_from: Source path (local or S3 URI).
        loc_to: Destination path (local or S3 URI).

    Returns:
        str: A single AWS CLI command string.
    """
    command = (
        "aws s3 cp --recursive "
        f"{loc_from} {loc_to} "
        "--exclude '*/fifo/*' "
        "--exclude '*/static/*' "
        "--exclude '*/work/*' "
        "--exclude '*/input/*' "
        "--include '*/input/keys.csv' "
        "--include '*/input/keys-errors.csv'"
    )
    return command


def model_requirements_commands():
    """Generate commands to install model-specific Python dependencies.

    Returns:
        list[str]: Shell commands to execute. The command is a conditional
            that checks for requirements files and installs if present.
    """
    return [
        (
            "if [ -f requirements.txt ]; then "
            "  sudo python3 -m pip install -r requirements.txt; "
            "elif [ -f requirements.in ]; then "
            "  sudo python3 -m pip install -r requirements.in; "
            "else "
            "  echo 'No requirements.txt or requirements.in found'; "
            "fi"
        )
    ]
