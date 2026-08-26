from alpaca.benchmark.main import main
from alpaca.exceptions import OasisAlpacaConfigError
from pathlib import Path
from unittest import mock

import logging
import pytest
import json


CONFIG_PATH = Path(__file__).parent.parent / "config.json"
PIWIND = "https://github.com/OasisLMF/OasisPiWind"


def _write_config(tmp_path, overrides=None):
    config = {
        "AMI_ID": "id",
        "SECURITY_GROUP_ID": "group id",
        "SUBNET_ID": "mr subnet",
        "IAM_INSTANCE_PROFILE": "profile",
        "REPO_LOCATIONS": [PIWIND],
        "PATH_TO_OASISLMF_JSON": "./oasislmf.json",
        "OASISLMF_VERSIONS": ["2.3.3", "2.4.9"],
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


@mock.patch("alpaca.benchmark.main.build_comparison_reports")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_returns_structured_results_for_every_target(mock_model_main, mock_build_comparison, tmp_path):
    """Test that main runs every target (reusing model_main) and returns their results."""
    mock_build_comparison.return_value = {"reference": "PiWind 2.3.3", "status": "pass", "comparisons": []}
    config_path = _write_config(tmp_path)

    output = main(config_path)

    assert mock_model_main.call_count == 2
    assert sorted(output["results"], key=lambda r: r["version"]) == [
        {
            "label": "PiWind-2.3.3", "model": "PiWind", "version": "2.3.3", "status": "success",
            "runtime_seconds": mock.ANY, "total_runtime_seconds": mock.ANY, "step_timings": {},
        },
        {
            "label": "PiWind-2.4.9", "model": "PiWind", "version": "2.4.9", "status": "success",
            "runtime_seconds": mock.ANY, "total_runtime_seconds": mock.ANY, "step_timings": {},
        },
    ]


@mock.patch("alpaca.benchmark.main.build_comparison_reports")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_passes_distinct_versions_to_each_target(mock_model_main, mock_build_comparison, tmp_path):
    """Test that every OASISLMF_VERSIONS entry gets its own target."""
    mock_build_comparison.return_value = {"reference": "PiWind 2.3.3", "status": "pass", "comparisons": []}
    config_path = _write_config(tmp_path)

    main(config_path)

    versions_called = {call.args[0]["OASISLMF_VERSION"] for call in mock_model_main.call_args_list}
    assert versions_called == {"2.3.3", "2.4.9"}


@mock.patch("alpaca.benchmark.main.build_comparison_reports")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_runs_a_target_per_version_and_branch(mock_model_main, mock_build_comparison, tmp_path):
    """Test that versions and branches can be benchmarked against each other in one run."""
    mock_build_comparison.return_value = {"reference": "PiWind 2.4.9", "status": "pass", "comparisons": []}
    config_path = _write_config(tmp_path, {"OASISLMF_VERSIONS": ["2.4.9"], "OASISLMF_BRANCHES": ["stable/2.5.x"]})

    output = main(config_path)

    assert mock_model_main.call_count == 2
    assert [result["version"] for result in output["results"]] == ["2.4.9", "branch:stable/2.5.x"]


@mock.patch("alpaca.benchmark.main.build_comparison_reports")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_runs_every_location_at_every_version(mock_model_main, mock_build_comparison, tmp_path):
    """Test that REPO_LOCATIONS multiplies out against the OasisLMF versions."""
    mock_build_comparison.return_value = {"reference": "PiWind 2.3.3", "status": "pass", "comparisons": []}
    config_path = _write_config(tmp_path, {"REPO_LOCATIONS": [PIWIND, "https://github.com/OasisLMF/OasisLeague"]})

    output = main(config_path)

    assert mock_model_main.call_count == 4
    assert [(result["model"], result["version"]) for result in output["results"]] == [
        ("PiWind", "2.3.3"), ("PiWind", "2.4.9"), ("League", "2.3.3"), ("League", "2.4.9"),
    ]


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
    """Test that comparison is skipped, with a warning, when fewer than two targets succeed."""
    mock_model_main.side_effect = [None, RuntimeError("boom")]
    config_path = _write_config(tmp_path)

    with caplog.at_level(logging.WARNING, logger="alpaca.benchmark.main"):
        output = main(config_path)

    assert output["comparison"] is None
    assert "Skipping result comparison" in caplog.text


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_reports_pass_when_outputs_identical(mock_model_main, tmp_path, capsys):
    """Test that main compares every target's output directory and reports a pass."""
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "PiWind-2.3.3", {"summary.csv": "a,b\n1,2\n"})
    _write_output_files(results_dir / "PiWind-2.4.9", {"summary.csv": "a,b\n1,2\n"})
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    assert output["comparison"]["status"] == "pass"
    assert "PASS:\nOutputs identical" in capsys.readouterr().out


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_reports_fail_when_outputs_differ(mock_model_main, tmp_path, capsys):
    """Test that main reports the differing file names when outputs don't match."""
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "PiWind-2.3.3", {"summary.csv": "a,b\n1,2\n"})
    _write_output_files(results_dir / "PiWind-2.4.9", {"summary.csv": "a,b\n1,3\n"})
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    assert output["comparison"]["status"] == "fail"
    assert output["comparison"]["comparisons"][0]["different_files"] == ["summary.csv"]
    assert "FAIL:\nFiles different:\n- summary.csv" in capsys.readouterr().out


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_compares_every_other_target_against_the_fastest(mock_model_main, tmp_path):
    """Test that the fastest run is the reference every other target is diffed against,
    rather than whichever target happens to be configured first.
    """
    results_dir = tmp_path / "results"
    for target, seconds, summary in [
        ("PiWind-2.3.3", "210.5", "a,b\n1,2\n"), ("PiWind-2.4.9", "165.75", "a,b\n1,2\n"), ("PiWind-2.5.6", "300.25", "a,b\n1,3\n"),
    ]:
        result_file = results_dir / target / "losses-x" / "result.txt"
        result_file.parent.mkdir(parents=True)
        result_file.write_text(f"COMPLETED: oasislmf.manager.interface in {seconds}s\n")
        _write_output_files(results_dir / target, {"summary.csv": summary})
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.3.3", "2.4.9", "2.5.6"], "RESULT_DIRECTORY": str(results_dir),
    })

    output = main(config_path)

    assert output["comparison"]["reference"] == "PiWind 2.4.9"
    assert output["comparison"]["comparisons"] == [
        {"target": "PiWind 2.3.3", "status": "pass", "different_files": []},
        {"target": "PiWind 2.5.6", "status": "fail", "different_files": ["summary.csv"]},
    ]


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_still_reports_when_a_targets_output_cannot_be_read(mock_model_main, tmp_path, capsys):
    """A run whose results didn't download leaves nothing to diff, but its timings and the
    other targets' are still worth reporting, so the report isn't lost to an exception.
    """
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "PiWind-2.3.3", {"summary.csv": "a,b\n1,2\n"})
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    assert output["comparison"] is None
    assert "Output comparison skipped: No 'output' directory found" in capsys.readouterr().out
    assert "Benchmark Report" in output["report_path"].read_text()


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_treats_tiny_numeric_differences_as_a_pass(mock_model_main, tmp_path, capsys):
    """Two runs of the same model rarely produce byte-identical loss tables, so a tiny
    numeric difference (well within the default tolerance) should still report a pass.
    """
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "PiWind-2.3.3", {"summary.csv": "a,b\n1,2.0000001\n"})
    _write_output_files(results_dir / "PiWind-2.4.9", {"summary.csv": "a,b\n1,2.0000002\n"})
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    assert output["comparison"]["status"] == "pass"
    assert "PASS:\nOutputs identical" in capsys.readouterr().out


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_respects_configured_comparison_tolerance(mock_model_main, tmp_path, capsys):
    """Test that COMPARISON_TOLERANCE from the config reaches the comparison."""
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "PiWind-2.3.3", {"summary.csv": "a,b\n1,2.0\n"})
    _write_output_files(results_dir / "PiWind-2.4.9", {"summary.csv": "a,b\n1,2.001\n"})
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir), "COMPARISON_TOLERANCE": "0.01"})

    output = main(config_path)

    assert output["comparison"]["status"] == "pass"


