from alpaca.api.utils import REQUIRED_CONFIG_API, OPTIONAL_CONFIG_API
from alpaca.model.utils import REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL
from alpaca.pytest.utils import REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST
from alpaca.exceptions import OasisAlpacaConfigError
from alpaca.cli.images import print_alpaca
from alpaca.config import create_config

CONFIGS = {
    'api': (REQUIRED_CONFIG_API, OPTIONAL_CONFIG_API),
    'model': (REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL),
    'pytest': (REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST)
}


def create_config_router(args=None):
    """Route to the appropriate config creator based on run type.

    Args:
        args: Command-line arguments. If args[0] is 'api', 'model', or 'pytest',
            uses that config type directly. Otherwise prompts the user.

    Raises:
        OasisAlpacaConfigError: If user enters an invalid config type when prompted.
    """
    if len(args) > 0:
        if args[0].lower() in CONFIGS:
            return create_config(*CONFIGS[args[0].lower()])
    print_alpaca()
    print("Welcome to Alpaca! This script will create alpaca config you can use to run your instance.\n")
    direction = input("Is this for API, Model or Pytest?\n").lower()
    if direction not in CONFIGS:
        raise OasisAlpacaConfigError("Must be for either API, Model or Pytest")
    return create_config(*CONFIGS[direction])
