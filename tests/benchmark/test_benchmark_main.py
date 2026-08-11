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
        # Default RESULT_DIRECTORY into tmp_path so main()'s report-writing step never
        # touches the real working directory during a test.
        "RESULT_DIRECTORY": str(tmp_path / "runs"),
        **(overrides or {}),
    }
    config_path = tmp_path / "benchmark.json"
    config_path.write_text(json.dumps(config))
    return config_path


def _write_output_files(directory, files):
    output_dir = Path(directory) / "output"
    output_dir.mkdir(parents=True)
    for name, content in files.items():
        (output_dir / name).write_text(content)


@mock.patch("alpaca.benchmark.main.build_comparison_report")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_returns_structured_results_for_both_targets(mock_model_main, mock_build_comparison, tmp_path):
    """Test that main runs both targets (reusing model_main) and returns their results."""
    mock_build_comparison.return_value = {"status": "pass", "different_files": []}
    config_path = _write_config(tmp_path)

    output = main(config_path)

    assert mock_model_main.call_count == 2
    assert sorted(output["results"], key=lambda r: r["version"]) == [
        {
            "model": "PiWind", "version": "2.3.3", "status": "success",
            "runtime_seconds": mock.ANY, "total_runtime_seconds": mock.ANY, "step_timings": {},
        },
        {
            "model": "PiWind", "version": "2.4.9", "status": "success",
            "runtime_seconds": mock.ANY, "total_runtime_seconds": mock.ANY, "step_timings": {},
        },
    ]


@mock.patch("alpaca.benchmark.main.build_comparison_report")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_passes_distinct_versions_to_each_target(mock_model_main, mock_build_comparison, tmp_path):
    """Test that the baseline and comparison targets each get their own OASISLMF_VERSION."""
    mock_build_comparison.return_value = {"status": "pass", "different_files": []}
    config_path = _write_config(tmp_path)

    main(config_path)

    versions_called = {call.args[0]["OASISLMF_VERSION"] for call in mock_model_main.call_args_list}
    assert versions_called == {"2.3.3", "2.4.9"}


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_marks_target_failed_when_model_main_raises(mock_model_main, tmp_path):
    """Test that a target whose model_main call raises is reported as failed, not propagated."""
    mock_model_main.side_effect = [None, RuntimeError("boom")]
    config_path = _write_config(tmp_path)

    output = main(config_path)

    statuses = sorted(r["status"] for r in output["results"])
    assert statuses == ["failed", "success"]


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_skips_comparison_when_a_target_failed(mock_model_main, tmp_path, caplog):
    """Test that comparison is skipped, with a warning, if either target failed."""
    mock_model_main.side_effect = [None, RuntimeError("boom")]
    config_path = _write_config(tmp_path)

    with caplog.at_level(logging.WARNING, logger="alpaca.benchmark.main"):
        output = main(config_path)

    assert output["comparison"] is None
    assert "Skipping result comparison" in caplog.text


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_reports_pass_when_outputs_identical(mock_model_main, tmp_path, capsys):
    """Test that main compares both targets' output directories and reports a pass."""
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "baseline", {"summary.csv": "a,b\n1,2\n"})
    _write_output_files(results_dir / "comparison", {"summary.csv": "a,b\n1,2\n"})
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    assert output["comparison"] == {"status": "pass", "different_files": []}
    assert "PASS:\nOutputs identical" in capsys.readouterr().out


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_reports_fail_when_outputs_differ(mock_model_main, tmp_path, capsys):
    """Test that main reports the differing file names when outputs don't match."""
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "baseline", {"summary.csv": "a,b\n1,2\n"})
    _write_output_files(results_dir / "comparison", {"summary.csv": "a,b\n1,3\n"})
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    assert output["comparison"] == {"status": "fail", "different_files": ["summary.csv"]}
    assert "FAIL:\nFiles different:\n- summary.csv" in capsys.readouterr().out


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_treats_tiny_numeric_differences_as_a_pass(mock_model_main, tmp_path, capsys):
    """Two runs of the same model rarely produce byte-identical loss tables, so a tiny
    numeric difference (well within the default tolerance) should still report a pass.
    """
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "baseline", {"summary.csv": "a,b\n1,2.0000001\n"})
    _write_output_files(results_dir / "comparison", {"summary.csv": "a,b\n1,2.0000002\n"})
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    assert output["comparison"] == {"status": "pass", "different_files": []}
    assert "PASS:\nOutputs identical" in capsys.readouterr().out


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_respects_configured_comparison_tolerance(mock_model_main, tmp_path, capsys):
    """Test that COMPARISON_TOLERANCE from the config reaches the comparison."""
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "baseline", {"summary.csv": "a,b\n1,2.0\n"})
    _write_output_files(results_dir / "comparison", {"summary.csv": "a,b\n1,2.001\n"})
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir), "COMPARISON_TOLERANCE": "0.01"})

    output = main(config_path)

    assert output["comparison"] == {"status": "pass", "different_files": []}