def test_main_raises_on_invalid_comparison_tolerance(tmp_path):
    """Test that an invalid COMPARISON_TOLERANCE is rejected before any target runs."""
    config_path = _write_config(tmp_path, {"COMPARISON_TOLERANCE": "not-a-number"})

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_runs_a_single_target_when_only_one_version_is_configured(mock_model_main, tmp_path, capsys):
    """Test that one target still runs, with no comparison and a clear reason (not 'a target
    failed') for why it was skipped.
    """
    config_path = _write_config(tmp_path, {"OASISLMF_VERSIONS": ["2.5.6"]})

    output = main(config_path)

    assert mock_model_main.call_count == 1
    assert [r["version"] for r in output["results"]] == ["2.5.6"]
    assert output["comparison"] is None
    assert "only one target was configured" in capsys.readouterr().out


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_raises_when_no_versions_or_branches_are_configured(mock_model_main, tmp_path):
    """Test that a benchmark with nothing pinned is rejected before any EC2 spend, rather
    than quietly running against whatever PyPI's latest release happens to be.
    """
    config_path = _write_config(tmp_path, {"OASISLMF_VERSIONS": []})

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)

    mock_model_main.assert_not_called()


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_raises_when_no_repo_locations_are_configured(mock_model_main, tmp_path):
    """Test that a benchmark with no model to run is rejected before any EC2 spend."""
    config_path = _write_config(tmp_path, {"REPO_LOCATIONS": []})

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)

    mock_model_main.assert_not_called()


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_runs_a_branch_only_benchmark(mock_model_main, tmp_path):
    """Test that branches alone are enough to benchmark, with no versions configured."""
    config_path = _write_config(tmp_path, {"OASISLMF_VERSIONS": [], "OASISLMF_BRANCHES": ["main", "stable/2.5.x"]})

    output = main(config_path)

    assert mock_model_main.call_count == 2
    assert [r["version"] for r in output["results"]] == ["branch:main", "branch:stable/2.5.x"]
    assert [call.args[0]["OASISLMF_BRANCH"] for call in mock_model_main.call_args_list] == ["main", "stable/2.5.x"]


