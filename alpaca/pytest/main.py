from alpaca.pytest.utils import REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST
from alpaca.pytest.commands import run_pytest_commands
from alpaca.remote_controller import RemoteController


def main(config_file):
    """Run a repository's pytest suite on a new EC2 instance, then download the logs.

    Uploads the repository from REPO_LOCATION and runs pytest with PYTEST_ARGS. The
    instance is terminated on the way out.

    Args:
        config_file: Path to the JSON configuration file for the pytest run.
    """
    with RemoteController(config_file, REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST) as controller:
        controller.upload_model(controller.config['REPO_LOCATION'])
        controller.run_commands(run_pytest_commands(controller.config.get('PYTEST_ARGS', "")), log_condition)
        controller.download_results("/home/ubuntu/pytest_logs", controller.config.get('RESULT_DIRECTORY', None))


def log_condition(cmd):
    """Only flows logs from pytest run."""
    return cmd.startswith("pytest")


if __name__ == "__main__":
    main()
