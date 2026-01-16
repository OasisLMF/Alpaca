from alpaca.pytest.main import main, run_pytest_commands
from unittest import mock


@mock.patch("alpaca.pytest.main.RemoteController")
def test_main_controller_calls(mock_controller_cls):
    mock_controller = mock_controller_cls.return_value.__enter__.return_value

    mock_controller.config = {
        "REPO_LOCATION": "/repo",
        "PATH_TO_OASISLMF_JSON": "/path/config.json",
        "RESULT_DIRECTORY": "/results",
        "PYTEST_ARGS": "arg barg"
    }

    main("config.json")

    mock_controller.upload_model.assert_called_once_with("/repo")

    mock_controller.run_commands.assert_called_once()
    args, kwargs = mock_controller.run_commands.call_args
    assert args[0] == run_pytest_commands("arg barg")
    assert callable(args[1])
    assert kwargs == {}
    mock_controller.download_results.assert_called_once_with("/home/ubuntu/pytest_logs", "/results")
