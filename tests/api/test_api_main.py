from alpaca.api.main import main
from alpaca.api.scripts import api_run_commands, docker_install_commands, deploy_oasis_server_commands, wait_for_oasis_server_commands
from unittest import mock


@mock.patch("alpaca.api.main.RemoteController")
def test_main_controller_calls(mock_controller_cls):
    mock_controller = mock_controller_cls.return_value.__enter__.return_value

    mock_controller.config = {
        "REPO_LOCATION": "/repo",
        "PATH_TO_OASISLMF_JSON": "/path/config.json",
        "RESULT_DIRECTORY": "/results",
        "PATH_TO_DOCKER_COMPOSE": "/path/docker-compose.yml"
    }

    main("config.json")

    mock_controller.upload_model.assert_called_once_with("/repo")

    assert mock_controller.run_commands.call_count == 4
    calls = [i[0][0] for i in mock_controller.run_commands.call_args_list]
    assert calls[0] == docker_install_commands()
    assert calls[1] == deploy_oasis_server_commands(mock_controller.config["PATH_TO_DOCKER_COMPOSE"])
    assert calls[2] == wait_for_oasis_server_commands()
    assert calls[3] == api_run_commands(mock_controller.config["PATH_TO_OASISLMF_JSON"])
    mock_controller.download_results.assert_called_once_with(None, "/results")
