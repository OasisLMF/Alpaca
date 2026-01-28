import json


SAVE_PATH = "./myalpacaconfig.json"


def create_config(required_config, optional_config):
    """ Prompts user to fill in data for required and optional config to create a json config """
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
        with (SAVE_PATH, "w") as file:
            file.write(config)
