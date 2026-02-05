"""Interactive configuration file generator for Alpaca."""
import json


SAVE_PATH = "./myalpacaconfig.json"


def create_config(required_config, optional_config):
    """Interactively create an Alpaca configuration file.

    Prompts the user for each configuration value, using defaults for required
    fields if no input is provided. Optional fields are only included if a
    value is entered.

    If no save file is given at the end, file is saved to ./myalpacaconfig.json.

    Args:
        required_config: List of (name, description, default) tuples for required keys.
            Users will be prompted with the description and default value.
        optional_config: List of (name, description, default) tuples for optional keys.
            These are only added to the config if the user provides a value.
    """
    config = {}
    for name, description, default in required_config:
        config[name] = input(f"Choose value of {name}: {description}. Defaults to {default}.\n") or default

    for name, description, _ in optional_config:
        value = input(f"Choose value of {name}: {description}. Optional.\n")
        if value:
            config[name] = value

    path = input(f"Where do you want this config saved? Default is {SAVE_PATH}") or SAVE_PATH
    config = json.dumps(config, indent=4, sort_keys=True)
    try:
        with open(path, "w") as file:
            file.write(config)
    except Exception:
        print(f"Unable to save to path {path}. Saving to {SAVE_PATH}\n")
        with open(SAVE_PATH, "w") as file:
            file.write(config)
