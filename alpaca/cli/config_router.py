from alpaca.api.utils import create_api_config
from alpaca.model.utils import create_model_config
from alpaca.pytest.utils import create_pytest_config
from alpaca.exceptions import OasisAlpacaConfigError
from alpaca.cli.images import print_alpaca


ROUTING = {
    'api': create_api_config,
    'model': create_model_config,
    'pytest': create_pytest_config
}


def create_config_router(args=None):
    if len(args) > 0:
        if args[0] in ROUTING:
            return ROUTING[args[0]]()
    print_alpaca()
    print("Welcome to Alpaca! This script will create alpaca config you can use to run your instance.\n")
    direction = input("Is this for API, Model or Pytest?\n").lower()
    if direction not in ROUTING:
        raise OasisAlpacaConfigError("Must be for either API, Model or Pytest")
    ROUTING[direction]()