@mock.patch("alpaca.benchmark.main.upload_baseline")
@mock.patch("alpaca.benchmark.main.download_baseline")
@mock.patch("alpaca.benchmark.main.resolve_stored_versions")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_takes_a_stored_version_from_the_bucket_instead_of_running_it(
    mock_model_main, mock_resolve_stored, mock_download_baseline, mock_upload_baseline, tmp_path, capsys
):
    """Test that a version already held in BENCHMARK_BUCKET is downloaded and compared
    against, rather than being run on EC2 again.
    """
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "PiWind-2.5.6", {"summary.csv": "a,b\n1,2\n"})
    mock_resolve_stored.return_value = {"2.5.4"}

    def fake_download(bucket, version, local_directory, config):
        _write_output_files(local_directory, {"summary.csv": "a,b\n1,2\n"})
        return Path(local_directory)

    mock_download_baseline.side_effect = fake_download
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "RESULT_DIRECTORY": str(results_dir),
    })

    output = main(config_path)

    assert mock_model_main.call_count == 1
    mock_download_baseline.assert_called_once()
    assert mock_download_baseline.call_args.args[0] == "s3://alpaca-benchmark"
    assert mock_download_baseline.call_args.args[1] == "2.5.4"
    mock_upload_baseline.assert_not_called()
    assert output["comparison"]["status"] == "pass"
    assert [r["version"] for r in output["results"]] == ["2.5.6", "2.5.4 (S3 baseline)"]
    assert "PASS:\nOutputs identical" in capsys.readouterr().out


@mock.patch("alpaca.benchmark.main.download_baseline")
@mock.patch("alpaca.benchmark.main.resolve_stored_versions")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_times_a_stored_target_from_its_published_metrics(
    mock_model_main, mock_resolve_stored, mock_download_baseline, tmp_path
):
    """A stored baseline's published performance metrics are read like a live run's, so it
    joins the ranking and the timing table, and can even be the quickest.
    """
    results_dir = tmp_path / "results"
    result_file = results_dir / "PiWind-2.5.6" / "losses-x" / "result.txt"
    result_file.parent.mkdir(parents=True)
    result_file.write_text("COMPLETED: oasislmf.manager.interface in 210.50s\n")
    _write_output_files(results_dir / "PiWind-2.5.6", {"summary.csv": "a,b\n1,2\n"})
    mock_resolve_stored.return_value = {"2.5.4"}

    def fake_download(bucket, version, local_directory, config):
        _write_output_files(local_directory, {"summary.csv": "a,b\n1,2\n"})
        Path(local_directory, "result.txt").write_text("COMPLETED: oasislmf.manager.interface in 165.75s\n")
        return Path(local_directory)

    mock_download_baseline.side_effect = fake_download
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "RESULT_DIRECTORY": str(results_dir),
    })

    output = main(config_path)

    stored_result = output["results"][1]
    assert stored_result["runtime_seconds"] == 166
    assert stored_result["step_timings"] == {"oasislmf.manager.interface": 165.75}
    assert output["comparison"]["reference"] == "PiWind 2.5.4 (S3 baseline)"
    report_text = output["report_path"].read_text()
    assert "- PiWind 2.5.4 (S3 baseline): success (166s)" in report_text
    assert "210.50 (+27.0%)" in report_text


