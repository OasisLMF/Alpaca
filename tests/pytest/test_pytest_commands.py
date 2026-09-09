from alpaca.pytest.commands import run_pytest_commands
from unittest import mock


def test_run_pytest_installs_before_running():
    """Test that run_pytest_commands will install all modules before running pytest."""
    commands = run_pytest_commands()
    installs = ["pip install pytest", "pip install hypothesis", "pip install mock", "pip install responses"]

    installs_all_first = False
    for command in commands:
        for install in installs:
            if install in command:
                installs.remove(install)
        if "pytest ." in command:
            if installs == []:
                installs_all_first = True
            break
    assert installs_all_first


def test_run_pytest_creates_log_directory_before_running():
    """Test that run_pytest_commands will create pytest_logs directory before running."""
    commands = run_pytest_commands()

    creates_log_dir = False
    for command in commands:
        if "mkdir" in command and "pytest_logs" in command:
            creates_log_dir = True
            break
        if "pytest ." in command:
            assert False
    assert creates_log_dir


def test_run_pytest_uses_custom_args():
    """Test that run_pytest_commands includes custom pytest arguments."""
    custom_args = "custom args"
    commands = run_pytest_commands(custom_args)

    uses_custom_args = False
    for command in commands:
        if custom_args in command and "pytest ." in command:
            uses_custom_args = True
            break
    assert uses_custom_args


def test_run_pytest_with_empty_args():
    """Test that run_pytest_commands works with empty arguments."""
    commands = run_pytest_commands("")

    runs_pytest = False
    for command in commands:
        if "pytest ." in command:
            runs_pytest = True
            break
    assert runs_pytest


@mock.patch("alpaca.pytest.commands.get_timestamp")
def test_run_pytest_saves_to_correct_location(mock_timestamp):
    """Test that run_pytest_commands uses timestamp and location for log file name."""
    mock_timestamp.return_value = "timestamp"
    commands = run_pytest_commands()
    logs_output = False
    for command in commands:
        if "pytest ." in command and "tee pytest_logs/pytest-timestamp.txt" in command:
            logs_output = True
            break
    assert logs_output


def test_run_pytest_commands_reports_pytests_exit_status():
    """Without pipefail the piped suite reports tee's exit status, so failures look green."""
    command = next(c for c in run_pytest_commands() if "pytest ." in c)

    assert command.startswith("set -o pipefail; ")
