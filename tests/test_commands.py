from alpaca.commands import (
    setup_python_commands,
    oasislmf_install_commands,
    download_from_s3_commands,
    download_from_github_commands,
    upload_to_s3_commands,
    download_only_important_command,
    model_requirements_commands
)
from alpaca.exceptions import OasisAlpacaConfigError

import pytest


def test_setup_python_commands_uses_version():
    """Test that pip install uses version when given."""
    version = "2.3.4"
    commands = setup_python_commands(version)
    oasislmf_version_used = False
    for command in commands:
        if f"pip install oasislmf=={version}" in command:
            oasislmf_version_used = True
            break
    assert oasislmf_version_used


def test_setup_python_commands_no_version():
    """Test that pip install works fine without version."""
    commands = setup_python_commands()
    oasislmf_version_used = False
    for command in commands:
        if "pip install oasislmf " in command:
            oasislmf_version_used = True
            break
    assert oasislmf_version_used


def test_setup_python_commands_ends_with_oasislmf_install():
    """Test that the OasisLMF install is appended after the Python and AWS CLI setup."""
    commands = setup_python_commands("2.3.4", "develop")
    install_commands = oasislmf_install_commands("2.3.4", "develop")
    assert commands[-len(install_commands):] == install_commands
    assert "sudo apt-get update -y" == commands[0]


def test_oasislmf_install_commands_uses_branch():
    """Test that a branch is cloned and installed from source, with the tooling to build it."""
    commands = oasislmf_install_commands(oasislmf_branch="develop")
    assert commands == [
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential python3-dev",
        "sudo pip install --upgrade pip setuptools wheel -qq",
        "git clone --depth 1 --branch develop https://github.com/OasisLMF/OasisLMF.git /tmp/oasislmf",
        "sudo pip install '/tmp/oasislmf[extra]'",
        "oasislmf version"
    ]


def test_oasislmf_install_commands_branch_keeps_build_output():
    """Test that the source build is not quietened, as -qq hides why a build failed."""
    commands = oasislmf_install_commands(oasislmf_branch="develop")
    assert "sudo pip install '/tmp/oasislmf[extra]'" in commands
    assert not any("[extra]" in command and "-qq" in command for command in commands)


def test_oasislmf_install_commands_verify_install():
    """Test that every install path ends by checking oasislmf is actually runnable."""
    for kwargs in [{"oasislmf_branch": "develop"}, {"oasislmf_version": "2.3.4"}, {}]:
        assert oasislmf_install_commands(**kwargs)[-1] == "oasislmf version"


def test_oasislmf_install_commands_branch_takes_priority_over_version():
    """Test that a branch wins when both a branch and a version are given."""
    commands = oasislmf_install_commands("2.3.4", "feature/thing")
    joined = " ".join(commands)
    assert "--branch feature/thing https://github.com/OasisLMF/OasisLMF.git" in joined
    assert "2.3.4" not in joined


def test_oasislmf_install_commands_uses_version():
    """Test that a version pins both the plain and the extra install."""
    commands = oasislmf_install_commands("2.3.4")
    assert commands == [
        "sudo pip install oasislmf==2.3.4 -qq",
        "sudo pip install 'oasislmf[extra]==2.3.4' -qq",
        "oasislmf version"
    ]


def test_oasislmf_install_commands_latest():
    """Test that no branch and no version installs the latest release."""
    commands = oasislmf_install_commands()
    assert commands == [
        "sudo pip install oasislmf -qq",
        "sudo pip install 'oasislmf[extra]' -qq",
        "oasislmf version"
    ]
    assert not any("git" in command for command in commands)


def test_download_from_s3_uses_aws_s3_cp():
    """Test that download from S3 will use aws s3 cp."""
    s3_link = "s3://my-bucket/my-folder"
    acommands = download_from_s3_commands(s3_link)
    uses_aws_s3 = False
    for command in acommands:
        if "aws s3 cp --recursive s3://my-bucket/my-folder /home/ubuntu" == command:
            uses_aws_s3 = True
            break
    assert uses_aws_s3


def test_download_from_github_clones_repo_then_moves():
    """Test that download from github will clone the repository and then moving it."""
    github_link = "https://github.com/OasisLMF/PiWind"
    commands = download_from_github_commands(github_link)

    unused_commands = [f"git clone {github_link}", "find PiWind -mindepth 1 -maxdepth 1 -exec mv -t . {} +"]
    for command in commands:
        if unused_commands[0] in command:
            unused_commands.pop(0)
            if len(unused_commands) == 0:
                break
    assert unused_commands == []


def test_download_from_github_reads_the_repo_name_from_any_link_form():
    """A '.git' suffix, a trailing slash and an SSH-style link all name the same folder."""
    for link in ["https://github.com/OasisLMF/PiWind", "https://github.com/OasisLMF/PiWind.git",
                 "https://github.com/OasisLMF/PiWind/", "git@github.com:OasisLMF/PiWind.git"]:
        assert "find PiWind " in download_from_github_commands(link)[1]


def test_download_from_github_raises_without_a_repo_name():
    """A link with no repository would otherwise fail on an index that isn't there."""
    with pytest.raises(OasisAlpacaConfigError):
        download_from_github_commands("https://github.com/OasisLMF")


def test_upload_to_s3_creates_bucket_if_needed():
    """Test that upload to S3 will create bucket if it doesn't exist."""
    commands = upload_to_s3_commands("/local/path", "s3://my-bucket/folder")

    creates_bucket = False
    for command in commands:
        if "aws s3 ls s3://my-bucket >/dev/null 2>&1 || aws s3 mb s3://my-bucket" in command:
            creates_bucket = True
            break
    assert creates_bucket


def test_upload_to_s3_checks_bucket_first():
    """Test that upload to S3 will check if bucket exists before attempting to copy."""
    commands = upload_to_s3_commands("/local/path", "s3://test-bucket/path")
    unused_commands = ["aws s3 ls", "aws s3 cp --recursive /local/path s3://test-bucket/path"]
    for command in commands:
        if unused_commands[0] in command:
            unused_commands.pop(0)
            if len(unused_commands) == 0:
                break
    assert unused_commands == []


def test_download_only_important_excludes_fifo():
    """Test that download only important will exclude and include relevant directories."""
    command = download_only_important_command("/from/path", "/to/path")
    assert "aws s3 cp --recursive /from/path /to/path" in command
    assert "--exclude '*/fifo/*'" in command
    assert "--exclude '*/static/*'" in command
    assert "--exclude '*/work/*'" in command
    assert "--exclude '*/input/*'" in command
    assert "--include '*/input/keys.csv'" in command
    assert "--include '*/input/keys-errors.csv'" in command


def test_model_requirements_checks_requirements():
    """Test that model requirements will check for requirements and install them."""
    commands = model_requirements_commands()
    command = commands[0]
    assert "if [ -f requirements.txt ]; then   sudo python3 -m pip install -r requirements.txt" in command
    assert "if [ -f requirements.in ]; then   sudo python3 -m pip install -r requirements.in" in command
    assert "python -m pip" not in command
