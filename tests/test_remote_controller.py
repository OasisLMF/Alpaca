from alpaca.model.utils import OPTIONAL_CONFIG_MODEL
from alpaca.remote_controller import RemoteController
from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from alpaca.commands import (
    setup_python_commands, download_from_github_commands, download_from_s3_commands, model_requirements_commands,
    upload_to_s3_commands
)

from unittest import mock
from pathlib import Path

import pytest
import json
import logging


CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)


@mock.patch.object(RemoteController, "setup_instance")
@mock.patch.object(RemoteController, "shutdown")
def test_context_manager_calls_setup_and_shutdown(mock_shutdown, mock_setup):
    with RemoteController(CONFIG_PATH, {}) as rc:
        assert rc.ec2 is None
        assert rc.ssh is None
        assert rc.instance_id is None
        assert rc.public_ip is None

    mock_setup.assert_called_once()
    mock_shutdown.assert_called_once()


@mock.patch.object(RemoteController, "setup_instance")
@mock.patch.object(RemoteController, "shutdown")
def test_context_manager_checks_config(mock_shutdown, mock_setup):
    with pytest.raises(OasisAlpacaConfigError):
        with RemoteController(CONFIG_PATH, [("missing_config", "", "")]):
            pass
    with pytest.raises(FileNotFoundError):
        with RemoteController("fake/config/path"):
            pass
    # And then make sure it doesn't raise with some correct one
    with RemoteController(CONFIG_PATH, [("croissant", "", ""), ("Al", "", "")]):
        pass


def test_setup_instance_success():
    controller = RemoteController(CONFIG_PATH, [])
    controller.session = mock.Mock()

    controller._create_instance = mock.Mock(return_value="instancey mcinstanceface")
    controller._wait_for_instance = mock.Mock(return_value="2.3.5.7")
    controller._wait_for_ssm_registration = mock.Mock()
    controller._wait_for_ssh = mock.Mock(return_value=mock.Mock())
    controller.run_commands = mock.Mock()
    controller.shutdown = mock.Mock()

    mock_ec2 = controller.session.client.return_value

    controller.setup_instance()

    controller.session.client.assert_called_once_with("ec2")

    controller._create_instance.assert_called_once()
    controller._wait_for_instance.assert_called_once()
    controller._wait_for_ssm_registration.assert_called_once()
    controller._wait_for_ssh.assert_called_once()

    controller.run_commands.assert_called_once_with(
        setup_python_commands(CONFIG["OASISLMF_VERSION"], None), check=True
    )

    controller.shutdown.assert_not_called()

    assert controller.ec2 is mock_ec2
    assert controller.instance_id == "instancey mcinstanceface"
    assert controller.public_ip == "2.3.5.7"


def test_setup_instance_passes_branch_to_install():
    """Test that OASISLMF_BRANCH reaches the install commands run on the instance."""
    controller = RemoteController(CONFIG_PATH, [])
    controller.session = mock.Mock()
    controller.config["OASISLMF_BRANCH"] = "develop"

    controller._create_instance = mock.Mock(return_value="instance id")
    controller._wait_for_instance = mock.Mock(return_value="2.3.5.7")
    controller._wait_for_ssm_registration = mock.Mock()
    controller._wait_for_ssh = mock.Mock(return_value=mock.Mock())
    controller.run_commands = mock.Mock()

    controller.setup_instance()

    controller.run_commands.assert_called_once_with(
        setup_python_commands(CONFIG["OASISLMF_VERSION"], "develop"), check=True
    )
    assert any("--branch develop" in command for command in controller.run_commands.call_args[0][0])


def test_setup_instance_failure():
    controller = RemoteController(CONFIG_PATH, [])
    controller.session = mock.Mock()
    controller.session.client = mock.Mock(side_effect=ValueError())
    controller.shutdown = mock.Mock()
    with pytest.raises(OasisAlpacaError):
        controller.setup_instance()
    controller.shutdown.assert_called_once()


def test_shutdown_early():
    controller = RemoteController(CONFIG_PATH, [])
    controller.ec2 = mock.Mock()
    controller.shutdown()
    controller.ec2.terminate_instances.assert_not_called()


