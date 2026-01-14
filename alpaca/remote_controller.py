from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from alpaca.utils import remove_start, _download_results
from alpaca.scripts import (
    download_from_github_commands, download_from_s3_commands, upload_to_s3_commands, setup_python_commands, model_requirements_commands
)
import json
import logging
import boto3
import paramiko
import time
import os
import codecs
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class RemoteController():
    def __init__(self, config_file, required_config):
        self.config = self._create_config(config_file, required_config)  # To ensure no required config is missing
        self.ec2 = None
        self.ssh = None
        self.instance_id = None
        self.public_ip = None
        logger.setLevel(self.config.get("LOG_LEVEL", "INFO"))

    def __enter__(self):
        self.setup_instance()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.shutdown()
        logger.debug(exc_type, exc_value, traceback)

    def setup_instance(self):
        """Makes EC2, SSH's in and sets up Python/OasisLMF"""
        try:
            self.ec2 = boto3.client("ec2", region_name=self.config["AWS_REGION"])
            self.instance_id = self._create_instance()
            self.public_ip = self._wait_for_instance()
            self.ssh = self._wait_for_ssh()
            self.run_commands(setup_python_commands(self.config.get('OASISLMF_VERSION', None)))
        except Exception as e:
            self.shutdown()
            raise OasisAlpacaError(f"Error during instance setup: {e}")

    def shutdown(self):
        if self.ssh:
            self.ssh.close()
        if not self.instance_id or not self.ec2:
            return
        logger.info(f"Terminating instance {self.instance_id}")
        self.ec2.terminate_instances(InstanceIds=[self.instance_id])

        waiter = self.ec2.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=[self.instance_id])

        logger.info("Instance terminated.")

    def run_commands(self, commands, log_condition=None):
        """Run shell commands over SSH using Paramiko."""
        log_condition = log_condition or (lambda cmd: False)
        for cmd in commands:
            logger.info(f"Executing: {cmd}")
            needs_logs = log_condition(cmd)
            stdin, stdout, stderr = self.ssh.exec_command(cmd, get_pty=needs_logs)

            if needs_logs:
                self._ssh_logs_important(stdout, stderr)
            else:
                self._ssh_logs_unimportant(stdout, stderr)

    def upload_model(self, repo_location):
        """Upload model to ec2 instance"""
        if 'github.com' in repo_location:
            self.run_commands(download_from_github_commands(repo_location))
        elif repo_location.startswith("s3"):
            self.run_commands(download_from_s3_commands(repo_location))
        self.run_commands(model_requirements_commands())

    def download_results(self, remote_path=None, local_path=None):
        """Download all data from remote_path to local_path"""
        logger.info("Starting download of results folder")
        if remote_path is None:
            remote_path = "/home/ubuntu/runs"

        if local_path and "s3://" in local_path:
            return self.run_commands(upload_to_s3_commands(remote_path, local_path))
        if local_path is None:
            local_path = Path(os.getcwd()) / "runs"
        sftp = self.ssh.open_sftp()
        _download_results(sftp, Path(remote_path), Path(local_path))
        logger.info("Download complete")

    def _create_config(self, config_file, required_config):
        with open(config_file, 'r') as f:
            config = json.load(f)
        for (key, _, _) in required_config:
            if key not in config:
                raise OasisAlpacaConfigError(f"Missing key {key} from alpaca config")
        return config

    def _create_instance(self):
        """Creating EC2 instance using config"""
        ec2_kwargs = {
            "ImageId": self.config["AMI_ID"],
            "InstanceType": self.config.get("INSTANCE_TYPE", "t3.medium"),
            "MinCount": 1,
            "MaxCount": 1,
            "KeyName": self.config["KEY_NAME"],
            "NetworkInterfaces": [
                {
                    "DeviceIndex": 0,
                    "SubnetId": self.config["SUBNET_ID"],
                    "Groups": [self.config["SECURITY_GROUP_ID"]],
                    "AssociatePublicIpAddress": True
                }
            ],
            "TagSpecifications": [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": self.config.get("EC2_NAME", "Alpaca")},
                    ]
                }
            ],
            "BlockDeviceMappings": [
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize": self.config.get("DISK_GB", 100),
                        "VolumeType": "gp3",
                        "DeleteOnTermination": True
                    }
                }
            ],
        }
        if "IAM_INSTANCE_PROFILE" in self.config:
            ec2_kwargs["IamInstanceProfile"] = {'Name': self.config["IAM_INSTANCE_PROFILE"]}

        resp = self.ec2.run_instances(**ec2_kwargs)

        instance_id = resp["Instances"][0]["InstanceId"]
        logger.info(f"Instance launched: {instance_id}")
        return instance_id

    def _wait_for_instance(self):
        """Wait for EC2 to be running"""
        logger.info("Waiting for instance to enter 'running' state")
        waiter = self.ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[self.instance_id])

        desc = self.ec2.describe_instances(InstanceIds=[self.instance_id])
        public_ip = desc["Reservations"][0]["Instances"][0]["PublicIpAddress"]

        logger.info(f"Instance public IP: {public_ip}")
        return public_ip

    def _wait_for_ssh(self):
        """Wait for the SSH connection"""
        logger.info("Waiting for SSH")
        key = paramiko.RSAKey.from_private_key_file(self.config['KEY_PATH'])

        while True:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(self.public_ip, username="ubuntu", pkey=key, timeout=5)
                return ssh
            except Exception:
                time.sleep(3)

    def _ssh_logs_important(self, stdout, stderr):
        """Logging handler for important logs"""
        stdout.channel.set_combine_stderr(True)
        decoder = codecs.getincrementaldecoder("utf-8")()
        while not stdout.channel.exit_status_ready() or stdout.channel.recv_ready():
            if stdout.channel.recv_ready():
                chunk = stdout.channel.recv(4096)
                data = decoder.decode(chunk)
                for line in data.splitlines():
                    line = remove_start(line)
                    if line:
                        logger.info(line)
            else:
                time.sleep(1)

    def _ssh_logs_unimportant(self, stdout, stderr):
        """Logging handler for unimportant logs"""
        out = stdout.read().decode("utf-8").strip()
        err = stderr.read().decode("utf-8").strip()
        if out:
            logger.debug(out)
        if err:
            logger.warning(err)
