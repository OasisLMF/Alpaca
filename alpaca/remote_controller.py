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

logger = logging.getLogger(__name__)


class RemoteController:
    """Controller for managing remote EC2 instances. Designed to be used as a context manager.

    Example:
        with RemoteController(config_file, REQUIRED_CONFIG, OPTIONAL_CONFIG) as rc:
            rc.upload_model(repo_location)
            rc.run_commands(["mkdir runs", 'echo "hello world" > runs/file.txt'])
            rc.download_results()

    Attributes:
        config (dict): Configuration dictionary loaded from JSON file and environment.
        ec2 (boto3.client): AWS EC2 client for instance management.
        ssh (paramiko.SSHClient): SSH client for remote command execution.
        instance_id (str): The AWS instance ID of the created EC2 instance.
        public_ip (str): Public IP address of the running instance.

    Raises:
        OasisAlpacaConfigError: If required configuration keys are missing.
        OasisAlpacaError: If instance setup or SSH connection fails.
    """

    def __init__(self, config_file, required_config=[], optional_config=[]):
        """Initialize the RemoteController with configuration.

        Args:
            config_file: Path to JSON configuration file containing AWS and run settings.
            required_config: List of tuples (key, description, default) for required config keys.
                If a required key is missing from the config file, it will be read from
                the environment variable ALPACA_{key}. Raises error if still not found.
            optional_config: List of tuples (key, description, default) for optional config keys.
                These are loaded from environment variables if not present in config file.

        Raises:
            OasisAlpacaConfigError: If any required configuration key is missing from both
                the config file and environment variables.
        """
        self.config = self._create_config(config_file, required_config, optional_config)
        self.ec2 = None
        self.ssh = None
        self.instance_id = None
        self.public_ip = None
        # Set up log levels for all modules
        log_level_str = self.config.get("LOG_LEVEL", "INFO")
        log_level = getattr(logging, log_level_str, logging.INFO)
        logging.getLogger("alpaca").setLevel(log_level)
        logging.getLogger("botocore").setLevel(log_level)
        logging.getLogger("paramiko").setLevel(log_level)
        logging.getLogger("urllib3").setLevel(log_level)

    def __enter__(self):
        """Sets up the EC2 instance by calling self.setup_instance.

        Returns:
            RemoteController: Controller ready for command execution.
        """
        self.setup_instance()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the context manager, ensuring instance cleanup. Terminates the EC2 instance and
        closes SSH connection, regardless of whether an exception occurred.

        Args:
            exc_type: Exception type if an exception was raised, None otherwise.
            exc_value: Exception value if an exception was raised, None otherwise.
            traceback: Traceback object if an exception was raised, None otherwise.

        Returns:
            None: Exceptions are not suppressed.
        """
        self.shutdown()
        logger.debug(exc_type, exc_value, traceback)

    def setup_instance(self):
        """Create and configure the EC2 instance for model execution.

        1. Creates an EC2 client for the configured AWS region
        2. Launches a new EC2 instance with the specified configuration
        3. Waits for the instance to reach 'running' state
        4. Establishes an SSH connection (with retries)
        5. Installs Python and OasisLMF dependencies on the EC2 instance.

        Raises:
            OasisAlpacaError: If any step in the setup process fails.
        """
        try:
            self.ec2 = boto3.client("ec2", region_name=self.config.get("AWS_REGION", 'eu-west-1'))
            self.instance_id = self._create_instance()
            self.public_ip = self._wait_for_instance()
            self.ssh = self._wait_for_ssh()
            self.run_commands(setup_python_commands(self.config.get('OASISLMF_VERSION', None)))
        except KeyboardInterrupt:
            # Ctrl c here will skip shutdown as it is differently cased to exception
            self.shutdown()
        except Exception as e:
            self.shutdown()
            raise OasisAlpacaError(f"Error during instance setup: {e}")

    def shutdown(self):
        """Terminates the EC2 instance and close all connections.
        Called automatically when exiting the context manager.
        """
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
        """Execute shell commands on the remote EC2 instance via SSH.

        Args:
            commands: List of shell command strings to execute sequentially.
            log_condition: Optional callable(cmd) -> bool that determines whether
                a command's output should be streamed in real-time (True) or
                logged only at debug level after completion (False).
                Defaults to logging all commands at debug level.
        """
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
        """Download and set up an OasisLMF model on the EC2 instance.
        After downloading, installs any Python requirements from requirements.txt.

        Args:
            repo_location: URL of the model source. Either a GitHub URL
                (e.g., 'https://github.com/org/repo') or S3 URI
                (e.g., 's3://bucket/path').
        """
        if 'github.com' in repo_location:
            self.run_commands(download_from_github_commands(repo_location))
        elif repo_location.startswith("s3"):
            self.run_commands(download_from_s3_commands(repo_location))
        self.run_commands(model_requirements_commands())

    def download_results(self, from_path=None, to_path=None):
        """Download model execution results from the EC2 instance.

        Args:
            from_path: Path on the EC2 instance to download from.
                Defaults to '/home/ubuntu/runs'.
            to_path: Destination for results. Can be:
                - Local filesystem path (e.g., './results')
                - S3 URI (e.g., 's3://bucket/results')
                Defaults to './runs' in the current working directory.
        """
        logger.info("Starting download of results folder")
        if from_path is None:
            from_path = "/home/ubuntu/runs"

        if to_path and "s3://" in to_path:
            return self.run_commands(upload_to_s3_commands(from_path, to_path))
        if to_path is None:
            to_path = Path(os.getcwd()) / "runs"
        sftp = self.ssh.open_sftp()
        _download_results(sftp, Path(from_path), Path(to_path))
        logger.info("Download complete")

    def _create_config(self, config_file, required_config, optional_config):
        """Load and validate configuration from JSON file and environment variables.
        JSON config always takes priority.

        Args:
            config_file: Path to the JSON configuration file.
            required_config: List of (key, description, default) tuples for required keys.
            optional_config: List of (key, description, default) tuples for optional keys.

        Returns:
            dict: Merged configuration dictionary.

        Raises:
            OasisAlpacaConfigError: If a required key is missing from both file and environment.
        """
        with open(config_file, 'r') as f:
            config = json.load(f)
        for (key, _, _) in required_config:
            if key not in config:
                if f"ALPACA_{key}" in os.environ:
                    logger.info(f"Config {key} taken from environment")
                    config[key] = os.environ[f"ALPACA_{key}"]
                else:
                    raise OasisAlpacaConfigError(f"Missing required key {key} from alpaca config")
        for (key, _, _) in optional_config:
            if key not in config and f"ALPACA_{key}" in os.environ:
                logger.info(f"Config {key} taken from environment")
                config[key] = os.environ[f"ALPACA_{key}"]
        return config

    def _create_instance(self):
        """Launch a new EC2 instance with the configured settings.

        Returns:
            str: The instance ID of the newly created EC2 instance.
        """
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
                        {"Key": "ALPACA_END_TIME", "Value": str(time.time() + self.config.get("MAX_LIFETIME_HOURS", 2) * 60 * 60)}
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
        """Wait for the EC2 instance to reach 'running' state and get its IP.

        Returns:
            str: The public IP address of the running instance.
        """
        logger.info("Waiting for instance to enter 'running' state")
        waiter = self.ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[self.instance_id])

        desc = self.ec2.describe_instances(InstanceIds=[self.instance_id])
        public_ip = desc["Reservations"][0]["Instances"][0]["PublicIpAddress"]

        logger.info(f"Instance public IP: {public_ip}")
        return public_ip

    def _wait_for_ssh(self):
        """Waits to establish SSH connection to the instance with retries, then returns connected client.

        Returns:
            paramiko.SSHClient: Connected SSH client

        Raises:
            OasisAlpacaError: If connection fails after SSH_MAX_RETRIES attempts
                (default: 60 retries = 3 minutes).
        """
        logger.info("Waiting for SSH")
        key = paramiko.RSAKey.from_private_key_file(self.config['KEY_PATH'])

        max_retries = int(self.config.get("SSH_MAX_RETRIES", 60))
        retry_count = 0

        while retry_count < max_retries:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(self.public_ip, username="ubuntu", pkey=key, timeout=5)
                return ssh
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise OasisAlpacaError(f"Failed to establish SSH connection after {max_retries} attempts: {e}")
                time.sleep(3)

    def _ssh_logs_important(self, stdout, stderr):
        """Stream command output in real-time for important commands.

        Args:
            stdout: Paramiko ChannelFile for standard output.
            stderr: Paramiko ChannelFile for standard error (combined with stdout).
        """
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
        """Log command output after completion. Non-error output is only logged at the debug level.

        Args:
            stdout: Paramiko ChannelFile for standard output.
            stderr: Paramiko ChannelFile for standard error.
        """
        out = stdout.read().decode("utf-8").strip()
        err = stderr.read().decode("utf-8").strip()
        if out:
            logger.debug(out)
        if err:
            logger.warning(err)
