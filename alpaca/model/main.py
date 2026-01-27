from alpaca.model.scripts import model_run_commands
from alpaca.model.utils import REQUIRED_CONFIG, OPTIONAL_CONFIG
from alpaca.remote_controller import RemoteController


def main(config_file):
    with RemoteController(config_file, REQUIRED_CONFIG, OPTIONAL_CONFIG) as controller:
        controller.upload_model(controller.config['REPO_LOCATION'])
        controller.run_commands(model_run_commands(controller.config['PATH_TO_OASISLMF_JSON']), log_condition)
        controller.download_results(None, controller.config.get("RESULT_DIRECTORY", None))


def log_condition(cmd):
    return cmd.startswith("oasislmf model")


if __name__ == "__main__":
    main()
