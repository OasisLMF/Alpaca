from alpaca.model.commands import model_run_commands
from alpaca.model.utils import REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL
from alpaca.remote_controller import RemoteController


def main(config_file):
    """Run an Oasis model on a new EC2 instance, then download the results.

    Uploads the model from REPO_LOCATION and runs it with oasislmf. The instance is
    terminated on the way out.

    A run that exits non-zero raises rather than being reported as a run that worked, so a
    benchmark can tell its failed targets from its successful ones. Results are downloaded
    either way, since a failed run's partial output and logs are worth having.

    Args:
        config_file: Path to the JSON configuration file for the model run.

    Raises:
        OasisAlpacaError: If the model run exits non-zero.
    """
    with RemoteController(config_file, REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL) as controller:
        controller.upload_model(controller.config['REPO_LOCATION'])
        try:
            controller.run_commands(model_run_commands(controller.config['PATH_TO_OASISLMF_JSON']), log_condition, check=True)
        finally:
            controller.download_results(None, controller.config.get("RESULT_DIRECTORY", None))


def log_condition(cmd):
    """Only flows logs for oasislmf model run."""
    return "oasislmf model run" in cmd
