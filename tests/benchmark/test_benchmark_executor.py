from alpaca.benchmark.executor import instance_groups, run_benchmark_targets
from alpaca.exceptions import OasisAlpacaError
from pathlib import Path
from alpaca.logging_context import TargetFilter

from unittest import mock

import json
import logging
import threading
import time


def _entry(label, run_directory, model="PiWind", version="2.3.3", test=None):
    return {
        "label": label, "model": model, "test": test, "version": version,
        "run_config": {"label": label, "RESULT_DIRECTORY": str(run_directory)},
    }


def _write_result_file(run_directory, content):
    result_file = run_directory / "losses-20260811133635" / "runs" / "result.txt"
    result_file.parent.mkdir(parents=True)
    result_file.write_text(content)


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_reuses_model_main_per_target(mock_model_main, tmp_path):
    run_configs = [_entry("baseline", tmp_path / "baseline"), _entry("comparison", tmp_path / "comparison", version="2.4.9")]

    run_benchmark_targets(run_configs, "sequential")

    assert mock_model_main.call_count == 2
    run_configs_called = [call.args[0] for call in mock_model_main.call_args_list]
    assert run_configs_called == [entry["run_config"] for entry in run_configs]


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_reports_success(mock_model_main, tmp_path):
    """Without a result.txt, runtime_seconds falls back to the wall-clock timing."""
    run_configs = [_entry("baseline", tmp_path / "baseline"), _entry("comparison", tmp_path / "comparison", version="2.4.9")]

    results = run_benchmark_targets(run_configs, "sequential")

    assert results == [
        {
            "label": "baseline", "model": "PiWind", "test": None, "version": "2.3.3", "status": "success",
            "runtime_seconds": mock.ANY, "total_runtime_seconds": mock.ANY, "step_timings": {},
        },
        {
            "label": "comparison", "model": "PiWind", "test": None, "version": "2.4.9", "status": "success",
            "runtime_seconds": mock.ANY, "total_runtime_seconds": mock.ANY, "step_timings": {},
        },
    ]


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_reports_failure_without_raising(mock_model_main, tmp_path):
    mock_model_main.side_effect = RuntimeError("instance setup failed")
    run_configs = [_entry("baseline", tmp_path / "baseline")]

    results = run_benchmark_targets(run_configs, "sequential")

    assert results[0]["status"] == "failed"


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_does_not_look_for_result_file_on_failure(mock_model_main, tmp_path):
    """A failed target has no valid result.txt to trust, so runtime_seconds should just be
    the wall-clock timing rather than attempting to resolve a model runtime from disk.
    """
    mock_model_main.side_effect = RuntimeError("instance setup failed")
    run_configs = [_entry("baseline", tmp_path / "baseline")]

    results = run_benchmark_targets(run_configs, "sequential")

    assert results[0]["runtime_seconds"] == results[0]["total_runtime_seconds"]
    assert results[0]["step_timings"] == {}


@mock.patch("alpaca.benchmark.executor.time.monotonic", side_effect=[100.0, 142.7])
@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_records_total_runtime_seconds(mock_model_main, mock_monotonic, tmp_path):
    results = run_benchmark_targets([_entry("baseline", tmp_path / "baseline")], "sequential")

    assert results[0]["total_runtime_seconds"] == 43


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_uses_model_runtime_step_when_result_file_present(mock_model_main, tmp_path):
    """When OasisLMF's own timing is available, runtime_seconds should reflect the model
    run itself rather than the full wall-clock (EC2 startup, upload and download included).
    """
    run_directory = tmp_path / "baseline"
    _write_result_file(run_directory, (
        "COMPLETED: computation.generate.files.run in 12.34s\n"
        "COMPLETED: execution.runner.run in 200.11s\n"
        "COMPLETED: oasislmf.manager.interface in 257.19s\n"
    ))
    run_configs = [_entry("baseline", run_directory)]

    results = run_benchmark_targets(run_configs, "sequential")

    assert results[0]["runtime_seconds"] == 257
    assert results[0]["step_timings"] == {
        "computation.generate.files.run": 12.34,
        "execution.runner.run": 200.11,
        "oasislmf.manager.interface": 257.19,
    }


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_sequential_runs_one_at_a_time(mock_model_main, tmp_path):
    lock = threading.Lock()
    concurrency = {"current": 0, "max": 0}

    def fake_model_main(run_config):
        with lock:
            concurrency["current"] += 1
            concurrency["max"] = max(concurrency["max"], concurrency["current"])
        time.sleep(0.05)
        with lock:
            concurrency["current"] -= 1

    mock_model_main.side_effect = fake_model_main
    run_configs = [_entry("baseline", tmp_path / "baseline"), _entry("comparison", tmp_path / "comparison", version="2.4.9")]

    run_benchmark_targets(run_configs, "sequential")

    assert concurrency["max"] == 1


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_parallel_runs_concurrently(mock_model_main, tmp_path):
    lock = threading.Lock()
    concurrency = {"current": 0, "max": 0}

    def fake_model_main(run_config):
        with lock:
            concurrency["current"] += 1
            concurrency["max"] = max(concurrency["max"], concurrency["current"])
        time.sleep(0.1)
        with lock:
            concurrency["current"] -= 1

    mock_model_main.side_effect = fake_model_main
    run_configs = [_entry("baseline", tmp_path / "baseline"), _entry("comparison", tmp_path / "comparison", version="2.4.9")]

    run_benchmark_targets(run_configs, "parallel")

    assert concurrency["max"] == 2


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_tags_log_records_with_model_and_version(mock_model_main, tmp_path):
    seen_targets = []

    def fake_model_main(run_config):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", None, None)
        TargetFilter().filter(record)
        seen_targets.append(record.target)

    mock_model_main.side_effect = fake_model_main
    run_configs = [_entry("baseline", tmp_path / "baseline"), _entry("comparison", tmp_path / "comparison", version="2.4.9")]

    run_benchmark_targets(run_configs, "sequential")

    assert seen_targets == [" [PiWind 2.3.3]", " [PiWind 2.4.9]"]


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_clears_log_target_after_each_target(mock_model_main, tmp_path):
    mock_model_main.side_effect = None
    run_configs = [_entry("baseline", tmp_path / "baseline")]

    run_benchmark_targets(run_configs, "sequential")

    record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", None, None)
    TargetFilter().filter(record)
    assert record.target == ""


