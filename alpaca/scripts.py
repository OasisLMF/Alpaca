from urllib.parse import urlparse
import re


def setup_python_commands(oasislmf_version=None):
    """Generate commands to install Python, pip, AWS CLI, and OasisLMF.

    Args:
        oasislmf_version: Specific version of OasisLMF to install (e.g., '2.0.0').
            If None, installs the latest version.

    Returns:
        list[str]: Shell commands to execute in sequence.
    """
    if oasislmf_version:
        oasislmf_version = f"=={oasislmf_version}"
    else:
        oasislmf_version = ""
    commands = [
        "sudo apt-get update -y",
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip unzip curl",
        "curl \"https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip\" -o \"awscliv2.zip\"",
        "unzip awscliv2.zip",
        "sudo ./aws/install",
        f"sudo pip install oasislmf{oasislmf_version} -qq",
        f"sudo pip install 'oasislmf[extra]{oasislmf_version}' -qq",
    ]
    return commands


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
    """
    folder_name = re.split(r"[/.]", urlparse(github_link).path)[2]
    commands = [
        f"git clone {github_link}",
        f"mv {folder_name}/* ."
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
    """Generate an S3 copy command to attain all run files except for:

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
            "  python -m pip install -r requirements.txt; "
            "elif [ -f requirements.in ]; then "
            "  python -m pip install -r requirements.in; "
            "else "
            "  echo 'No requirements.txt or requirements.in found'; "
            "fi"
        )
    ]
