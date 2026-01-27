from urllib.parse import urlparse
import re


def setup_python_commands(oasislmf_version=None):
    """Bash commands used to set up pip and oasislmf

    Args:
        oasislmf_version (string, None): specific version of oasislmf to install

    Returns: List[string]
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
    commands = [
        f"aws s3 cp --recursive {s3_link} /home/ubuntu"
    ]
    return commands


def download_from_github_commands(github_link):
    folder_name = re.split(r"[/.]", urlparse(github_link).path)[2]
    commands = [
        f"git clone {github_link}",
        f"mv {folder_name}/* ."
    ]
    return commands


def upload_to_s3_commands(remote_link, s3_link):
    bucket = s3_link.replace("s3://", "").split("/", 1)[0]

    commands = [
        f"aws s3 ls s3://{bucket} >/dev/null 2>&1 || aws s3 mb s3://{bucket}",
        download_only_important_command(remote_link, s3_link)
    ]
    return commands


def download_only_important_command(loc_from, loc_to):
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
    """
    Return shell commands that install model requirements if present.
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