@mock.patch("alpaca.benchmark.executor.MAX_PARALLEL_TARGETS", 2)
@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_parallel_caps_concurrency(mock_model_main, tmp_path):
    """More targets than the cap queue for a slot rather than all launching an instance at once."""
    lock = threading.Lock()
    concurrency = {"current": 0, "max": 0}

    def fake_model_main(run_config):
        with lock:
            concurrency["current"] += 1
            concurrency["max"] = max(concurrency["max"], concurrency["current"])
        time.sleep(0.1)
        with lock:
            concurrency["current"] -= 1

    mock_model_main.side_effect = fake_model_main
    run_configs = [_entry(f"target-{index}", tmp_path / f"target-{index}") for index in range(5)]

    results = run_benchmark_targets(run_configs, "parallel")

    assert concurrency["max"] == 2
    assert [result["label"] for result in results] == [f"target-{index}" for index in range(5)]


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_writes_a_manifest_for_every_run(mock_model_main, tmp_path):
    run_configs = [_entry("first", tmp_path / "first")]
    run_configs[0]["run_config"]["INSTANCE_TYPE"] = "m5.xlarge"

    run_benchmark_targets(run_configs, "sequential")

    manifest = json.loads((tmp_path / "first" / "manifest.json").read_text())
    assert manifest["instance_type"] == "m5.xlarge"


@mock.patch("alpaca.benchmark.executor.model_main", side_effect=RuntimeError("boom"))
def test_run_benchmark_targets_writes_a_manifest_for_a_failed_run_too(mock_model_main, tmp_path):
    """A failed run's manifest is what shows which of its inputs were missing or changed."""
    run_benchmark_targets([_entry("failed", tmp_path / "failed")], "sequential")

    assert (tmp_path / "failed" / "manifest.json").is_file()


def _test_entry(test, version, tmp_path, location="s3://my-model-bucket"):
    label = f"model-{test}-{version}"
    return {
        "label": label, "model": "model", "test": test, "version": version,
        "run_config": {
            "label": label, "REPO_LOCATION": location, "OASISLMF_VERSION": version,
            "PATH_TO_OASISLMF_JSON": f"tests/{test}/oasislmf.json", "RESULT_DIRECTORY": str(tmp_path / label),
        },
    }


def _fake_controller(failing_tests=()):
    """A RemoteController stand-in: each test 'runs' unless listed, and its download writes a result.txt."""
    controller = mock.MagicMock()

    def run_commands(commands, log_condition=None, check=False):
        if any(f"tests/{test}/" in commands[-1] for test in failing_tests):
            raise OasisAlpacaError("Command failed with exit status 1: oasislmf model run\nValueError: bad test data")

    def download_results(from_path, to_path):
        Path(to_path).mkdir(parents=True, exist_ok=True)
        (Path(to_path) / "result.txt").write_text("COMPLETED: oasislmf.manager.interface in 12.5s\n")

    controller.run_commands.side_effect = run_commands
    controller.download_results.side_effect = download_results
    remote_controller = mock.MagicMock()
    remote_controller.return_value.__enter__.return_value = controller
    return remote_controller, controller


def test_instance_groups_puts_every_target_on_its_own_instance_by_default(tmp_path):
    entries = [_test_entry("test_1", "2.5.8", tmp_path), _test_entry("test_2", "2.5.8", tmp_path)]

    assert instance_groups(entries) == [[entries[0]], [entries[1]]]


