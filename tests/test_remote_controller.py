from alpaca.remote_controller import RemoteController
from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from alpaca.scripts import (
    setup_python_commands, download_from_github_commands, download_from_s3_commands, model_requirements_commands,
    upload_to_s3_commands
)

from unittest import mock
from pathlib import Path

import pytest
import json


CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)


@mock.patch.object(RemoteController, "setup_instance")
@mock.patch.object(RemoteController, "shutdown")
def test_context_manager_calls_setup_and_shutdown(mock_shutdown, mock_setup):
    with RemoteController(CONFIG_PATH, {}) as rc:
        # Check instantiates vars
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


@mock.patch("alpaca.remote_controller.boto3.client")
def test_setup_instance_success(mock_boto_client):
    controller = RemoteController(CONFIG_PATH, [])

    controller._create_instance = mock.Mock(return_value="instancey mcinstanceface")
    controller._wait_for_instance = mock.Mock(return_value="2.3.5.7")
    controller._wait_for_ssh = mock.Mock(return_value=mock.Mock())
    controller.run_commands = mock.Mock()
    controller.shutdown = mock.Mock()

    mock_ec2 = mock.Mock()
    mock_boto_client.return_value = mock_ec2

    controller.setup_instance()

    mock_boto_client.assert_called_once_with(
        "ec2", region_name=CONFIG["AWS_REGION"]
    )

    controller._create_instance.assert_called_once()
    controller._wait_for_instance.assert_called_once()
    controller._wait_for_ssh.assert_called_once()

    controller.run_commands.assert_called_once_with(
        setup_python_commands(CONFIG["OASISLMF_VERSION"])
    )

    controller.shutdown.assert_not_called()

    assert controller.ec2 is mock_ec2
    assert controller.instance_id == "instancey mcinstanceface"
    assert controller.public_ip == "2.3.5.7"


@mock.patch("alpaca.remote_controller.boto3")
def test_setup_instance_failure(mock_boto):
    mock_boto.client = mock.Mock(side_effect=ValueError())
    controller = RemoteController(CONFIG_PATH, [])
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


def test__create_config_returns_config():
    controller = RemoteController(CONFIG_PATH)
    config = controller._create_config(CONFIG_PATH, [], [])
    assert config == CONFIG


@mock.patch("alpaca.remote_controller.os")
def test__create_config_uses_environment(mock_os):
    mock_os.environ = {
        "ALPACA_1": "2",
        "ALPACA_3": "4",
        "ALPACA_SUBNET_ID": "should not override config"
    }
    controller = RemoteController(CONFIG_PATH)
    config = controller._create_config(CONFIG_PATH, [("1", "", ""), ("SUBNET_ID", "", "")], [("3", "", "")])
    assert config["1"] == "2"
    assert config["3"] == "4"
    assert config["SUBNET_ID"] != "should not override config"


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
        "KeyName": CONFIG["KEY_NAME"],
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
def test__create_instance_no_iam_instance(mock_time):
    mock_time.time.return_value = 42
    controller = RemoteController(CONFIG_PATH)
    new_config = CONFIG.copy()
    default_config = ["IAM_INSTANCE_PROFILE", "INSTANCE_TYPE", "DISK_GB", "EC2_NAME"]
    new_config = {key: value for key, value in new_config.items() if key not in default_config}
    controller.config = new_config
    controller.ec2 = mock.Mock()
    controller.ec2.run_instances.return_value = {"Instances": [{"InstanceId": 99}]}
    expected_config = {
        "ImageId": CONFIG["AMI_ID"],
        "InstanceType": "t3.medium",
        "MinCount": 1,
        "MaxCount": 1,
        "KeyName": CONFIG["KEY_NAME"],
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
        ]
    }
    assert controller._create_instance() == 99
    controller.ec2.run_instances.assert_called_once_with(**expected_config)


def test__wait_for_instance():
    controller = RemoteController(CONFIG_PATH)
    controller.ec2 = mock.Mock()
    controller.instance_id = "instance id"
    waiter = mock.Mock()
    controller.ec2.get_waiter.return_value = waiter
    controller.ec2.describe_instances.return_value = {"Reservations": [{"Instances": [{"PublicIpAddress": "ip address"}]}]}
    assert controller._wait_for_instance() == "ip address"
    controller.ec2.describe_instances.assert_called_once_with(InstanceIds=[controller.instance_id])
    waiter.wait.assert_called_once_with(InstanceIds=[controller.instance_id])


@mock.patch("alpaca.remote_controller.paramiko")
def test_wait_for_ssh(paramiko):
    ssh = mock.Mock()
    paramiko.SSHClient.return_value = ssh
    controller = RemoteController(CONFIG_PATH)
    assert controller._wait_for_ssh() == ssh
    paramiko.RSAKey.from_private_key_file.assert_called_once_with(CONFIG["KEY_PATH"])
    ssh.connect.assert_called_once()
