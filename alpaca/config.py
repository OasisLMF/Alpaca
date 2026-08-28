"""Configuration file generation and loading for Alpaca."""
import json
import logging
import os

from alpaca.exceptions import OasisAlpacaConfigError


logger = logging.getLogger(__name__)

SAVE_PATH = "./myalpacaconfig.json"


def parse_config_value(key, value, default):
    """Coerce one config value to the type its input declares in alpaca.inputs.

    A JSON config file can carry a real list, number or boolean, while an environment
    variable and an interactive answer can only carry text, so a value arrives in either
    shape and is typed here. The declared default is what says which type is wanted: a list
    default means a list of strings, a boolean default a switch, an integer default a whole
    number, a float default any number, and anything else text.

    Every declared type is covered, so nothing downstream needs to convert a config value
    again: a caller can rely on the type of what it reads out of a loaded config.

    Booleans are checked before integers, as bool is a subclass of int and a switch would
    otherwise be read as a number.

    Args:
        key: Name of the config key, for error messages.
        value: The raw value, as read from a config file, an environment variable or input().
        default: The default from the key's (name, description, default) input tuple.

    Returns:
        The value as a list, a bool, an int, a float or a string. A switch is only on when
        the value reads 'True' in any case, or is a JSON true, so anything else (including
        nothing at all) reads as off rather than as an error, since 'DEBUG': 'no' plainly
        means no. A JSON null against a text key stays None rather than becoming the string
        'None', so a key written as null is still falsy to the 'config.get(key) or default'
        the text keys are read with.

    Raises:
        OasisAlpacaConfigError: If a list key holds a non-string entry, or a numeric key
            holds something that isn't a number.
    """
    if isinstance(default, list):
        return parse_list_value(key, value)
    if isinstance(default, bool):
        return str(value).lower() == "true"
    if isinstance(default, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            raise OasisAlpacaConfigError(f"{key} must be a whole number, got '{value}'")
    if isinstance(default, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            raise OasisAlpacaConfigError(f"{key} must be a number, got '{value}'")
    return value if value is None else str(value)


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
        config[name] = parse_config_value(name, value, default)

    for name, description, default in optional_config:
        value = input(f"Choose value of {name}: {description}. Optional.\n")
        if value:
            config[name] = parse_config_value(name, value, default)

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
    """Load and validate an Alpaca configuration. JSON config always takes priority.

    This is the one place configuration is assembled, for every run type and whether it came
    from a file on disk or was built in memory, so that the file/environment precedence and
    the type coercion are the same everywhere.

    Args:
        config_file: Path to the JSON configuration file, or an already-loaded config dict
            (e.g. one built for a single benchmark target rather than saved to disk). A dict
            is copied rather than modified in place.
        required_config: List of (key, description, default) tuples for required keys.
            If a required key is missing from the config file, it will be read from
            the environment variable ALPACA_{key}. Raises error if still not found.
        optional_config: List of (key, description, default) tuples for optional keys.
            These are loaded from environment variables if not present in config file.

    Returns:
        dict: The loaded and validated configuration, with every declared key that is present
            coerced to the type its default declares (see parse_config_value), so nothing
            downstream has to coerce a config value again. A key absent from both the config
            and the environment is left absent rather than filled in from its declared
            default, so callers keep their own fallbacks.

    Raises:
        OasisAlpacaConfigError: If a required key is missing from both file and environment,
            if a list key holds a non-string entry, or if an integer key holds something
            other than a whole number.
    """
    if isinstance(config_file, dict):
        config = dict(config_file)
    else:
        with open(config_file, 'r') as f:
            config = json.load(f)

    # 1- ensure required is here
    for (key, _, _) in required_config:
        if key not in config:
            value = os.environ.get(f"ALPACA_{key}")
            if not value:
                raise OasisAlpacaConfigError(f"Missing required key {key} from alpaca config")
            logger.info(f"Config {key} taken from environment")
            config[key] = value

    # 2- add optionals from environment
    for (key, _, _) in optional_config:
        if key not in config and os.environ.get(f"ALPACA_{key}"):
            logger.info(f"Config {key} taken from environment")
            config[key] = os.environ[f"ALPACA_{key}"]

    # 3- make sure all values are typed correctly
    for (key, _, default) in [*required_config, *optional_config]:
        if key in config:
            config[key] = parse_config_value(key, config.get(key), default)

    return config
