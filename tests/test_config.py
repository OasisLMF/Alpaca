from alpaca.config import create_config, load_config
from alpaca.exceptions import OasisAlpacaConfigError
from alpaca.inputs import (AMI_ID, AWS_REGION, REPO_LOCATION, SECURITY_GROUP_ID, DISK_GB)
from unittest import mock
from pathlib import Path
import tempfile
import pytest
import json
import os

REQUIRED_CONFIG = [AMI_ID, AWS_REGION, DISK_GB]
OPTIONAL_CONFIG = [REPO_LOCATION, SECURITY_GROUP_ID]
CONFIG_PATH = Path(__file__).parent / "config.json"


@mock.patch("alpaca.config.input", create=True)
def test_create_config(mock_input):
    mock_input.side_effect = ["hello", "world", "", "goodbye", "", ""]
    expected_config = {
        AMI_ID[0]: "hello",
        AWS_REGION[0]: "world",
        DISK_GB[0]: DISK_GB[2],
        REPO_LOCATION[0]: "goodbye"
    }
    cwd = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            create_config(REQUIRED_CONFIG, OPTIONAL_CONFIG)
            path = Path(d) / "myalpacaconfig.json"
            with open(path, "r") as f:
                config = json.load(f)
            assert config == expected_config
        # Testing input messages
        calls = mock_input.call_args_list
        assert len(calls) == 6
        for i in range(len(REQUIRED_CONFIG)):
            assert REQUIRED_CONFIG[i][0] in calls[i][0][0]
            assert REQUIRED_CONFIG[i][1] in calls[i][0][0]
            assert REQUIRED_CONFIG[i][2] in calls[i][0][0]
        for j in range(len(OPTIONAL_CONFIG)):
            assert OPTIONAL_CONFIG[j][0] in calls[i + j + 1][0][0]
            assert OPTIONAL_CONFIG[j][1] in calls[i + j + 1][0][0]
            assert "optional" in calls[i + j + 1][0][0].lower()
    finally:
        os.chdir(cwd)


def test_load_config_returns_config():
    with open(CONFIG_PATH, "r") as f:
        expected = json.load(f)
    assert load_config(CONFIG_PATH, [], []) == expected


def test_load_config_raises_on_missing_required_key():
    with pytest.raises(OasisAlpacaConfigError):
        load_config(CONFIG_PATH, [("missing_config", "", "")], [])


def test_load_config_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("fake/config/path", [], [])


@mock.patch("alpaca.config.os")
def test_load_config_uses_environment(mock_os):
    mock_os.environ = {
        "ALPACA_1": "2",
        "ALPACA_3": "4",
        "ALPACA_SUBNET_ID": "should not override config"
    }
    config = load_config(CONFIG_PATH, [("1", "", ""), ("SUBNET_ID", "", "")], [("3", "", "")])
    assert config["1"] == "2"
    assert config["3"] == "4"
    assert config["SUBNET_ID"] != "should not override config"
