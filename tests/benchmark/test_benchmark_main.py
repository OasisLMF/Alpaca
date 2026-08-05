from alpaca.benchmark.main import main
from alpaca.exceptions import OasisAlpacaConfigError
from pathlib import Path

import logging
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


def test_main_prints_benchmark_plan(tmp_path, capsys):
    """Test that main prints the benchmark plan in the documented format."""
    config_path = tmp_path / "benchmark.json"
    config_path.write_text(json.dumps({
        "AMI_ID": "id",
        "SECURITY_GROUP_ID": "group id",
        "SUBNET_ID": "mr subnet",
        "IAM_INSTANCE_PROFILE": "profile",
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "PATH_TO_OASISLMF_JSON": "./oasislmf.json",
        "OASISLMF_VERSION": "2.4.9",
        "OASISLMF_VERSION_COMPARISON": "2.3.3",
    }))

    main(config_path)

    assert capsys.readouterr().out == (
        "Benchmark configuration loaded\n"
        "\n"
        "Models:\n"
        "- PiWind\n"
        "\n"
        "Comparison:\n"
        "- OasisLMF 2.4.9\n"
        "- OasisLMF 2.3.3\n"
        "\n"
        "Execution mode:\n"
        "parallel\n"
    )


def test_main_builds_and_logs_execution_plan(tmp_path, caplog):
    """Test that main builds the baseline/comparison execution plan and logs it."""
    config_path = tmp_path / "benchmark.json"
    config_path.write_text(json.dumps({
        "AMI_ID": "id",
        "SECURITY_GROUP_ID": "group id",
        "SUBNET_ID": "mr subnet",
        "IAM_INSTANCE_PROFILE": "profile",
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "PATH_TO_OASISLMF_JSON": "./oasislmf.json",
        "OASISLMF_VERSION": "2.3.3",
        "OASISLMF_VERSION_COMPARISON": "2.4.9",
    }))

    with caplog.at_level(logging.DEBUG, logger="alpaca.benchmark.main"):
        main(config_path)

    assert "{'baseline': {'version': '2.3.3'}, 'comparison': {'version': '2.4.9'}}" in caplog.text


def test_main_raises_on_invalid_execution_mode(tmp_path):
    """Test that an EXECUTION_MODE outside 'parallel'/'sequential' is rejected."""
    config_path = tmp_path / "benchmark.json"
    config_path.write_text(json.dumps({
        "AMI_ID": "id",
        "SECURITY_GROUP_ID": "group id",
        "SUBNET_ID": "mr subnet",
        "IAM_INSTANCE_PROFILE": "profile",
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "PATH_TO_OASISLMF_JSON": "./oasislmf.json",
        "EXECUTION_MODE": "sideways",
    }))

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)
