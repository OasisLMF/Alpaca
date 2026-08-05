from alpaca.utils import get_timestamp


def run_pytest_commands(pytest_args=""):
    """Generate commands to install pytest dependencies and run tests.
    Saves results to timestamped ./pytest_logs/pytest-YYYYMMDDHHMM.txt.

    Args:
        pytest_args: Additional arguments to pass to pytest (e.g., '-k test_name',
            '--maxfail=3'). The -vv flag is always included.

    Returns:
        list[str]: Shell commands to execute in sequence.
    """
    timestamp = get_timestamp()
    commands = [
        "sudo pip install pytest -qq",
        "sudo pip install hypothesis -qq",
        "sudo pip install mock -qq",
        "sudo pip install responses -qq",
        "mkdir -p pytest_logs",
        f"pytest . -vv {pytest_args} | tee pytest_logs/pytest-{timestamp}.txt"
    ]
    return commands
