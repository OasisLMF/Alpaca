from alpaca.scripts import (
    setup_python_commands,
    download_from_s3_commands,
    download_from_github_commands,
    upload_to_s3_commands,
    download_only_important_command,
    model_requirements_commands
)


def test_setup_python_commands_uses_version():
    """ Test that pip install uses version when given """
    version = "2.3.4"
    commands = setup_python_commands(version)
    oasislmf_version_used = False
    for command in commands:
        if f"pip install oasislmf=={version}" in command:
            oasislmf_version_used = True
            break
    assert oasislmf_version_used


def test_setup_python_commands_no_version():
    """ Test that pip install works fine without version """
    commands = setup_python_commands()
    oasislmf_version_used = False
    for command in commands:
        if "pip install oasislmf " in command:
            oasislmf_version_used = True
            break
    assert oasislmf_version_used


def test_download_from_s3_uses_aws_s3_cp():
    """Test that download from S3 will use aws s3 cp"""
    s3_link = "s3://my-bucket/my-folder"
    acommands = download_from_s3_commands(s3_link)
    uses_aws_s3 = False
    for command in acommands:
        if "aws s3 cp --recursive s3://my-bucket/my-folder /home/ubuntu" == command:
            uses_aws_s3 = True
            break
    assert uses_aws_s3


def test_download_from_github_clones_repo_then_moves():
    """Test that download from github will clone the repository and then moving it"""
    github_link = "https://github.com/OasisLMF/PiWind"
    commands = download_from_github_commands(github_link)

    unused_commands = [f"git clone {github_link}", "mv PiWind/* ."]
    for command in commands:
        if unused_commands[0] in command:
            unused_commands.pop(0)
            if len(unused_commands) == 0:
                break
    assert unused_commands == []


def test_upload_to_s3_creates_bucket_if_needed():
    """Test that upload to S3 will create bucket if it doesn't exist"""
    commands = upload_to_s3_commands("/local/path", "s3://my-bucket/folder")

    creates_bucket = False
    for command in commands:
        if "aws s3 ls s3://my-bucket >/dev/null 2>&1 || aws s3 mb s3://my-bucket" in command:
            creates_bucket = True
            break
    assert creates_bucket


def test_upload_to_s3_checks_bucket_first():
    """Test that upload to S3 will check if bucket exists before attempting to copy"""
    commands = upload_to_s3_commands("/local/path", "s3://test-bucket/path")
    unused_commands = ["aws s3 ls", "aws s3 cp --recursive /local/path s3://test-bucket/path"]
    for command in commands:
        if unused_commands[0] in command:
            unused_commands.pop(0)
            if len(unused_commands) == 0:
                break
    assert unused_commands == []


def test_download_only_important_excludes_fifo():
    """Test that download only important will exclude and include relevant directories"""
    command = download_only_important_command("/from/path", "/to/path")
    assert "aws s3 cp --recursive /from/path /to/path" in command
    assert "--exclude '*/fifo/*'" in command
    assert "--exclude '*/static/*'" in command
    assert "--exclude '*/work/*'" in command
    assert "--exclude '*/input/*'" in command
    assert "--include '*/input/keys.csv'" in command
    assert "--include '*/input/keys-errors.csv'" in command


def test_model_requirements_checks_requirements():
    """Test that model requirements will check for requirements and install them"""
    commands = model_requirements_commands()
    command = commands[0]
    assert "if [ -f requirements.txt ]; then   python -m pip install -r requirements.txt" in command
    assert "if [ -f requirements.in ]; then   python -m pip install -r requirements.in" in command