def test_main_raises_on_invalid_comparison_tolerance(tmp_path):
    """Test that an invalid COMPARISON_TOLERANCE is rejected before any target runs."""
    config_path = _write_config(tmp_path, {"COMPARISON_TOLERANCE": "not-a-number"})

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)


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


@mock.patch("alpaca.benchmark.main.build_comparison_report")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_prints_benchmark_plan(mock_model_main, mock_build_comparison, tmp_path, capsys):
    """Test that main prints the benchmark plan in the documented format."""
    mock_build_comparison.return_value = {"status": "pass", "different_files": []}
    config_path = _write_config(tmp_path, {"EXECUTION_MODE": "parallel"})

    main(config_path)

    assert capsys.readouterr().out.startswith(
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


@mock.patch("alpaca.benchmark.main.build_comparison_report")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_builds_and_logs_execution_plan(mock_model_main, mock_build_comparison, tmp_path, caplog):
    """Test that main builds the baseline/comparison execution plan and logs it."""
    mock_build_comparison.return_value = {"status": "pass", "different_files": []}
    config_path = _write_config(tmp_path)

    with caplog.at_level(logging.DEBUG, logger="alpaca.benchmark.main"):
        main(config_path)

    assert "{'baseline': {'version': '2.3.3'}, 'comparison': {'version': '2.4.9'}}" in caplog.text


def test_main_raises_on_invalid_execution_mode(tmp_path):
    """Test that an EXECUTION_MODE outside 'parallel'/'sequential' is rejected."""
    config_path = _write_config(tmp_path, {"EXECUTION_MODE": "sideways"})

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)


@mock.patch("alpaca.benchmark.main.build_comparison_report")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_writes_report_file_alongside_result_directories(mock_model_main, mock_build_comparison, tmp_path):
    """Test that main saves the printed report to a file next to the targets' results,
    so it's still available for review after the terminal output has scrolled away.
    """
    mock_build_comparison.return_value = {"status": "pass", "different_files": []}
    results_dir = tmp_path / "results"
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    report_path = output["report_path"]
    assert report_path == results_dir / "benchmark_report.txt"
    assert "Benchmark Report" in report_path.read_text()


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_report_includes_timing_comparison_when_both_targets_succeed(mock_model_main, tmp_path, capsys):
    """Test that the report includes a step-by-step timing table sourced from each
    target's result.txt, not just the pass/fail output comparison.
    """
    results_dir = tmp_path / "results"

    def make_result_file(target, seconds):
        result_file = results_dir / target / "losses-x" / "runs" / "result.txt"
        result_file.parent.mkdir(parents=True)
        result_file.write_text(f"COMPLETED: oasislmf.manager.interface in {seconds}s\n")
        _write_output_files(results_dir / target, {"summary.csv": "a,b\n1,2\n"})

    make_result_file("baseline", "210.50")
    make_result_file("comparison", "165.75")
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    report_text = output["report_path"].read_text()
    assert "Timing comparison (2.3.3 vs 2.4.9):" in report_text
    assert "oasislmf.manager.interface" in report_text
    assert "210.50" in report_text
    assert "165.75" in report_text
    assert capsys.readouterr().out.count("Timing comparison") == 1


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_report_notes_comparison_skipped_when_a_target_failed(mock_model_main, tmp_path):
    """Test that the saved report explains why comparison/timing sections are absent,
    rather than silently omitting them.
    """
    mock_model_main.side_effect = [None, RuntimeError("boom")]
    config_path = _write_config(tmp_path)

    output = main(config_path)

    report_text = output["report_path"].read_text()
    assert "Output comparison skipped" in report_text
    assert "Timing comparison" not in report_text
