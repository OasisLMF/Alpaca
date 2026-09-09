from alpaca.model.main import log_condition, main, model_run_commands
from alpaca.exceptions import OasisAlpacaError
from unittest import mock

import pytest


@mock.patch("alpaca.model.main.RemoteController")
def test_main_controller_calls(mock_controller_cls):
    mock_controller = mock_controller_cls.return_value.__enter__.return_value

    mock_controller.config = {
        "REPO_LOCATION": "/repo",
        "PATH_TO_OASISLMF_JSON": "/path/config.json",
        "RESULT_DIRECTORY": "/results",
    }

    main("config.json")

    mock_controller.upload_model.assert_called_once_with("/repo")

    mock_controller.run_commands.assert_called_once()
    args, kwargs = mock_controller.run_commands.call_args
    assert args[0] == model_run_commands("/path/config.json")
    assert callable(args[1])
    assert kwargs == {"check": True}
    mock_controller.download_results.assert_called_once_with(None, "/results")


@mock.patch("alpaca.model.main.RemoteController")
def test_main_downloads_results_then_raises_when_the_run_fails(mock_controller_cls):
    """A failed run's partial output is worth having, and the failure must not be swallowed."""
    mock_controller = mock_controller_cls.return_value.__enter__.return_value
    mock_controller.config = {"REPO_LOCATION": "/repo", "PATH_TO_OASISLMF_JSON": "/c.json", "RESULT_DIRECTORY": "/results"}
    mock_controller.run_commands.side_effect = OasisAlpacaError("Command failed with exit status 1")

    with pytest.raises(OasisAlpacaError):
        main("config.json")

    mock_controller.download_results.assert_called_once_with(None, "/results")


def test_log_condition_still_matches_the_piped_model_run():
    """The pipefail prefix means the command no longer starts with 'oasislmf'."""
    assert any(log_condition(command) for command in model_run_commands("/c.json"))
