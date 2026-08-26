from alpaca.config import create_config, is_list_input, load_config, parse_list_value
from alpaca.exceptions import OasisAlpacaConfigError
from alpaca.inputs import (AMI_ID, AWS_REGION, OASISLMF_VERSIONS, REPO_LOCATION, REPO_LOCATIONS, SECURITY_GROUP_ID, DISK_GB)
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


def test_is_list_input_follows_the_default_value():
    """An input declares that it takes a list by having a list default."""
    assert is_list_input(OASISLMF_VERSIONS[2])
    assert not is_list_input(AMI_ID[2])


def test_parse_list_value_reads_a_json_array():
    assert parse_list_value("OASISLMF_VERSIONS", ["2.5.6", "2.4.9"]) == ["2.5.6", "2.4.9"]


def test_parse_list_value_reads_a_json_array_from_text():
    """Environment variables and typed input can only carry text, not a real array."""
    assert parse_list_value("OASISLMF_VERSIONS", '["2.5.6", "2.4.9"]') == ["2.5.6", "2.4.9"]


def test_parse_list_value_wraps_a_single_value():
    assert parse_list_value("OASISLMF_VERSIONS", "2.5.6") == ["2.5.6"]


def test_parse_list_value_wraps_a_single_value_that_parses_as_json():
    """'2' is valid JSON, but it's still one version rather than a list of them."""
    assert parse_list_value("OASISLMF_VERSIONS", "2") == ["2"]


def test_parse_list_value_treats_nothing_as_no_entries():
    assert parse_list_value("OASISLMF_VERSIONS", None) == []
    assert parse_list_value("OASISLMF_VERSIONS", "") == []
    assert parse_list_value("OASISLMF_VERSIONS", []) == []


def test_parse_list_value_keeps_a_single_entry_list():
    assert parse_list_value("OASISLMF_VERSIONS", ["2.5.6"]) == ["2.5.6"]
    assert parse_list_value("OASISLMF_VERSIONS", '["2.5.6"]') == ["2.5.6"]


def test_parse_list_value_drops_blank_entries():
    """A blank entry would otherwise reach a benchmark as a nameless version or location."""
    assert parse_list_value("OASISLMF_VERSIONS", ["", "2.5.6", "   "]) == ["2.5.6"]


def test_parse_list_value_strips_surrounding_whitespace():
    assert parse_list_value("OASISLMF_VERSIONS", '["2.5.6 ", " 2.4.9"]') == ["2.5.6", "2.4.9"]


def test_parse_list_value_treats_a_blank_single_value_as_no_entries():
    assert parse_list_value("OASISLMF_VERSIONS", "   ") == []


def test_parse_list_value_raises_on_non_string_entries():
    with pytest.raises(OasisAlpacaConfigError):
        parse_list_value("OASISLMF_VERSIONS", [2.5, 2.4])


def test_parse_list_value_raises_on_a_nested_list():
    with pytest.raises(OasisAlpacaConfigError):
        parse_list_value("OASISLMF_VERSIONS", '[["2.5.6"]]')


def test_parse_list_value_raises_on_a_bare_number():
    """A JSON number is a value, not text, so it can't be a version or a location."""
    with pytest.raises(OasisAlpacaConfigError):
        parse_list_value("OASISLMF_VERSIONS", 3)


def test_load_config_reads_a_list_key_from_the_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"OASISLMF_VERSIONS": ["2.5.6", "2.4.9"]}))

    config = load_config(config_path, [], [OASISLMF_VERSIONS])

    assert config["OASISLMF_VERSIONS"] == ["2.5.6", "2.4.9"]


def test_load_config_wraps_a_single_value_given_to_a_list_key(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"OASISLMF_VERSIONS": "2.5.6"}))

    config = load_config(config_path, [], [OASISLMF_VERSIONS])

    assert config["OASISLMF_VERSIONS"] == ["2.5.6"]


def test_load_config_defaults_an_absent_list_key_to_no_entries(tmp_path):
    """A list key is always a list once loaded, so callers never have to guard for None."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}))

    config = load_config(config_path, [], [OASISLMF_VERSIONS])

    assert config["OASISLMF_VERSIONS"] == []


def test_load_config_parses_a_list_key_from_the_environment(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}))

    with mock.patch.dict(os.environ, {"ALPACA_OASISLMF_VERSIONS": '["2.5.6", "2.4.9"]'}):
        config = load_config(config_path, [], [OASISLMF_VERSIONS])

    assert config["OASISLMF_VERSIONS"] == ["2.5.6", "2.4.9"]


def test_load_config_prefers_the_file_over_the_environment_for_a_list_key(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"OASISLMF_VERSIONS": ["2.5.6"]}))

    with mock.patch.dict(os.environ, {"ALPACA_OASISLMF_VERSIONS": '["9.9.9"]'}):
        config = load_config(config_path, [], [OASISLMF_VERSIONS])

    assert config["OASISLMF_VERSIONS"] == ["2.5.6"]


def test_load_config_reads_a_required_list_key_from_the_environment(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}))

    with mock.patch.dict(os.environ, {"ALPACA_OASISLMF_VERSIONS": "2.5.6"}):
        config = load_config(config_path, [OASISLMF_VERSIONS], [])

    assert config["OASISLMF_VERSIONS"] == ["2.5.6"]


def test_load_config_still_requires_a_missing_required_list_key(tmp_path):
    """An empty list is not a value: a required list key has to come from somewhere."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}))

    with pytest.raises(OasisAlpacaConfigError):
        load_config(config_path, [OASISLMF_VERSIONS], [])


def test_load_config_raises_on_a_list_key_with_non_string_entries(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"OASISLMF_VERSIONS": [2.5]}))

    with pytest.raises(OasisAlpacaConfigError):
        load_config(config_path, [], [OASISLMF_VERSIONS])


@mock.patch("alpaca.config.input", create=True)
def test_create_config_parses_an_entered_list(mock_input, tmp_path):
    mock_input.side_effect = ['["2.5.6", "2.4.9"]', str(tmp_path / "config.json")]

    create_config([OASISLMF_VERSIONS], [])

    with open(tmp_path / "config.json", "r") as f:
        assert json.load(f) == {"OASISLMF_VERSIONS": ["2.5.6", "2.4.9"]}


@mock.patch("alpaca.config.input", create=True)
def test_create_config_wraps_a_single_entered_value_for_a_list_key(mock_input, tmp_path):
    mock_input.side_effect = ["2.5.6", str(tmp_path / "config.json")]

    create_config([], [OASISLMF_VERSIONS])

    with open(tmp_path / "config.json", "r") as f:
        assert json.load(f) == {"OASISLMF_VERSIONS": ["2.5.6"]}


@mock.patch("alpaca.config.input", create=True)
def test_create_config_falls_back_to_a_required_list_keys_default(mock_input, tmp_path):
    """Entering nothing for a required list key keeps its default, as a list."""
    mock_input.side_effect = ["", str(tmp_path / "config.json")]

    create_config([REPO_LOCATIONS], [])

    with open(tmp_path / "config.json", "r") as f:
        assert json.load(f) == {REPO_LOCATIONS[0]: REPO_LOCATIONS[2]}


@mock.patch("alpaca.config.input", create=True)
def test_create_config_omits_an_optional_list_key_left_blank(mock_input, tmp_path):
    mock_input.side_effect = ["", str(tmp_path / "config.json")]

    create_config([], [OASISLMF_VERSIONS])

    with open(tmp_path / "config.json", "r") as f:
        assert json.load(f) == {}


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
