from alpaca.api.scripts import api_run_commands, docker_install_commands, deploy_oasis_server_commands, wait_for_oasis_server_commands
from alpaca.api.utils import REQUIRED_CONFIG_API, OPTIONAL_CONFIG_API
from alpaca.remote_controller import RemoteController


def main(config_file):
    """Run an Oasis API deployment on a new EC2 instance, then download the results.

    Uploads the model, installs Docker, deploys the Oasis server, waits for it to come up
    and runs the model through the API. The instance is terminated on the way out.

    Args:
        config_file: Path to the JSON configuration file for the API run.
    """
    with RemoteController(config_file, REQUIRED_CONFIG_API, OPTIONAL_CONFIG_API) as controller:
        controller.upload_model(controller.config['REPO_LOCATION'])
        controller.run_commands(docker_install_commands())
        controller.run_commands(deploy_oasis_server_commands(controller.config['PATH_TO_DOCKER_COMPOSE']))
        controller.run_commands(wait_for_oasis_server_commands())
        controller.run_commands(api_run_commands(controller.config['PATH_TO_OASISLMF_JSON']), log_condition)
        controller.download_results(None, controller.config.get("RESULT_DIRECTORY", None))


def log_condition(cmd):
    """Only uses flow logs for api run command."""
    return cmd.startswith("oasislmf api")


if __name__ == "__main__":
    main()
