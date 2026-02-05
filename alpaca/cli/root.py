import sys
from alpaca.cli.images import print_alpaca
from alpaca.cli.run_start import run_model, run_api, run_pytest
from alpaca.cli.config_router import create_config_router

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    """Main entry point for the Alpaca CLI. Goes to subcommand of first input or help if none given"""
    args = sys.argv
    if len(args) == 1:
        alpaca_help()
    elif args[1] in ALPACA_COMMANDS:
        ALPACA_COMMANDS[args[1]](args[2:])
    else:
        print(f"Command {args[1]} not found. Try 'alpaca' for all args.")


def alpaca_help(args=None):
    """Display help information and list available commands."""
    print_alpaca()
    print("Tool designed to allow OasisLMF runs to be made on EC2. All subcommands:")
    for key in ALPACA_COMMANDS.keys():
        print(key)


ALPACA_COMMANDS = {
    "help": alpaca_help,
    "model": run_model,
    "create-config": create_config_router,
    "pytest": run_pytest,
    "api": run_api
}


if __name__ == "__main__":
    main()
