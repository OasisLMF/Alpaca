from alpaca.benchmark.executor import run_benchmark_targets

from unittest import mock

import threading
import time


def _entry(label, model="PiWind", version="2.3.3"):
    return {"label": label, "model": model, "version": version, "run_config": {"label": label}}


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_reuses_model_main_per_target(mock_model_main):
    run_configs = [_entry("baseline"), _entry("comparison", version="2.4.9")]

    run_benchmark_targets(run_configs, "sequential")

    assert mock_model_main.call_count == 2
    run_configs_called = [call.args[0] for call in mock_model_main.call_args_list]
    assert run_configs_called == [{"label": "baseline"}, {"label": "comparison"}]


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_reports_success(mock_model_main):
    run_configs = [_entry("baseline"), _entry("comparison", version="2.4.9")]

    results = run_benchmark_targets(run_configs, "sequential")

    assert results == [
        {"model": "PiWind", "version": "2.3.3", "status": "success", "runtime_seconds": mock.ANY},
        {"model": "PiWind", "version": "2.4.9", "status": "success", "runtime_seconds": mock.ANY},
    ]


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_reports_failure_without_raising(mock_model_main):
    mock_model_main.side_effect = RuntimeError("instance setup failed")
    run_configs = [_entry("baseline")]

    results = run_benchmark_targets(run_configs, "sequential")

    assert results[0]["status"] == "failed"


@mock.patch("alpaca.benchmark.executor.time.monotonic", side_effect=[100.0, 142.7])
@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_records_runtime_seconds(mock_model_main, mock_monotonic):
    results = run_benchmark_targets([_entry("baseline")], "sequential")

    assert results[0]["runtime_seconds"] == 43


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_sequential_runs_one_at_a_time(mock_model_main):
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
    run_configs = [_entry("baseline"), _entry("comparison", version="2.4.9")]

    run_benchmark_targets(run_configs, "sequential")

    assert concurrency["max"] == 1


@mock.patch("alpaca.benchmark.executor.model_main")
def test_run_benchmark_targets_parallel_runs_concurrently(mock_model_main):
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
    run_configs = [_entry("baseline"), _entry("comparison", version="2.4.9")]

    run_benchmark_targets(run_configs, "parallel")

    assert concurrency["max"] == 2