@mock.patch("alpaca.benchmark.main.download_baseline")
@mock.patch("alpaca.benchmark.main.resolve_stored_versions")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_compares_stored_targets_that_have_no_runtimes(
    mock_model_main, mock_resolve_stored, mock_download_baseline, tmp_path, caplog
):
    """Two stored baselines with no recorded runtimes can't be ranked, but their outputs are
    still worth diffing, so the first one stands in as the reference.
    """
    results_dir = tmp_path / "results"
    mock_resolve_stored.return_value = {"2.5.6", "2.5.4"}

    def fake_download(bucket, version, local_directory, config):
        _write_output_files(local_directory, {"summary.csv": "a,b\n1,2\n"})
        return Path(local_directory)

    mock_download_baseline.side_effect = fake_download
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "RESULT_DIRECTORY": str(results_dir),
    })

    with caplog.at_level(logging.WARNING, logger="alpaca.benchmark.main"):
        output = main(config_path)

    assert output["comparison"]["reference"] == "PiWind 2.5.6 (S3 baseline)"
    assert output["comparison"]["status"] == "pass"
    assert "No target reported a runtime" in caplog.text


@mock.patch("alpaca.benchmark.main.download_baseline")
@mock.patch("alpaca.benchmark.main.resolve_stored_versions")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_runs_nothing_when_the_only_version_is_already_stored(
    mock_model_main, mock_resolve_stored, mock_download_baseline, tmp_path, capsys
):
    """A single version that's already in the bucket is a no-op: it's taken from there, so
    there's no run and nothing to compare it against.
    """
    mock_resolve_stored.return_value = {"2.5.6"}
    mock_download_baseline.side_effect = lambda bucket, version, local_directory, config: Path(local_directory)
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6"], "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
    })

    output = main(config_path)

    mock_model_main.assert_not_called()
    assert [r["version"] for r in output["results"]] == ["2.5.6 (S3 baseline)"]
    assert "only one target was configured" in capsys.readouterr().out


@mock.patch("alpaca.benchmark.main.download_baseline")
@mock.patch("alpaca.benchmark.main.resolve_stored_versions")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_runs_nothing_when_every_version_is_already_stored(
    mock_model_main, mock_resolve_stored, mock_download_baseline, tmp_path
):
    """Every target coming from the bucket means no EC2 run at all, which must not trip the
    executor up on having nothing to run.
    """
    results_dir = tmp_path / "results"
    mock_resolve_stored.return_value = {"2.5.6", "2.5.4"}

    def fake_download(bucket, version, local_directory, config):
        _write_output_files(local_directory, {"summary.csv": "a,b\n1,2\n"})
        return Path(local_directory)

    mock_download_baseline.side_effect = fake_download
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "RESULT_DIRECTORY": str(results_dir),
    })

    output = main(config_path)

    mock_model_main.assert_not_called()
    assert mock_download_baseline.call_count == 2
    assert [r["version"] for r in output["results"]] == ["2.5.6 (S3 baseline)", "2.5.4 (S3 baseline)"]


