from alpaca.pytest.main import log_condition, main, run_pytest_commands
from alpaca.exceptions import OasisAlpacaError
from unittest import mock

import pytest


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
    assert kwargs == {"check": True}
    mock_controller.download_results.assert_called_once_with("/home/ubuntu/pytest_logs", "/results")


@mock.patch("alpaca.pytest.main.RemoteController")
def test_main_downloads_logs_then_raises_when_tests_fail(mock_controller_cls):
    """The logs are the point of the run, so they come back even when the suite fails."""
    mock_controller = mock_controller_cls.return_value.__enter__.return_value
    mock_controller.config = {"REPO_LOCATION": "/repo", "RESULT_DIRECTORY": "/results"}
    mock_controller.run_commands.side_effect = OasisAlpacaError("Command failed with exit status 1")

    with pytest.raises(OasisAlpacaError):
        main("config.json")

    mock_controller.download_results.assert_called_once_with("/home/ubuntu/pytest_logs", "/results")


def test_log_condition_matches_the_suite_but_not_the_pip_installs():
    """'sudo pip install pytest' shouldn't stream, but the run itself should."""
    streamed = [command for command in run_pytest_commands() if log_condition(command)]

    assert len(streamed) == 1
    assert "pytest ." in streamed[0]