def test_shutdown():
    controller = RemoteController(CONFIG_PATH, [])
    controller.instance_id = "id"
    controller.ec2 = mock.Mock()
    waiter = mock.Mock()
    controller.ec2.get_waiter.return_value = waiter
    controller.ssh = mock.Mock()

    controller.shutdown()

    controller.ec2.terminate_instances.assert_called_once_with(InstanceIds=[controller.instance_id])
    controller.ec2.get_waiter.assert_called_once_with("instance_terminated")
    waiter.wait.assert_called_once_with(InstanceIds=[controller.instance_id])
    controller.ssh.close.assert_called_once_with()


def test_run_commands():
    commands = ["command 1", "command b", "command iii"]
    controller = RemoteController(CONFIG_PATH)
    controller.ssh = mock.Mock()
    controller.ssh.exec_command.return_value = (1, 2, 3)
    controller._ssh_logs_unimportant = mock.Mock()
    controller.run_commands(commands)

    commands_taken = [call[0][0] for call in controller.ssh.exec_command.call_args_list]
    assert commands == commands_taken
    assert controller.ssh.exec_command.call_count == 3
    assert controller._ssh_logs_unimportant.call_count == 3


def test_run_commands_check_raises_on_failure():
    """Test that check stops at the first failing command and reports its output."""
    controller = RemoteController(CONFIG_PATH)
    controller.ssh = mock.Mock()
    stdout = mock.Mock()
    stdout.channel.recv_exit_status.return_value = 1
    controller.ssh.exec_command.return_value = (mock.Mock(), stdout, mock.Mock())
    controller._ssh_logs_unimportant = mock.Mock(return_value="ERROR: No matching distribution found")

    with pytest.raises(OasisAlpacaError) as excinfo:
        controller.run_commands(["failing command", "never reached"], check=True)

    assert "failing command" in str(excinfo.value)
    assert "No matching distribution found" in str(excinfo.value)
    assert controller.ssh.exec_command.call_count == 1


def test_run_commands_check_passes_on_success():
    """Test that check runs every command when they all exit zero."""
    controller = RemoteController(CONFIG_PATH)
    controller.ssh = mock.Mock()
    stdout = mock.Mock()
    stdout.channel.recv_exit_status.return_value = 0
    controller.ssh.exec_command.return_value = (mock.Mock(), stdout, mock.Mock())
    controller._ssh_logs_unimportant = mock.Mock(return_value="")

    controller.run_commands(["command 1", "command 2"], check=True)

    assert controller.ssh.exec_command.call_count == 2


def test_run_commands_without_check_ignores_failure():
    """Test that a failing command is only logged when check is not set."""
    controller = RemoteController(CONFIG_PATH)
    controller.ssh = mock.Mock()
    stdout = mock.Mock()
    stdout.channel.recv_exit_status.return_value = 1
    controller.ssh.exec_command.return_value = (mock.Mock(), stdout, mock.Mock())
    controller._ssh_logs_unimportant = mock.Mock(return_value="")

    controller.run_commands(["failing command", "still runs"])

    assert controller.ssh.exec_command.call_count == 2
    stdout.channel.recv_exit_status.assert_not_called()


def test_run_commands_condition():
    def condition(cmd):
        if "important" in cmd:
            return True
        return False

    commands = ["command", "other command", "important command 1", "another one", "important command doua"]
    controller = RemoteController(CONFIG_PATH)
    controller.ssh = mock.Mock()
    controller._ssh_logs_unimportant = mock.Mock()
    controller._ssh_logs_important = mock.Mock()
    controller.ssh.exec_command.return_value = (1, 2, 3)
    controller.run_commands(commands, condition)
    assert controller._ssh_logs_unimportant.call_count == 3
    assert controller._ssh_logs_important.call_count == 2


def _debug_controller(responses):
    """Build a controller in debug mode whose prompt answers the given responses in order."""
    controller = RemoteController(CONFIG_PATH)
    controller.debug = True
    controller.ssh = mock.Mock()
    controller.ssh.exec_command.return_value = (1, 2, 3)
    controller._ssh_logs_important = mock.Mock()
    controller.shutdown = mock.Mock()
    return controller, mock.patch("builtins.input", side_effect=responses)


@pytest.mark.parametrize("response", ["", "x", "X"])
def test_run_commands_debug_executes(response):
    """Test that the debug prompt runs each command as it stands and streams its output."""
    commands = ["command 1", "command 2"]
    controller, prompt = _debug_controller([response] * len(commands))

    with prompt:
        controller.run_commands(commands)

    commands_taken = [call[0][0] for call in controller.ssh.exec_command.call_args_list]
    assert commands_taken == commands
    assert controller._ssh_logs_important.call_count == 2


