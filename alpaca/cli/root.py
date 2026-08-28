import sys
from alpaca.cli.images import print_alpaca
from alpaca.cli.run_start import HELP_ARGS, run_model, run_api, run_pytest, run_benchmark
from alpaca.cli.config_router import create_config_router

from importlib.metadata import PackageNotFoundError, version

import logging


def main():
    """Main entry point for the Alpaca CLI. Goes to subcommand of first input or help if none given."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = sys.argv
    if len(args) == 1:
        alpaca_help()
    elif args[1] in ALPACA_COMMANDS:
        ALPACA_COMMANDS[args[1]](args[2:])
    elif args[1] in HELP_ARGS:
        alpaca_help()
    else:
        print(f"Command {args[1]} not found. Try 'alpaca' for all args.")


def alpaca_help(args=None):
    """Display help information and list available commands."""
    print_alpaca()
    print("Tool designed to allow OasisLMF runs to be made on EC2. All subcommands:")
    for key in ALPACA_COMMANDS.keys():
        print(key)


def alpaca_version(args=None):
    """Display the installed version of Alpaca."""
    try:
        print(version("Alpaca"))
    except PackageNotFoundError:
        print("Alpaca is not installed as a package, so its version is unknown. Try 'pip install -e .'")


ALPACA_COMMANDS = {
    "help": alpaca_help,
    "model": run_model,
    "create-config": create_config_router,
    "pytest": run_pytest,
    "api": run_api,
    "benchmark": run_benchmark,
    "version": alpaca_version
}


if __name__ == "__main__":
    main()