def test_instance_groups_shares_an_instance_per_model_and_version(tmp_path):
    entries = [_test_entry(test, version, tmp_path) for version in ("2.5.7", "2.5.8") for test in ("test_1", "test_2")]

    groups = instance_groups(entries, "shared")

    assert [[entry["label"] for entry in group] for group in groups] == [
        ["model-test_1-2.5.7", "model-test_2-2.5.7"], ["model-test_1-2.5.8", "model-test_2-2.5.8"],
    ]


def test_instance_groups_never_shares_between_models(tmp_path):
    entries = [_test_entry("test_1", "2.5.8", tmp_path, "s3://a"), _test_entry("test_1", "2.5.8", tmp_path, "s3://b")]

    assert len(instance_groups(entries, "shared")) == 2


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_runs_shared_tests_on_one_instance(mock_model_main, tmp_path):
    entries = [_test_entry(test, "2.5.8", tmp_path) for test in ("test_1", "test_2", "test_3")]
    remote_controller, controller = _fake_controller()

    with mock.patch("alpaca.benchmark.executor.RemoteController", remote_controller):
        results = run_benchmark_targets(entries, "sequential", "shared")

    assert remote_controller.call_count == 1
    controller.upload_model.assert_called_once_with("s3://my-model-bucket")
    mock_model_main.assert_not_called()
    assert [result["status"] for result in results] == ["success"] * 3
    assert [result["runtime_seconds"] for result in results] == [12, 12, 12]
    downloads = [call.args for call in controller.download_results.call_args_list]
    assert downloads == [
        (f"/home/ubuntu/alpaca_tests/{test}/runs", str(tmp_path / f"model-{test}-2.5.8")) for test in ("test_1", "test_2", "test_3")
    ]
    manifest = json.loads((tmp_path / "model-test_2-2.5.8" / "manifest.json").read_text())
    assert manifest["tests_per_instance"] == "shared"


@mock.patch("alpaca.benchmark.executor.model_main")
def test_a_failing_shared_test_does_not_stop_the_rest(mock_model_main, tmp_path):
    entries = [_test_entry(test, "2.5.8", tmp_path) for test in ("test_1", "test_2", "test_3")]
    remote_controller, controller = _fake_controller(failing_tests=["test_2"])

    with mock.patch("alpaca.benchmark.executor.RemoteController", remote_controller):
        results = run_benchmark_targets(entries, "sequential", "shared")

    assert [result["status"] for result in results] == ["success", "failed", "success"]
    assert results[1]["failure"]["stage"] == "model run"
    assert results[1]["failure"]["message"] == "ValueError: bad test data"
    assert (tmp_path / "model-test_2-2.5.8" / "failure.txt").is_file()
    assert controller.download_results.call_count == 3


@mock.patch("alpaca.benchmark.executor.model_main")
def test_a_shared_instance_that_cannot_be_set_up_fails_every_test_on_it(mock_model_main, tmp_path):
    entries = [_test_entry(test, "2.5.8", tmp_path) for test in ("test_1", "test_2")]
    remote_controller = mock.MagicMock()
    remote_controller.return_value.__enter__.side_effect = OasisAlpacaError("Error during instance setup: no capacity")

    with mock.patch("alpaca.benchmark.executor.RemoteController", remote_controller):
        results = run_benchmark_targets(entries, "sequential", "shared")

    assert [result["status"] for result in results] == ["failed", "failed"]
    assert {result["failure"]["stage"] for result in results} == {"instance setup"}


@mock.patch("alpaca.benchmark.executor.model_main")
def test_a_failed_run_saves_its_evidence_with_any_missing_input(mock_model_main, tmp_path):
    """A wrong model_settings_json shows up in the result as the missing file, not just 'failed'."""
    entry = _test_entry("test_1", "2.5.8", tmp_path)
    run_directory = Path(entry["run_config"]["RESULT_DIRECTORY"])

    def fail(run_config):
        run_directory.mkdir(parents=True)
        (run_directory / "input_checksums.json").write_text(json.dumps({
            "model_settings_json": {"path": "settings/1.4.0.0/model_settings.json", "sha256": None},
        }))
        raise OasisAlpacaError("Command failed: oasislmf model run\nOdsException: Invalid model_settings file or file path")

    mock_model_main.side_effect = fail

    result = run_benchmark_targets([entry], "sequential")[0]

    assert result["failure"]["missing_inputs"] == ["settings/1.4.0.0/model_settings.json"]
    assert result["failure"]["details"] == str(run_directory / "failure.txt")
    assert "- settings/1.4.0.0/model_settings.json" in (run_directory / "failure.txt").read_text()


@mock.patch("alpaca.benchmark.executor.model_main")
def test_a_successful_run_has_no_failure(mock_model_main, tmp_path):
    result = run_benchmark_targets([_test_entry("test_1", "2.5.8", tmp_path)], "sequential")[0]

    assert "failure" not in result
    assert not (tmp_path / "model-test_1-2.5.8" / "failure.txt").exists()
