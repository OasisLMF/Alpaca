from alpaca.model.main import main as model_main
from alpaca.pytest.main import main as pytest_main
from alpaca.api.main import main as api_main

HELP_ARGS = {'h', '-h', 'help', '-help', '--help'}


def run_model(args):
    """ Starts model alpaca instance with args[0] as config file """
    if len(args) == 0 or args[0] in HELP_ARGS:
        print("Usage: 'alpaca model <config.json>'")
    else:
        model_main(args[0])


def run_pytest(args):
    """ Starts pytest alpaca instance with args[0] as config file """
    if len(args) == 0 or args[0] in HELP_ARGS:
        print("Usage: 'alpaca pytest <config.json>'")
    else:
        pytest_main(args[0])


def run_api(args):
    """ Starts api alpaca instance with args[0] as config file """
    if len(args) == 0 or args[0] in HELP_ARGS:
        print("Usage: 'alpaca api <config.json>'")
    else:
        api_main(args[0])