def test_run_commands_debug_skips():
    """Test that s skips the command and moves on to the next one."""
    controller, prompt = _debug_controller(["s", ""])

    with prompt:
        controller.run_commands(["skipped command", "run command"])

    commands_taken = [call[0][0] for call in controller.ssh.exec_command.call_args_list]
    assert commands_taken == ["run command"]


def test_run_commands_debug_runs_own_command_first():
    """Test that any other response runs as a command, then the original is offered again."""
    controller, prompt = _debug_controller(["ls -l", ""])

    with prompt:
        controller.run_commands(["original command"])

    calls = controller.ssh.exec_command.call_args_list
    assert [call[0][0] for call in calls] == ["ls -l", "original command"]
    # A command of the user's own may expect a terminal, the ones Alpaca runs here do not.
    assert calls[0][1] == {"get_pty": True}
    assert calls[1][1] == {}


def test_run_commands_debug_terminates():
    """Test that t shuts the instance down and stops the run before any later command."""
    controller, prompt = _debug_controller(["t"])

    with prompt:
        with pytest.raises(OasisAlpacaError):
            controller.run_commands(["command 1", "command 2"])

    controller.shutdown.assert_called_once()
    controller.ssh.exec_command.assert_not_called()


def test_debug_defaults_to_off():
    """Test that a config without DEBUG runs normally rather than failing to build."""
    controller = RemoteController(CONFIG_PATH)
    assert controller.debug is False
    assert "DEBUG" not in CONFIG


