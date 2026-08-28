from alpaca.config import create_config, load_config, parse_config_value, parse_list_value
from alpaca.exceptions import OasisAlpacaConfigError
from alpaca.inputs import (AMI_ID, AWS_REGION, DEBUG, OASISLMF_VERSIONS, REPO_LOCATION, REPO_LOCATIONS, SECURITY_GROUP_ID, DISK_GB)
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
            assert str(REQUIRED_CONFIG[i][2]) in calls[i][0][0]
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


def test_parse_config_value_follows_the_declared_default():
    """An input declares its type by the type of its default in alpaca.inputs."""
    assert parse_config_value("OASISLMF_VERSIONS", "2.5.6", OASISLMF_VERSIONS[2]) == ["2.5.6"]
    assert parse_config_value("DISK_GB", "50", DISK_GB[2]) == 50
    assert parse_config_value("DEBUG", "True", DEBUG[2]) is True
    assert parse_config_value("AMI_ID", "ami-123", AMI_ID[2]) == "ami-123"


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


def test_load_config_leaves_an_absent_list_key_absent(tmp_path):
    """Absent means absent whatever the type, so callers keep their own 'or []' fallback."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}))

    config = load_config(config_path, [], [OASISLMF_VERSIONS])

    assert "OASISLMF_VERSIONS" not in config


def test_parse_config_value_reads_a_number_from_a_number_or_text():
    """Environment variables and typed input can only carry text, not a real number."""
    assert parse_config_value("DISK_GB", 50, 100) == 50
    assert parse_config_value("DISK_GB", "50", 100) == 50


def test_parse_config_value_raises_on_a_non_number():
    with pytest.raises(OasisAlpacaConfigError):
        parse_config_value("DISK_GB", "fifty", 100)
    with pytest.raises(OasisAlpacaConfigError):
        parse_config_value("DISK_GB", None, 100)


def test_parse_config_value_reads_a_fractional_number():
    """COMPARISON_TOLERANCE is a float, and '1e-6' is text until it is parsed."""
    assert parse_config_value("COMPARISON_TOLERANCE", "1e-6", 1e-6) == 1e-6
    assert parse_config_value("COMPARISON_TOLERANCE", "0.01", 1e-6) == 0.01
    assert parse_config_value("COMPARISON_TOLERANCE", 0.01, 1e-6) == 0.01


def test_parse_config_value_raises_on_a_non_numeric_float():
    with pytest.raises(OasisAlpacaConfigError):
        parse_config_value("COMPARISON_TOLERANCE", "not-a-number", 1e-6)


def test_parse_config_value_reads_text_as_text():
    """A text key with a number in it stays usable as text rather than becoming a number."""
    assert parse_config_value("EC2_NAME", 12345, "Alpaca") == "12345"
    assert parse_config_value("EC2_NAME", "Alpaca", "Alpaca") == "Alpaca"


def test_parse_config_value_keeps_a_null_text_value_as_nothing():
    """'AWS_PROFILE': null means no profile, and the string 'None' would be a profile name."""
    assert parse_config_value("AWS_PROFILE", None, "") is None


def test_parse_config_value_reads_a_switch_from_a_bool_or_text():
    for value in [True, "True", "true", "TRUE"]:
        assert parse_config_value("DEBUG", value, False) is True


def test_parse_config_value_treats_anything_else_as_a_switch_being_off():
    """'no' plainly means no, and an absent switch reads as off rather than as an error."""
    for value in [False, "False", "false", "no", "", None]:
        assert parse_config_value("DEBUG", value, False) is False


def test_parse_config_value_reads_a_switch_before_a_number():
    """Booleans subclass int, so a switch would otherwise be read as a number."""
    assert parse_config_value("DEBUG", "True", False) is True
    assert parse_config_value("DEBUG", "not a number", False) is False


def test_load_config_parses_an_int_key_from_the_file(tmp_path):
    """A string in the file would otherwise reach boto3, which rejects a string volume size."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"DISK_GB": "50"}))

    config = load_config(config_path, [], [DISK_GB])

    assert config["DISK_GB"] == 50


def test_load_config_parses_an_int_key_from_the_environment(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}))

    with mock.patch.dict(os.environ, {"ALPACA_DISK_GB": "200"}):
        config = load_config(config_path, [], [DISK_GB])

    assert config["DISK_GB"] == 200


def test_load_config_leaves_an_absent_int_key_absent(tmp_path):
    """Unlike a list key, an absent number is left out so callers keep their own default."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}))

    config = load_config(config_path, [], [DISK_GB])

    assert "DISK_GB" not in config


def test_load_config_raises_on_an_unparseable_int_key(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"DISK_GB": "fifty"}))

    with pytest.raises(OasisAlpacaConfigError):
        load_config(config_path, [], [DISK_GB])


def test_load_config_accepts_a_dict(tmp_path):
    """A benchmark target's config is built in memory rather than written to disk first."""
    config = load_config({"DISK_GB": "50"}, [], [DISK_GB])

    assert config["DISK_GB"] == 50


def test_load_config_does_not_mutate_a_given_dict():
    original = {"DISK_GB": "50"}

    load_config(original, [], [DISK_GB])

    assert original == {"DISK_GB": "50"}


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
