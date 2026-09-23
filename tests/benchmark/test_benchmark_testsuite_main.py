from alpaca.benchmark.testsuite_main import log_condition, main, run_pytest_commands
from alpaca.exceptions import OasisAlpacaError
from unittest import mock

import pytest


@mock.patch("alpaca.benchmark.testsuite_main.RemoteController")
def test_main_controller_calls(mock_controller_cls):
    mock_controller = mock_controller_cls.return_value.__enter__.return_value

    mock_controller.config = {
        "REPO_LOCATION": "s3://bucket/model",
        "RESULT_DIRECTORY": "/results",
        "PYTEST_ARGS": "arg barg",
    }

    main({"REPO_LOCATION": "s3://bucket/model", "RESULT_DIRECTORY": "/results", "PYTEST_ARGS": "arg barg"})

    mock_controller.upload_model.assert_called_once_with("s3://bucket/model")

    mock_controller.run_commands.assert_called_once()
    args, kwargs = mock_controller.run_commands.call_args
    assert args[0] == run_pytest_commands("arg barg")
    assert callable(args[1])
    assert kwargs == {"check": True}
    mock_controller.download_results.assert_called_once_with("/home/ubuntu/pytest_logs", "/results")


@mock.patch("alpaca.benchmark.testsuite_main.RemoteController")
def test_main_downloads_logs_then_raises_when_tests_fail(mock_controller_cls):
    """The logs are the point of the run, so they come back even when the suite fails."""
    mock_controller = mock_controller_cls.return_value.__enter__.return_value
    mock_controller.config = {"REPO_LOCATION": "s3://bucket/model", "RESULT_DIRECTORY": "/results"}
    mock_controller.run_commands.side_effect = OasisAlpacaError("Command failed with exit status 1")

    with pytest.raises(OasisAlpacaError):
        main({"REPO_LOCATION": "s3://bucket/model", "RESULT_DIRECTORY": "/results"})

    mock_controller.download_results.assert_called_once_with("/home/ubuntu/pytest_logs", "/results")


@mock.patch("alpaca.benchmark.testsuite_main.RemoteController")
def test_main_passes_the_run_config_dict_straight_to_the_controller(mock_controller_cls):
    """A benchmark target's run_config is already a built dict, not a file path — it must
    reach RemoteController unmodified rather than being treated as a path to load.
    """
    mock_controller = mock_controller_cls.return_value.__enter__.return_value
    mock_controller.config = {"REPO_LOCATION": "s3://bucket/model", "RESULT_DIRECTORY": "/results"}
    run_config = {"REPO_LOCATION": "s3://bucket/model", "RESULT_DIRECTORY": "/results", "RUN_TEST_SUITE": True}

    main(run_config)

    assert mock_controller_cls.call_args.args[0] is run_config


def test_log_condition_matches_the_suite_but_not_the_pip_installs():
    """'sudo pip install pytest' shouldn't stream, but the run itself should."""
    streamed = [command for command in run_pytest_commands() if log_condition(command)]

    assert len(streamed) == 1
    assert "pytest ." in streamed[0]