@pytest.mark.parametrize("value,expected", [("True", True), ("true", True), (True, True), ("False", False), ("no", False)])
def test_debug_config_values(tmp_path, value, expected):
    """Test that DEBUG is read as True from a string or a JSON boolean, and is off otherwise."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({**CONFIG, "DEBUG": value}))

    assert RemoteController(config_path, [], OPTIONAL_CONFIG_MODEL).debug is expected


def test_shutdown_only_terminates_once():
    """Test that shutting down twice, as a forced shutdown does, terminates only once."""
    controller = RemoteController(CONFIG_PATH)
    controller.instance_id = "id"
    controller.ec2 = mock.Mock()
    controller.ec2.get_waiter.return_value = mock.Mock()
    controller.ssh = mock.Mock()

    controller.shutdown()
    controller.shutdown()

    controller.ec2.terminate_instances.assert_called_once_with(InstanceIds=["id"])


def test_upload_model_github():
    repo_location = "http://github.com/place/repo"
    controller = RemoteController(CONFIG_PATH)
    controller.run_commands = mock.Mock()
    controller.upload_model(repo_location)
    commands_taken = [call[0][0] for call in controller.run_commands.call_args_list]
    assert len(commands_taken) == 2
    assert commands_taken[0] == download_from_github_commands(repo_location)
    assert commands_taken[1] == model_requirements_commands()


def test_upload_model_s3():
    repo_location = "s3://model-bucket"
    controller = RemoteController(CONFIG_PATH)
    controller.run_commands = mock.Mock()
    controller.upload_model(repo_location)
    commands_taken = [call[0][0] for call in controller.run_commands.call_args_list]
    assert len(commands_taken) == 2
    assert commands_taken[0] == download_from_s3_commands(repo_location)
    assert commands_taken[1] == model_requirements_commands()


@mock.patch("alpaca.remote_controller._download_results")
def test_download_results_s3(downloader):
    local_path = "s3://place"
    controller = RemoteController(CONFIG_PATH)
    controller.run_commands = mock.Mock()

    controller.download_results(None, local_path)
    controller.run_commands.assert_called_once_with(upload_to_s3_commands("/home/ubuntu/runs", local_path))
    downloader.assert_not_called()


@mock.patch("alpaca.remote_controller._download_results")
def test_download_results_local(downloader):
    local_path = "/path/to/place"
    remote_path = "/another/path"
    controller = RemoteController(CONFIG_PATH)
    controller.run_commands = mock.Mock()
    sftp = mock.Mock()
    controller.ssh = mock.Mock()
    controller.ssh.open_sftp.return_value = sftp
    controller.download_results(remote_path, local_path)
    controller.run_commands.assert_not_called()
    downloader.assert_called_once_with(sftp, Path(remote_path), Path(local_path))


@mock.patch("alpaca.remote_controller._download_results")
def test_download_results_reports_a_missing_remote_directory(downloader):
    """A run that never created its output directory should say so, not raise FileNotFoundError."""
    downloader.side_effect = FileNotFoundError
    controller = RemoteController(CONFIG_PATH)
    controller.ssh = mock.Mock()

    with pytest.raises(OasisAlpacaError, match="does not exist on the instance"):
        controller.download_results("/missing/runs", "/path/to/place")


@mock.patch("alpaca.remote_controller.time")
def test__create_instance_iam_instance(mock_time):
    mock_time.time.return_value = 17
    controller = RemoteController(CONFIG_PATH)
    controller.ec2 = mock.Mock()
    controller.ec2.run_instances.return_value = {"Instances": [{"InstanceId": 32}]}
    expected_config = {
        "ImageId": CONFIG["AMI_ID"],
        "InstanceType": CONFIG["INSTANCE_TYPE"],
        "MinCount": 1,
        "MaxCount": 1,
        "NetworkInterfaces": [
            {
                "DeviceIndex": 0,
                "SubnetId": CONFIG["SUBNET_ID"],
                "Groups": [CONFIG["SECURITY_GROUP_ID"]],
                "AssociatePublicIpAddress": True
            }
        ],
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": CONFIG["EC2_NAME"]},
                    {"Key": "ALPACA_END_TIME", "Value": str(17 + 2 * 60 * 60)}
                ]
            }
        ],
        "BlockDeviceMappings": [
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": CONFIG["DISK_GB"],
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True
                }
            }
        ],
        "IamInstanceProfile": {'Name': CONFIG["IAM_INSTANCE_PROFILE"]}
    }
    assert controller._create_instance() == 32
    controller.ec2.run_instances.assert_called_once_with(**expected_config)


@mock.patch("alpaca.remote_controller.time")
def test__create_instance_uses_defaults(mock_time):
    """Optional config falls back to defaults. IAM_INSTANCE_PROFILE is not optional: it is
    required by every entrypoint, since the SSM Agent needs a role to register with.
    """
    mock_time.time.return_value = 42
    controller = RemoteController(CONFIG_PATH)
    new_config = CONFIG.copy()
    default_config = ["INSTANCE_TYPE", "DISK_GB", "EC2_NAME"]
    new_config = {key: value for key, value in new_config.items() if key not in default_config}
    controller.config = new_config
    controller.ec2 = mock.Mock()
    controller.ec2.run_instances.return_value = {"Instances": [{"InstanceId": 99}]}
    expected_config = {
        "ImageId": CONFIG["AMI_ID"],
        "InstanceType": "t3.medium",
        "MinCount": 1,
        "MaxCount": 1,
        "NetworkInterfaces": [
            {
                "DeviceIndex": 0,
                "SubnetId": CONFIG["SUBNET_ID"],
                "Groups": [CONFIG["SECURITY_GROUP_ID"]],
                "AssociatePublicIpAddress": True
            }
        ],
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": "Alpaca"},
                    {"Key": "ALPACA_END_TIME", "Value": str(42 + 2 * 60 * 60)}
                ]
            }
        ],
        "BlockDeviceMappings": [
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": 100,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True
                }
            }
        ],
        "IamInstanceProfile": {'Name': CONFIG["IAM_INSTANCE_PROFILE"]}
    }
    assert controller._create_instance() == 99
    controller.ec2.run_instances.assert_called_once_with(**expected_config)


def test_ssh_max_retries_below_one_is_rejected():
    """Zero retries would leave both wait loops returning as though they had connected."""
    with pytest.raises(OasisAlpacaConfigError):
        RemoteController({**CONFIG, "SSH_MAX_RETRIES": 0})


@mock.patch("alpaca.remote_controller.time")
def test__create_instance_accepts_numeric_config_as_strings(mock_time):
    """Interactive create-config answers and ALPACA_* environment overrides are always strings."""
    mock_time.time.return_value = 17
    alpaca_logger = logging.getLogger("alpaca")
    original_level = alpaca_logger.level
    try:
        controller = RemoteController(
            {**CONFIG, "DISK_GB": "50", "MAX_LIFETIME_HOURS": "3", "LOG_LEVEL": "debug"}, [], OPTIONAL_CONFIG_MODEL
        )
        controller.ec2 = mock.Mock()
        controller.ec2.run_instances.return_value = {"Instances": [{"InstanceId": 7}]}

        assert controller._create_instance() == 7
        kwargs = controller.ec2.run_instances.call_args.kwargs
        assert kwargs["BlockDeviceMappings"][0]["Ebs"]["VolumeSize"] == 50
        assert kwargs["TagSpecifications"][0]["Tags"][1]["Value"] == str(17 + 3 * 60 * 60)
        assert alpaca_logger.level == logging.DEBUG
    finally:
        alpaca_logger.setLevel(original_level)


def test__wait_for_instance():
    controller = RemoteController(CONFIG_PATH)
    controller.ec2 = mock.Mock()
    controller.instance_id = "instance id"
    waiter = mock.Mock()
    controller.ec2.get_waiter.return_value = waiter
    controller.ec2.describe_instances.return_value = {
        "Reservations": [{"Instances": [{"PublicIpAddress": "ip address", "Placement": {"AvailabilityZone": "eu-west-1a"}}]}]
    }
    assert controller._wait_for_instance() == "ip address"
    controller.ec2.describe_instances.assert_called_once_with(InstanceIds=[controller.instance_id])
    waiter.wait.assert_called_once_with(InstanceIds=[controller.instance_id])
    assert controller.availability_zone == "eu-west-1a"


def test_wait_for_ssm_registration_succeeds_immediately():
    controller = RemoteController(CONFIG_PATH)
    controller.session = mock.Mock()
    ssm = controller.session.client.return_value
    ssm.describe_instance_information.return_value = {
        "InstanceInformationList": [{"PingStatus": "Online"}]
    }

    controller.instance_id = "i-fakeinstance"

    controller._wait_for_ssm_registration()

    controller.session.client.assert_called_once_with("ssm")
    ssm.describe_instance_information.assert_called_once_with(
        Filters=[{"Key": "InstanceIds", "Values": ["i-fakeinstance"]}]
    )


@mock.patch("alpaca.remote_controller.time.sleep")
def test_wait_for_ssm_registration_retries_until_online(mock_sleep):
    controller = RemoteController(CONFIG_PATH)
    controller.session = mock.Mock()
    ssm = controller.session.client.return_value
    ssm.describe_instance_information.side_effect = [
        {"InstanceInformationList": []},
        {"InstanceInformationList": [{"PingStatus": "ConnectionLost"}]},
        {"InstanceInformationList": [{"PingStatus": "Online"}]},
    ]

    controller.instance_id = "i-fakeinstance"

    controller._wait_for_ssm_registration()

    assert ssm.describe_instance_information.call_count == 3
    assert mock_sleep.call_count == 2


@mock.patch("alpaca.remote_controller.time.sleep")
def test_wait_for_ssm_registration_fails_after_max_retries(mock_sleep):
    controller = RemoteController(CONFIG_PATH)
    controller.session = mock.Mock()
    ssm = controller.session.client.return_value
    ssm.describe_instance_information.return_value = {"InstanceInformationList": []}

    controller.instance_id = "i-fakeinstance"
    controller.config["SSH_MAX_RETRIES"] = 3

    with pytest.raises(OasisAlpacaError):
        controller._wait_for_ssm_registration()

    assert ssm.describe_instance_information.call_count == 3


@mock.patch("alpaca.remote_controller.paramiko")
def test_wait_for_ssh(paramiko):
    ssh = mock.Mock()
    paramiko.SSHClient.return_value = ssh

    controller = RemoteController(CONFIG_PATH)
    controller.session = mock.Mock()
    instance_connect = controller.session.client.return_value
    controller.instance_id = "i-fakeinstance"
    controller.availability_zone = "eu-west-1a"

    assert controller._wait_for_ssh() == ssh

    controller.session.client.assert_called_once_with("ec2-instance-connect")
    instance_connect.send_ssh_public_key.assert_called_once_with(
        InstanceId="i-fakeinstance",
        InstanceOSUser="ubuntu",
        SSHPublicKey=mock.ANY,
        AvailabilityZone="eu-west-1a",
    )
    paramiko.ProxyCommand.assert_called_once()
    ssh.connect.assert_called_once_with(
        "i-fakeinstance", username="ubuntu", pkey=mock.ANY, sock=paramiko.ProxyCommand.return_value, timeout=15
    )


@mock.patch("alpaca.remote_controller.time.sleep")
@mock.patch("alpaca.remote_controller.paramiko")
def test_wait_for_ssh_retries_on_failure(paramiko, mock_sleep):
    """Test that _wait_for_ssh will retry when SSH connection fails."""
    ssh = mock.Mock()
    paramiko.SSHClient.return_value = ssh
    # First two attempts fail, third succeeds
    ssh.connect.side_effect = [Exception("Connection refused"), Exception("Timeout"), None]

    controller = RemoteController(CONFIG_PATH)
    controller.session = mock.Mock()
    result = controller._wait_for_ssh()

    assert result == ssh
    assert ssh.connect.call_count == 3
    assert mock_sleep.call_count == 2
    # A fresh authorization is pushed before every attempt, since the ephemeral key only lives 60s
    instance_connect = controller.session.client.return_value
    assert instance_connect.send_ssh_public_key.call_count == 3


@mock.patch("alpaca.remote_controller.time.sleep")
@mock.patch("alpaca.remote_controller.paramiko")
def test_wait_for_ssh_fails_after_max_retries(paramiko, mock_sleep):
    """Test that _wait_for_ssh raises error after exceeding max retries."""
    ssh = mock.Mock()
    paramiko.SSHClient.return_value = ssh
    ssh.connect.side_effect = Exception("Connection refused")

    controller = RemoteController(CONFIG_PATH)
    controller.session = mock.Mock()
    controller.config["SSH_MAX_RETRIES"] = 3

    with pytest.raises(OasisAlpacaError):
        controller._wait_for_ssh()

    assert ssh.connect.call_count == 3


@mock.patch("alpaca.remote_controller.time.sleep")
@mock.patch("alpaca.remote_controller.paramiko")
def test_wait_for_ssh_sleeps_between_retries(paramiko, mock_sleep):
    """Test that _wait_for_ssh sleeps between retry attempts."""
    ssh = mock.Mock()
    paramiko.SSHClient.return_value = ssh
    ssh.connect.side_effect = [Exception("Failed"), None]

    controller = RemoteController(CONFIG_PATH)
    controller.session = mock.Mock()
    controller._wait_for_ssh()

    mock_sleep.assert_called_once_with(3)


@mock.patch("alpaca.remote_controller.time.sleep")
@mock.patch("alpaca.remote_controller.paramiko")
def test_wait_for_ssh_retries_when_key_authorization_fails(paramiko, mock_sleep):
    """Test that a failure to push the ephemeral key is retried just like a connect failure."""
    ssh = mock.Mock()
    paramiko.SSHClient.return_value = ssh

    controller = RemoteController(CONFIG_PATH)
    controller.session = mock.Mock()
    instance_connect = controller.session.client.return_value
    instance_connect.send_ssh_public_key.side_effect = [Exception("not registered yet"), None]

    assert controller._wait_for_ssh() == ssh

    assert instance_connect.send_ssh_public_key.call_count == 2
    ssh.connect.assert_called_once()


@mock.patch("alpaca.remote_controller.time.sleep")
@mock.patch("alpaca.remote_controller.paramiko")
def test_wait_for_ssh_closes_failed_attempt(paramiko, mock_sleep):
    """Test that a failed attempt tears down its client and SSM tunnel before retrying,
    otherwise every retry leaks an 'aws ssm start-session' subprocess.
    """
    ssh = mock.Mock()
    paramiko.SSHClient.return_value = ssh
    ssh.connect.side_effect = [Exception("Connection refused"), None]

    controller = RemoteController(CONFIG_PATH)
    controller.session = mock.Mock()
    controller._wait_for_ssh()

    ssh.close.assert_called_once_with()
    paramiko.ProxyCommand.return_value.close.assert_called_once_with()


@mock.patch("alpaca.remote_controller.time.sleep")
@mock.patch("alpaca.remote_controller.paramiko")
def test_wait_for_ssh_survives_failure_during_teardown(paramiko, mock_sleep):
    """Test that an error while tearing down a failed attempt does not mask the connection
    error or abandon the remaining retries.
    """
    ssh = mock.Mock()
    paramiko.SSHClient.return_value = ssh
    ssh.connect.side_effect = [Exception("Connection refused"), None]
    ssh.close.side_effect = ProcessLookupError("already gone")
    paramiko.ProxyCommand.return_value.close.side_effect = ProcessLookupError("already gone")

    controller = RemoteController(CONFIG_PATH)
    controller.session = mock.Mock()

    assert controller._wait_for_ssh() == ssh
    assert ssh.connect.call_count == 2


@mock.patch("alpaca.remote_controller.boto3.Session")
def test_aws_client_without_profile(mock_session):
    controller = RemoteController(CONFIG_PATH)
    controller.config.pop("AWS_PROFILE", None)

    client = controller._aws_client("ssm")

    mock_session.assert_called_once_with(profile_name=None, region_name=CONFIG["AWS_REGION"])
    mock_session.return_value.client.assert_called_once_with("ssm")
    assert client is mock_session.return_value.client.return_value


@mock.patch("alpaca.remote_controller.boto3.Session")
def test_aws_client_uses_profile_for_every_client(mock_session):
    """AWS_PROFILE must reach boto3 as well as the SSM tunnel, otherwise the instance is
    created and polled under the default profile while the tunnel uses the named one.
    """
    controller = RemoteController(CONFIG_PATH)
    controller.config["AWS_PROFILE"] = "oasis"

    controller._aws_client("ec2")
    controller._aws_client("ec2-instance-connect")

    mock_session.assert_called_once_with(profile_name="oasis", region_name=CONFIG["AWS_REGION"])
    assert controller.session is mock_session.return_value
    assert mock_session.return_value.client.call_args_list == [mock.call("ec2"), mock.call("ec2-instance-connect")]
    assert " --profile oasis" in controller._ssm_proxy_command()


def test_ssm_proxy_command_without_profile():
    controller = RemoteController(CONFIG_PATH)
    controller.instance_id = "i-fakeinstance"
    controller.config.pop("AWS_PROFILE", None)
    command = controller._ssm_proxy_command()
    assert command == (
        "aws ssm start-session --target i-fakeinstance "
        f"--document-name AWS-StartSSHSession --parameters 'portNumber=22' --region {CONFIG['AWS_REGION']}"
    )


def test_ssm_proxy_command_with_profile():
    controller = RemoteController(CONFIG_PATH)
    controller.instance_id = "i-fakeinstance"
    controller.config["AWS_PROFILE"] = "oasis"
    command = controller._ssm_proxy_command()
    assert command.endswith(" --profile oasis")


def test_run_commands_with_empty_list():
    """Test that run_commands handles empty command list."""
    controller = RemoteController(CONFIG_PATH)
    controller.ssh = mock.Mock()

    controller.run_commands([])

    controller.ssh.exec_command.assert_not_called()


def test_context_manager_calls_shutdown_on_exception():
    """Test that context manager calls shutdown even when exception occurs."""
    controller = RemoteController(CONFIG_PATH)
    controller.setup_instance = mock.Mock()
    controller.shutdown = mock.Mock()

    try:
        with controller:
            raise ValueError("Test exception")
    except ValueError:
        pass

    controller.shutdown.assert_called_once()


def test_shutdown_with_no_ssh_connection():
    """Test that shutdown handles case when SSH connection doesn't exist."""
    controller = RemoteController(CONFIG_PATH)
    controller.instance_id = "test-id"
    controller.ec2 = mock.Mock()
    controller.ssh = None
    waiter = mock.Mock()
    controller.ec2.get_waiter.return_value = waiter

    controller.shutdown()

    controller.ec2.terminate_instances.assert_called_once()


def test_upload_model_runs_model_requirements():
    """Test that upload_model will install model requirements after downloading."""
    repo = "https://github.com/test/repo"
    controller = RemoteController(CONFIG_PATH)
    controller.run_commands = mock.Mock()

    controller.upload_model(repo)

    commands_called = [call[0][0] for call in controller.run_commands.call_args_list]
    # Check that model_requirements_commands is called
    assert any("requirements" in str(cmd) for cmd in commands_called)


def test_upload_model_rejects_an_unrecognised_location():
    """Neither GitHub nor S3 downloaded nothing at all, then failed later on an empty home."""
    controller = RemoteController(CONFIG_PATH)
    controller.run_commands = mock.Mock()

    with pytest.raises(OasisAlpacaConfigError):
        controller.upload_model("/a/local/path")

    controller.run_commands.assert_not_called()
