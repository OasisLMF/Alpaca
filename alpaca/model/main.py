from alpaca.model.scripts import model_run_commands
from alpaca.model.utils import REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL
from alpaca.remote_controller import RemoteController


def main(config_file):
    """Run an Oasis model on a new EC2 instance, then download the results.

    Uploads the model from REPO_LOCATION and runs it with oasislmf. The instance is
    terminated on the way out.

    Args:
        config_file: Path to the JSON configuration file for the model run.
    """
    with RemoteController(config_file, REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL) as controller:
        controller.upload_model(controller.config['REPO_LOCATION'])
        controller.run_commands(model_run_commands(controller.config['PATH_TO_OASISLMF_JSON']), log_condition)
        controller.download_results(None, controller.config.get("RESULT_DIRECTORY", None))


def log_condition(cmd):
    """Only flows logs for oasislmf model run."""
    return cmd.startswith("oasislmf model")


if __name__ == "__main__":
    main()