@mock.patch("alpaca.benchmark.main.download_baseline")
@mock.patch("alpaca.benchmark.main.resolve_stored_versions")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_reports_a_stored_target_with_no_recorded_runtime(
    mock_model_main, mock_resolve_stored, mock_download_baseline, tmp_path
):
    """A baseline published before performance metrics were stored still has usable output,
    so it's compared, just never ranked as the quickest.
    """
    results_dir = tmp_path / "results"
    _write_output_files(results_dir / "PiWind-2.5.6", {"summary.csv": "a,b\n1,2\n"})
    mock_resolve_stored.return_value = {"2.5.4"}

    def fake_download(bucket, version, local_directory, config):
        _write_output_files(local_directory, {"summary.csv": "a,b\n1,2\n"})
        return Path(local_directory)

    mock_download_baseline.side_effect = fake_download
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "RESULT_DIRECTORY": str(results_dir),
    })

    output = main(config_path)

    stored_result = output["results"][1]
    assert stored_result["runtime_seconds"] is None
    assert output["comparison"]["reference"] == "PiWind 2.5.6"
    assert "- PiWind 2.5.4 (S3 baseline): success (runtime unknown)" in output["report_path"].read_text()


@mock.patch("alpaca.benchmark.main.upload_baseline")
@mock.patch("alpaca.benchmark.main.download_baseline")
@mock.patch("alpaca.benchmark.main.resolve_stored_versions")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_does_not_republish_a_stored_target(
    mock_model_main, mock_resolve_stored, mock_download_baseline, mock_upload_baseline, tmp_path
):
    """Uploading a baseline straight back to where it was just downloaded from would be
    pointless, and would overwrite it with itself.
    """
    mock_resolve_stored.return_value = {"2.5.4"}
    mock_download_baseline.side_effect = lambda bucket, version, local_directory, config: Path(local_directory)
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "PUBLISH_BASELINE": "True",
    })

    main(config_path)

    assert [call.args[1] for call in mock_upload_baseline.call_args_list] == ["2.5.6"]


@mock.patch("alpaca.benchmark.main.download_baseline")
@mock.patch("alpaca.benchmark.main.resolve_stored_versions")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_marks_a_stored_target_failed_when_the_download_fails(
    mock_model_main, mock_resolve_stored, mock_download_baseline, tmp_path
):
    """A broken download shouldn't throw away the targets that did run."""
    mock_resolve_stored.return_value = {"2.5.4"}
    mock_download_baseline.side_effect = RuntimeError("no such bucket")
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"], "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
    })

    output = main(config_path)

    assert [r["status"] for r in output["results"]] == ["success", "failed"]


@mock.patch("alpaca.benchmark.main.upload_baseline")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_publishes_every_version_target_when_configured(mock_model_main, mock_upload_baseline, tmp_path):
    """Test that PUBLISH_BASELINE uploads each successful version target's own results."""
    results_dir = tmp_path / "results"
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "PUBLISH_BASELINE": "True",
        "RESULT_DIRECTORY": str(results_dir),
    })

    main(config_path)

    assert [call.args[1] for call in mock_upload_baseline.call_args_list] == ["2.5.6", "2.5.4"]
    assert mock_upload_baseline.call_args_list[0].args[0] == "s3://alpaca-benchmark"


@mock.patch("alpaca.benchmark.main.upload_baseline")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_does_not_publish_a_branch_target(mock_model_main, mock_upload_baseline, tmp_path):
    """A baseline is stored under a version, which a branch target hasn't got."""
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6"],
        "OASISLMF_BRANCHES": ["stable/2.5.x"],
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "PUBLISH_BASELINE": "True",
    })

    main(config_path)

    assert [call.args[1] for call in mock_upload_baseline.call_args_list] == ["2.5.6"]


@mock.patch("alpaca.benchmark.main.upload_baseline")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_does_not_publish_a_failed_target(mock_model_main, mock_upload_baseline, tmp_path):
    mock_model_main.side_effect = [None, RuntimeError("boom")]
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "PUBLISH_BASELINE": "True",
    })

    main(config_path)

    assert [call.args[1] for call in mock_upload_baseline.call_args_list] == ["2.5.6"]


def test_main_raises_when_publish_baseline_missing_bucket(tmp_path):
    """Test that PUBLISH_BASELINE without BENCHMARK_BUCKET is rejected before any EC2 spend."""
    config_path = _write_config(tmp_path, {"OASISLMF_VERSIONS": ["2.5.4"], "PUBLISH_BASELINE": "True"})

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)


def test_main_raises_when_publish_baseline_has_no_versions(tmp_path):
    """Test that publishing a branch-only benchmark is rejected: there's no version to
    store its baseline under.
    """
    config_path = _write_config(tmp_path, {
        "OASISLMF_VERSIONS": [],
        "OASISLMF_BRANCHES": ["stable/2.5.x"],
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "PUBLISH_BASELINE": "True",
    })

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)


