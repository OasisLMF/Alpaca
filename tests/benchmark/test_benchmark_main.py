from alpaca.benchmark.main import main
from alpaca.exceptions import OasisAlpacaConfigError
from pathlib import Path
from unittest import mock

import logging
import pytest
import json


CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def _write_config(tmp_path, overrides=None):
    config = {
        "AMI_ID": "id",
        "SECURITY_GROUP_ID": "group id",
        "SUBNET_ID": "mr subnet",
        "IAM_INSTANCE_PROFILE": "profile",
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "PATH_TO_OASISLMF_JSON": "./oasislmf.json",
        "OASISLMF_VERSION": "2.3.3",
        "OASISLMF_VERSION_COMPARISON": "2.4.9",
        "EXECUTION_MODE": "sequential",
        **(overrides or {}),
    }
    config_path = tmp_path / "benchmark.json"
    config_path.write_text(json.dumps(config))
    return config_path


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_returns_structured_results_for_both_targets(mock_model_main, tmp_path):
    """Test that main runs both targets (reusing model_main) and returns their results."""
    config_path = _write_config(tmp_path)

    results = main(config_path)

    assert mock_model_main.call_count == 2
    assert sorted(results, key=lambda r: r["version"]) == [
        {"model": "PiWind", "version": "2.3.3", "status": "success", "runtime_seconds": mock.ANY},
        {"model": "PiWind", "version": "2.4.9", "status": "success", "runtime_seconds": mock.ANY},
    ]


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_passes_distinct_versions_to_each_target(mock_model_main, tmp_path):
    """Test that the baseline and comparison targets each get their own OASISLMF_VERSION."""
    config_path = _write_config(tmp_path)

    main(config_path)

    versions_called = {call.args[0]["OASISLMF_VERSION"] for call in mock_model_main.call_args_list}
    assert versions_called == {"2.3.3", "2.4.9"}


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_marks_target_failed_when_model_main_raises(mock_model_main, tmp_path):
    """Test that a target whose model_main call raises is reported as failed, not propagated."""
    mock_model_main.side_effect = [None, RuntimeError("boom")]
    config_path = _write_config(tmp_path)

    results = main(config_path)

    statuses = sorted(r["status"] for r in results)
    assert statuses == ["failed", "success"]


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


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_prints_benchmark_plan(mock_model_main, tmp_path, capsys):
    """Test that main prints the benchmark plan in the documented format."""
    config_path = _write_config(tmp_path, {"EXECUTION_MODE": "parallel"})

    main(config_path)

    assert capsys.readouterr().out == (
        "Benchmark configuration loaded\n"
        "\n"
        "Models:\n"
        "- PiWind\n"
        "\n"
        "Comparison:\n"
        "- OasisLMF 2.3.3\n"
        "- OasisLMF 2.4.9\n"
        "\n"
        "Execution mode:\n"
        "parallel\n"
    )


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_builds_and_logs_execution_plan(mock_model_main, tmp_path, caplog):
    """Test that main builds the baseline/comparison execution plan and logs it."""
    config_path = _write_config(tmp_path)

    with caplog.at_level(logging.DEBUG, logger="alpaca.benchmark.main"):
        main(config_path)

    assert "{'baseline': {'version': '2.3.3'}, 'comparison': {'version': '2.4.9'}}" in caplog.text


def test_main_raises_on_invalid_execution_mode(tmp_path):
    """Test that an EXECUTION_MODE outside 'parallel'/'sequential' is rejected."""
    config_path = _write_config(tmp_path, {"EXECUTION_MODE": "sideways"})

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)
