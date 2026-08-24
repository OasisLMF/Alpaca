from alpaca.benchmark.executor import run_benchmark_targets
from alpaca.logging_context import TargetFilter

from unittest import mock

import logging
import threading
import time


def _entry(label, run_directory, model="PiWind", version="2.3.3"):
    return {"label": label, "model": model, "version": version, "run_config": {"label": label, "RESULT_DIRECTORY": str(run_directory)}}


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
            "label": "baseline", "model": "PiWind", "version": "2.3.3", "status": "success",
            "runtime_seconds": mock.ANY, "total_runtime_seconds": mock.ANY, "step_timings": {},
        },
        {
            "label": "comparison", "model": "PiWind", "version": "2.4.9", "status": "success",
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