def test_main_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        main("not/a/real/path.json")


def test_main_raises_on_generic_config_missing_benchmark_keys():
    """The shared tests/config.json fixture has no benchmark-specific keys, so it should fail."""
    with pytest.raises(OasisAlpacaConfigError):
        main(CONFIG_PATH)


@mock.patch("alpaca.benchmark.main.build_comparison_reports")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_prints_benchmark_plan(mock_model_main, mock_build_comparison, tmp_path, capsys):
    """Test that main prints the benchmark plan in the documented format."""
    mock_build_comparison.return_value = {"reference": "PiWind 2.3.3", "status": "pass", "comparisons": []}
    config_path = _write_config(tmp_path, {"EXECUTION_MODE": "parallel"})

    main(config_path)

    assert capsys.readouterr().out.startswith(
        "Benchmark configuration loaded\n"
        "\n"
        "Models:\n"
        "- PiWind\n"
        "\n"
        "Targets:\n"
        "- PiWind: OasisLMF 2.3.3\n"
        "- PiWind: OasisLMF 2.4.9\n"
        "\n"
        "Execution mode:\n"
        "parallel\n"
    )


def test_main_raises_on_invalid_execution_mode(tmp_path):
    """Test that an EXECUTION_MODE outside 'parallel'/'sequential' is rejected."""
    config_path = _write_config(tmp_path, {"EXECUTION_MODE": "sideways"})

    with pytest.raises(OasisAlpacaConfigError):
        main(config_path)


@mock.patch("alpaca.benchmark.main.build_comparison_reports")
@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_writes_report_file_alongside_result_directories(mock_model_main, mock_build_comparison, tmp_path):
    """Test that main saves the printed report to a file next to the targets' results,
    so it's still available for review after the terminal output has scrolled away.
    """
    mock_build_comparison.return_value = {"reference": "PiWind 2.3.3", "status": "pass", "comparisons": []}
    results_dir = tmp_path / "results"
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    report_path = output["report_path"]
    assert report_path == results_dir / "benchmark_report.txt"
    assert "Benchmark Report" in report_path.read_text()


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_report_includes_timing_table_when_targets_succeed(mock_model_main, tmp_path, capsys):
    """Test that the report includes a step-by-step timing table sourced from each
    target's result.txt, not just the pass/fail output comparison.
    """
    results_dir = tmp_path / "results"

    def make_result_file(target, seconds):
        result_file = results_dir / target / "losses-x" / "runs" / "result.txt"
        result_file.parent.mkdir(parents=True)
        result_file.write_text(f"COMPLETED: oasislmf.manager.interface in {seconds}s\n")
        _write_output_files(results_dir / target, {"summary.csv": "a,b\n1,2\n"})

    make_result_file("PiWind-2.3.3", "210.50")
    make_result_file("PiWind-2.4.9", "165.75")
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    report_text = output["report_path"].read_text()
    header = [line for line in report_text.splitlines() if line.startswith("Step ") and "PiWind" in line][0]
    assert header.index("PiWind 2.4.9") < header.index("PiWind 2.3.3")
    assert "oasislmf.manager.interface" in report_text
    assert "165.75" in report_text
    assert "210.50 (+27.0%)" in report_text
    assert capsys.readouterr().out.count("Step timings") == 1


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_saves_a_plain_text_report_and_prints_a_coloured_one(mock_model_main, tmp_path, capsys, in_green):
    """The terminal gets the quickest run and step highlighted; the saved report is read as
    text, so it must stay free of colour codes.
    """
    results_dir = tmp_path / "results"
    for target, seconds in [("PiWind-2.3.3", "210.50"), ("PiWind-2.4.9", "165.75")]:
        result_file = results_dir / target / "losses-x" / "result.txt"
        result_file.parent.mkdir(parents=True)
        result_file.write_text(f"COMPLETED: oasislmf.manager.interface in {seconds}s\n")
        _write_output_files(results_dir / target, {"summary.csv": "a,b\n1,2\n"})
    config_path = _write_config(tmp_path, {"RESULT_DIRECTORY": str(results_dir)})

    output = main(config_path)

    assert in_green(capsys.readouterr().out) == ["- PiWind 2.4.9: success (166s)", "165.75"]
    assert "\x1b" not in output["report_path"].read_text()


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
