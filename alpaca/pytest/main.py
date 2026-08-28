from alpaca.pytest.utils import REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST
from alpaca.pytest.commands import run_pytest_commands
from alpaca.remote_controller import RemoteController


def main(config_file):
    """Run a repository's pytest suite on a new EC2 instance, then download the logs.

    Uploads the repository from REPO_LOCATION and runs pytest with PYTEST_ARGS. The
    instance is terminated on the way out.

    A suite that fails raises rather than being reported as a run that passed, so an
    unattended run doesn't look green when it isn't. The logs are downloaded either way,
    since they are the whole point of the run.

    Args:
        config_file: Path to the JSON configuration file for the pytest run.

    Raises:
        OasisAlpacaError: If any test fails, or pytest itself can't run.
    """
    with RemoteController(config_file, REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST) as controller:
        controller.upload_model(controller.config['REPO_LOCATION'])
        try:
            controller.run_commands(run_pytest_commands(controller.config.get('PYTEST_ARGS', "")), log_condition, check=True)
        finally:
            controller.download_results("/home/ubuntu/pytest_logs", controller.config.get('RESULT_DIRECTORY', None))


def log_condition(cmd):
    """Only flows logs from pytest run, not from the pip installs that mention pytest."""
    return "pytest ." in cmd
