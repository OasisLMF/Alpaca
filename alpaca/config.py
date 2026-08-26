"""Interactive configuration file generator for Alpaca."""
import json
import os

from alpaca.exceptions import OasisAlpacaConfigError


SAVE_PATH = "./myalpacaconfig.json"


def is_list_input(default):
    """Report whether a config input holds a list of values rather than a single one.

    Args:
        default: The default value from an (name, description, default) input tuple.

    Returns:
        bool: True if this input's values are lists, which is declared by giving it a list
            default in alpaca.inputs.
    """
    return isinstance(default, list)


def parse_list_value(key, value):
    """Parse a list-valued config entry into a list of strings.

    A JSON config file can hold a real array, while environment variables and interactive
    input can only hold text, so a string is parsed as JSON first. Anything that isn't an
    array is taken as a single entry, so one value can be given without brackets, and
    nothing at all as no entries. Entries are stripped of surrounding whitespace, and blank
    ones are dropped rather than passed on as a nameless version, branch or location.

    Args:
        key: Name of the config key, for error messages.
        value: The raw value: a list, a JSON array string, a single value, or nothing.

    Returns:
        list[str]: The parsed entries, empty when no value was given.

    Raises:
        OasisAlpacaConfigError: If any entry isn't a string.
    """
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
        value = parsed if isinstance(parsed, list) else [value]
    if not isinstance(value, list):
        value = [value]
    if not all(isinstance(entry, str) for entry in value):
        raise OasisAlpacaConfigError(f"Every {key} entry must be a string, got '{value}'")
    return [entry.strip() for entry in value if entry.strip()]


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
        value = input(f"Choose value of {name}: {description}. Defaults to {default}.\n") or default
        config[name] = parse_list_value(name, value) if is_list_input(default) else value

    for name, description, default in optional_config:
        value = input(f"Choose value of {name}: {description}. Optional.\n")
        if value:
            config[name] = parse_list_value(name, value) if is_list_input(default) else value

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
        dict: The loaded and validated configuration. Keys declared with a list default
            (see is_list_input) are always returned as lists, whether they came from a JSON
            array in the file, a JSON array string in the environment, or a single value.

    Raises:
        OasisAlpacaConfigError: If a required key is missing from both file and environment,
            or if a list key holds a non-string entry.
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

    for (key, _, default) in [*required_config, *optional_config]:
        if is_list_input(default):
            config[key] = parse_list_value(key, config.get(key))
    return config
