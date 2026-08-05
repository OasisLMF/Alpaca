"""Interactive configuration file generator for Alpaca."""
import json
import os

from alpaca.exceptions import OasisAlpacaConfigError


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


def load_config(config_file, required_config, optional_config):
    """Load and validate an Alpaca configuration file. JSON config always takes priority.

    Args:
        config_file: Path to the JSON configuration file.
        required_config: List of (key, description, default) tuples for required keys.
            If a required key is missing from the config file, it will be read from
            the environment variable ALPACA_{key}. Raises error if still not found.
        optional_config: List of (key, description, default) tuples for optional keys.
            These are loaded from environment variables if not present in config file.

    Returns:
        dict: The loaded and validated configuration.

    Raises:
        OasisAlpacaConfigError: If a required key is missing from both file and environment.
    """
    with open(config_file, 'r') as f:
        config = json.load(f)
    for (key, _, _) in required_config:
        if key not in config:
            if f"ALPACA_{key}" in os.environ:
                config[key] = os.environ[f"ALPACA_{key}"]
            else:
                raise OasisAlpacaConfigError(f"Missing required key {key} from alpaca config")
    for (key, _, _) in optional_config:
        if key not in config and f"ALPACA_{key}" in os.environ:
            config[key] = os.environ[f"ALPACA_{key}"]
    return config
