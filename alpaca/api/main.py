from alpaca.api.scripts import api_run_commands, docker_install_commands, deploy_oasis_server_commands, wait_for_oasis_server_commands
from alpaca.api.utils import REQUIRED_CONFIG, OPTIONAL_CONFIG
from alpaca.remote_controller import RemoteController


def main(config_file):
    with RemoteController(config_file, REQUIRED_CONFIG, OPTIONAL_CONFIG) as controller:
        controller.upload_model(controller.config['REPO_LOCATION'])
        controller.run_commands(docker_install_commands())
        controller.run_commands(deploy_oasis_server_commands(controller.config['PATH_TO_DOCKER_COMPOSE']))
        controller.run_commands(wait_for_oasis_server_commands())
        controller.run_commands(api_run_commands(controller.config['PATH_TO_OASISLMF_JSON']), log_condition)
        controller.download_results(None, controller.config.get("RESULT_DIRECTORY", None))


def log_condition(cmd):
    return cmd.startswith("oasislmf api")


if __name__ == "__main__":
    main()
