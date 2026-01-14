from alpaca.utils import get_timestamp


def run_pytest_commands(pytest_args=""):
    """Runs pytest, storing logs in pytest_logs folder with unique name for time ran"""
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
