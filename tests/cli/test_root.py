import pytest
import alpaca.cli.root as root


@pytest.fixture
def restore_commands():
    original = root.ALPACA_COMMANDS.copy()
    yield
    root.ALPACA_COMMANDS = original


@pytest.fixture
def mock_argv(mocker):
    def _set(argv):
        mocker.patch.object(root.sys, "argv", argv)
    return _set


def test_main_no_args_calls_help(mock_argv, mocker):
    mock_help = mocker.patch.object(root, "alpaca_help")

    mock_argv(["alpaca"])
    root.main()

    mock_help.assert_called_once_with()


def test_main_with_model(mock_argv, restore_commands, mocker):
    mock_model = mocker.Mock()
    assert "model" in root.ALPACA_COMMANDS
    root.ALPACA_COMMANDS["model"] = mock_model

    mock_argv(["alpaca", "model", "config"])
    root.main()

    mock_model.assert_called_once_with(["config"])


def test_main_with_pytest(mock_argv, restore_commands, mocker):
    mock_pytest = mocker.Mock()
    assert "pytest" in root.ALPACA_COMMANDS
    root.ALPACA_COMMANDS["pytest"] = mock_pytest

    mock_argv(["alpaca", "pytest", "configuration"])
    root.main()

    mock_pytest.assert_called_once_with(["configuration"])


def test_main_with_api(mock_argv, restore_commands, mocker):
    mock_api = mocker.Mock()
    assert "api" in root.ALPACA_COMMANDS
    root.ALPACA_COMMANDS["api"] = mock_api

    mock_argv(["alpaca", "api", "config?"])
    root.main()

    mock_api.assert_called_once_with(["config?"])


def test_main_with_config(mock_argv, restore_commands, mocker):
    mock_config = mocker.Mock()
    assert "create-config" in root.ALPACA_COMMANDS
    root.ALPACA_COMMANDS["create-config"] = mock_config

    mock_argv(["alpaca", "create-config", "type"])
    root.main()

    mock_config.assert_called_once_with(["type"])


def test_main_with_help(mock_argv, restore_commands, mocker):
    mock_config = mocker.Mock()
    assert "help" in root.ALPACA_COMMANDS
    root.ALPACA_COMMANDS["help"] = mock_config

    mock_argv(["alpaca", "help"])
    root.main()

    mock_config.assert_called_once_with([])


def test_main_with_help_flags_calls_help(mock_argv, mocker):
    """'alpaca --help' used to report that --help was not a command."""
    mock_help = mocker.patch.object(root, "alpaca_help")

    for flag in ["-h", "--help", "-help", "h"]:
        mock_argv(["alpaca", flag])
        root.main()

    assert mock_help.call_count == 4


def test_main_with_unknown_command_reports_it(mock_argv, capsys):
    mock_argv(["alpaca", "nonsense"])
    root.main()

    assert "Command nonsense not found" in capsys.readouterr().out


def test_alpaca_help_lists_every_command(capsys):
    root.alpaca_help()

    printed = capsys.readouterr().out
    for command in root.ALPACA_COMMANDS:
        assert command in printed


def test_alpaca_version_prints_the_installed_version(capsys, mocker):
    mocker.patch.object(root, "version", return_value="1.2.3")

    root.alpaca_version()

    assert capsys.readouterr().out.strip() == "1.2.3"


def test_alpaca_version_explains_an_uninstalled_package(capsys, mocker):
    """Running from a source tree that was never pip installed has no version to report."""
    mocker.patch.object(root, "version", side_effect=root.PackageNotFoundError)

    root.alpaca_version()

    assert "not installed" in capsys.readouterr().out


def test_main_with_benchmark(mock_argv, restore_commands, mocker):
    mock_benchmark = mocker.Mock()
    assert "benchmark" in root.ALPACA_COMMANDS
    root.ALPACA_COMMANDS["benchmark"] = mock_benchmark

    mock_argv(["alpaca", "benchmark", "benchmark.json"])
    root.main()

    mock_benchmark.assert_called_once_with(["benchmark.json"])
