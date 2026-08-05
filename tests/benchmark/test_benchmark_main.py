from alpaca.benchmark.main import main
from alpaca.exceptions import OasisAlpacaConfigError
from pathlib import Path

import pytest
import json


CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def test_main_returns_valid_config(tmp_path):
    """Test that a config with every required benchmark key is loaded and returned."""
    config_path = tmp_path / "benchmark.json"
    config_path.write_text(json.dumps({
        "AMI_ID": "id",
        "SECURITY_GROUP_ID": "group id",
        "SUBNET_ID": "mr subnet",
        "IAM_INSTANCE_PROFILE": "profile",
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "PATH_TO_OASISLMF_JSON": "./oasislmf.json",
    }))

    config = main(config_path)

    assert config["REPO_LOCATION_COMPARISON"] == "https://github.com/OasisLMF/OasisPiWind"


def test_main_raises_on_missing_comparison_repo(tmp_path):
    """Test that a benchmark config missing REPO_LOCATION_COMPARISON is rejected."""
    config_path = tmp_path / "benchmark.json"
    config_path.write_text(json.dumps({
        "AMI_ID": "id",
        "SECURITY_GROUP_ID": "group id",
        "SUBNET_ID": "mr subnet",
        "IAM_INSTANCE_PROFILE": "profile",
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "PATH_TO_OASISLMF_JSON": "./oasislmf.json",
    }))

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)


def test_main_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        main("not/a/real/path.json")


def test_main_raises_on_generic_config_missing_benchmark_keys():
    """The shared tests/config.json fixture has no benchmark-specific keys, so it should fail."""
    with pytest.raises(OasisAlpacaConfigError):
        main(CONFIG_PATH)
