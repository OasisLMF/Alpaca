from alpaca.pytest.utils import REQUIRED_CONFIG, OPTIONAL_CONFIG
from alpaca.pytest.scripts import run_pytest_commands
from alpaca.remote_controller import RemoteController


def main(config_file):
    with RemoteController(config_file, REQUIRED_CONFIG, OPTIONAL_CONFIG) as controller:
        controller.upload_model(controller.config['REPO_LOCATION'])
        controller.run_commands(run_pytest_commands(controller.config.get('PYTEST_ARGS', "")), log_condition)
        controller.download_results("/home/ubuntu/pytest_logs", controller.config.get('RESULT_DIRECTORY', None))


def log_condition(cmd):
    return cmd.startswith("pytest")


if __name__ == "__main__":
    main()
