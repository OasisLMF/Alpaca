from alpaca.benchmark.comparison import find_output_dir
from alpaca.benchmark.executor import run_benchmark_targets
from alpaca.benchmark.main import benchmark_failed, main
from alpaca.benchmark.manifest import build_manifest, manifest_differences
from alpaca.benchmark.report import build_report_text
from alpaca.benchmark.s3_baseline import download_baseline, upload_baseline
from alpaca.benchmark.scripts import build_benchmark_plan, format_benchmark_plan
from alpaca.benchmark.timing import (
    find_result_file, outside_repeats, repeat_directories, resolve_model_runtime, resolve_repeat_timings
)
from alpaca.benchmark.utils import validate_repeats
from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from moto import mock_aws
from pathlib import Path
from unittest import mock

import boto3
import json
import os
import pytest
import time


PIWIND = "https://github.com/OasisLMF/OasisPiWind"


def _write_run(directory, seconds, output="a,b\n1,2\n", steps=None):
    """Lay out one run's results the way a download does: result.txt and losses-*/output beside it."""
    directory = Path(directory)
    (directory / "losses-20261103000000" / "output").mkdir(parents=True, exist_ok=True)
    (directory / "losses-20261103000000" / "output" / "summary.csv").write_text(output)
    lines = [f"COMPLETED: oasislmf.manager.interface in {seconds}s"]
    lines.extend(f"COMPLETED: {step} in {value}s" for step, value in (steps or {}).items())
    (directory / "result.txt").write_text("\n".join(lines) + "\n")


def _write_repeats(directory, seconds, outputs=None):
    """Lay out a repeated run: the first run in directory, each later one under repeats/<number>."""
    for index, value in enumerate(seconds):
        output = (outputs or {}).get(index + 1, "a,b\n1,2\n")
        _write_run(directory if index == 0 else Path(directory) / "repeats" / str(index + 1), value, output)


# --- timing -----------------------------------------------------------------------------------

def test_repeat_directories_lists_the_first_run_then_each_repeat_in_number_order(tmp_path):
    for name in ("10", "2", "3", "notes"):
        (tmp_path / "repeats" / name).mkdir(parents=True)

    assert repeat_directories(tmp_path) == [
        tmp_path, tmp_path / "repeats" / "2", tmp_path / "repeats" / "3", tmp_path / "repeats" / "10",
    ]


def test_repeat_directories_is_just_the_run_when_it_was_not_repeated(tmp_path):
    assert repeat_directories(tmp_path) == [tmp_path]


def test_outside_repeats_tells_the_first_run_from_a_later_repeat(tmp_path):
    assert outside_repeats(tmp_path / "losses-x" / "result.txt", tmp_path)
    assert not outside_repeats(tmp_path / "repeats" / "2" / "result.txt", tmp_path)


def test_find_result_file_never_picks_a_later_repeat_even_when_it_is_newer(tmp_path):
    _write_repeats(tmp_path, [100, 200])
    older = time.time() - 60
    os.utime(tmp_path / "result.txt", (older, older))

    assert find_result_file(tmp_path) == tmp_path / "result.txt"


def test_find_output_dir_never_picks_a_later_repeat_even_when_it_is_newer(tmp_path):
    _write_repeats(tmp_path, [100, 200])
    older = time.time() - 60
    os.utime(tmp_path / "losses-20261103000000" / "output", (older, older))

    assert find_output_dir(tmp_path) == tmp_path / "losses-20261103000000" / "output"


def test_resolve_repeat_timings_matches_resolve_model_runtime_for_a_single_run(tmp_path):
    _write_run(tmp_path, 210.5, steps={"oasislmf.execution.runner.run": 200.0})

    runtime, steps = resolve_model_runtime(tmp_path, 999)
    assert resolve_repeat_timings(tmp_path, 999) == (runtime, steps, [210.5])


def test_resolve_repeat_timings_takes_the_median_of_the_runtime_and_of_each_step(tmp_path):
    for index, (seconds, runner) in enumerate([(394, 380), (503, 490), (420, 401)]):
        directory = tmp_path if index == 0 else tmp_path / "repeats" / str(index + 1)
        _write_run(directory, seconds, steps={"oasislmf.execution.runner.run": runner})

    runtime, steps, repeat_runtimes = resolve_repeat_timings(tmp_path, None)

    assert runtime == 420
    assert steps == {"oasislmf.manager.interface": 420, "oasislmf.execution.runner.run": 401}
    assert repeat_runtimes == [394, 503, 420]


def test_resolve_repeat_timings_leaves_out_a_repeat_with_no_runtime(tmp_path):
    _write_repeats(tmp_path, [100, 300])
    (tmp_path / "repeats" / "3").mkdir()

    assert resolve_repeat_timings(tmp_path, None)[2] == [100, 300]


def test_resolve_repeat_timings_falls_back_when_no_repeat_reported_a_runtime(tmp_path):
    assert resolve_repeat_timings(tmp_path, 42) == (42, {}, [])


# --- validation, plan and manifest ------------------------------------------------------------

def test_validate_repeats_defaults_to_one():
    assert validate_repeats({}) == 1


@pytest.mark.parametrize("repeats", [1, 3, 10])
def test_validate_repeats_accepts_one_to_ten(repeats):
    assert validate_repeats({"REPEATS": repeats}) == repeats


@pytest.mark.parametrize("repeats", [0, -1, 11])
def test_validate_repeats_rejects_anything_else(repeats):
    with pytest.raises(OasisAlpacaConfigError, match="REPEATS must be between 1 and 10"):
        validate_repeats({"REPEATS": repeats})


def test_the_plan_shows_the_repeats_only_when_there_are_any():
    target = {"model": "PiWind", "test": None, "source": "live", "source_label": "OasisLMF 2.5.9",
              "label": "PiWind-2.5.9", "version": "2.5.9", "run_config": {"REPO_LOCATION": PIWIND}}

    assert "Repeats:" not in format_benchmark_plan(build_benchmark_plan({}, [target]))
    assert "Repeats:\n3 runs of each live target on its instance, reported as medians" in format_benchmark_plan(
        build_benchmark_plan({}, [target], repeats=3)
    )


def test_the_manifest_records_the_repeats_and_reads_the_first_runs_input_checksums(tmp_path):
    (tmp_path / "input_checksums.json").write_text(json.dumps({"oasislmf_json": {"path": "first", "sha256": "1"}}))
    (tmp_path / "repeats" / "2").mkdir(parents=True)
    (tmp_path / "repeats" / "2" / "input_checksums.json").write_text(json.dumps({"oasislmf_json": {"path": "a"}}))
    target = {"model": "PiWind", "test": None, "run_config": {"OASISLMF_VERSION": "2.5.9"}}

    manifest = build_manifest(target, tmp_path, repeats=3)

    assert manifest["repeats"] == 3
    assert manifest["inputs"]["oasislmf_json"]["path"] == "first"


def test_manifest_differences_flags_different_repeats_and_treats_older_manifests_as_one():
    base = {"instance_type": "m6i.xlarge", "ami_id": "ami", "inputs": {}}

    assert "repeats differ: 1 vs 3" in manifest_differences(base, {**base, "repeats": 3}, "a", "b")
    assert not any("repeats" in note for note in manifest_differences(base, {**base, "repeats": 1}, "a", "b"))


# --- executor ---------------------------------------------------------------------------------

def _entry(tmp_path, label="PiWind-2.5.9", test=None):
    return {
        "label": label, "model": "PiWind", "test": test, "version": "2.5.9",
        "run_config": {
            "label": label, "REPO_LOCATION": PIWIND, "OASISLMF_VERSION": "2.5.9",
            "PATH_TO_OASISLMF_JSON": f"tests/{test}/oasislmf.json" if test else "./oasislmf.json",
            "RESULT_DIRECTORY": str(tmp_path / label),
        },
    }


def _fake_controller(seconds_by_repeat, failing_repeat=None):
    """A RemoteController stand-in whose download of each repeat writes that repeat's runtime."""
    controller = mock.MagicMock()

    def repeat_of(path):
        parts = Path(path).parts
        return int(parts[parts.index("repeats") + 1]) if "repeats" in parts else 1

    def run_commands(commands, log_condition=None, check=False):
        run_directory = commands[-1].split("cd ", 1)[1].split(" &&", 1)[0]
        if repeat_of(run_directory) == failing_repeat:
            raise OasisAlpacaError("Command failed with exit status 1: oasislmf model run")

    def download_results(from_path, to_path):
        _write_run(to_path, seconds_by_repeat[repeat_of(from_path)])

    controller.run_commands.side_effect = run_commands
    controller.download_results.side_effect = download_results
    remote_controller = mock.MagicMock()
    remote_controller.return_value.__enter__.return_value = controller
    return remote_controller, controller


@mock.patch("alpaca.benchmark.executor.model_main")
def test_a_repeated_target_runs_every_repeat_on_one_instance(mock_model_main, tmp_path):
    remote_controller, controller = _fake_controller({1: 394, 2: 503, 3: 420})

    with mock.patch("alpaca.benchmark.executor.RemoteController", remote_controller):
        [result] = run_benchmark_targets([_entry(tmp_path)], "sequential", repeats=3)

    mock_model_main.assert_not_called()
    assert remote_controller.call_count == 1
    controller.upload_model.assert_called_once_with(PIWIND)
    result_directory = str(tmp_path / "PiWind-2.5.9")
    assert [call.args for call in controller.download_results.call_args_list] == [
        ("/home/ubuntu/alpaca_tests/run/runs", result_directory),
        ("/home/ubuntu/alpaca_tests/run/repeats/2/runs", f"{result_directory}/repeats/2"),
        ("/home/ubuntu/alpaca_tests/run/repeats/3/runs", f"{result_directory}/repeats/3"),
    ]
    assert all("drop_caches" in " ".join(call.args[0]) for call in controller.run_commands.call_args_list)
    assert result["status"] == "success"
    assert result["runtime_seconds"] == 420
    assert result["repeat_runtimes"] == [394, 503, 420]
    manifest = json.loads((tmp_path / "PiWind-2.5.9" / "manifest.json").read_text())
    assert (manifest["repeats"], manifest["tests_per_instance"]) == (3, "separate")


@mock.patch("alpaca.benchmark.executor.model_main")
def test_a_failed_repeat_fails_the_target_and_stops_its_later_repeats(mock_model_main, tmp_path):
    remote_controller, controller = _fake_controller({1: 394, 2: 503, 3: 420}, failing_repeat=2)

    with mock.patch("alpaca.benchmark.executor.RemoteController", remote_controller):
        [result] = run_benchmark_targets([_entry(tmp_path)], "sequential", repeats=3)

    assert result["status"] == "failed"
    assert controller.run_commands.call_count == 2
    assert (tmp_path / "PiWind-2.5.9" / "failure.txt").is_file()


@mock.patch("alpaca.benchmark.executor.model_main")
def test_shared_tests_each_run_every_repeat_on_the_one_instance(mock_model_main, tmp_path):
    entries = [_entry(tmp_path, f"PiWind-{test}-2.5.9", test) for test in ("test_1", "test_2")]
    remote_controller, controller = _fake_controller({1: 100, 2: 110})

    with mock.patch("alpaca.benchmark.executor.RemoteController", remote_controller):
        results = run_benchmark_targets(entries, "sequential", "shared", repeats=2)

    assert remote_controller.call_count == 1
    assert [call.args[0] for call in controller.download_results.call_args_list] == [
        "/home/ubuntu/alpaca_tests/test_1/runs", "/home/ubuntu/alpaca_tests/test_1/repeats/2/runs",
        "/home/ubuntu/alpaca_tests/test_2/runs", "/home/ubuntu/alpaca_tests/test_2/repeats/2/runs",
    ]
    assert [result["repeat_runtimes"] for result in results] == [[100, 110], [100, 110]]
    manifest = json.loads((tmp_path / "PiWind-test_2-2.5.9" / "manifest.json").read_text())
    assert (manifest["repeats"], manifest["tests_per_instance"]) == (2, "shared")


@mock.patch("alpaca.benchmark.executor.model_main")
def test_a_single_run_still_goes_through_model_main(mock_model_main, tmp_path):
    with mock.patch("alpaca.benchmark.executor.RemoteController") as remote_controller:
        run_benchmark_targets([_entry(tmp_path)], "sequential")

    mock_model_main.assert_called_once()
    remote_controller.assert_not_called()


# --- report -----------------------------------------------------------------------------------

def _result(version, runtime, repeat_runtimes, is_baseline=False, **extra):
    return {
        "label": f"PiWind-{version}", "model": "PiWind", "test": None, "version": version, "status": "success",
        "runtime_seconds": runtime, "total_runtime_seconds": runtime, "repeat_runtimes": repeat_runtimes,
        "step_timings": {"oasislmf.manager.interface": runtime}, "is_baseline": is_baseline, "source": "live", **extra,
    }


def _report(results):
    return build_report_text(results, [{"group": "PiWind", "report": None, "skip_reason": "x"}])


def test_the_report_gives_each_repeated_runs_median_and_range():
    text = _report([_result("2.5.8", 420, [394, 503, 420], is_baseline=True), _result("2.5.9", 466, [455, 466, 471])])

    assert "- PiWind 2.5.8 (baseline): success (420s median of 3, range 394-503s)" in text
    assert "- PiWind 2.5.9: success (466s median of 3, range 455-471s, +11.0% vs baseline, within run-to-run variation)" in text
    assert "Times are medians of each run's repeats." in text


def test_the_report_only_calls_a_change_variation_when_the_ranges_overlap():
    text = _report([_result("2.5.8", 400, [395, 400, 405], is_baseline=True), _result("2.5.9", 470, [466, 470, 480])])

    assert "+17.5% vs baseline)" in text
    assert "within run-to-run variation" not in text


def test_the_report_compares_a_single_stored_baseline_against_a_repeated_runs_range():
    text = _report([_result("2.5.8", 460, [460], is_baseline=True), _result("2.5.9", 466, [455, 466, 471])])

    assert "- PiWind 2.5.8 (baseline): success (460s)" in text
    assert "+1.3% vs baseline, within run-to-run variation" in text


def test_the_report_is_unchanged_without_repeats():
    text = _report([_result("2.5.8", 400, [400], is_baseline=True), _result("2.5.9", 470, [470])])

    assert "- PiWind 2.5.9: success (470s, +17.5% vs baseline)" in text
    assert "median" not in text and "variation" not in text and "Repeat outputs" not in text


def test_the_report_says_whether_each_repeated_runs_repeats_matched():
    text = _report([
        _result("2.5.8", 400, [400, 401], is_baseline=True, repeat_output_differences=[]),
        _result("2.5.9", 470, [470, 471, 469], repeat_output_differences=["repeat 3"]),
    ])

    assert "Repeat outputs (each repeat against its own first run):" in text
    assert "- PiWind 2.5.8 (baseline): all 2 repeats matched" in text
    assert "- PiWind 2.5.9: repeat 3 differed from repeat 1" in text


def test_benchmark_failed_when_a_runs_repeats_did_not_match():
    output = {"results": [_result("2.5.9", 470, [470, 471], repeat_output_differences=["repeat 2"])], "comparison": []}

    assert benchmark_failed(output)
    output["results"][0]["repeat_output_differences"] = []
    assert not benchmark_failed(output)


# --- stored baselines -------------------------------------------------------------------------

@mock_aws
def test_a_baseline_published_with_repeats_comes_back_with_every_repeats_timing(tmp_path):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="alpaca-benchmark")
    _write_repeats(tmp_path / "run", [394, 503, 420])
    upload_baseline("s3://alpaca-benchmark", "PiWind", None, "2.5.8", tmp_path / "run", {"AWS_REGION": "us-east-1"})

    keys = sorted(obj["Key"] for obj in boto3.client("s3", region_name="us-east-1").list_objects_v2(
        Bucket="alpaca-benchmark")["Contents"])
    downloaded = download_baseline(
        "s3://alpaca-benchmark", "PiWind", None, "2.5.8", tmp_path / "downloaded", {"AWS_REGION": "us-east-1"}
    )

    assert "PiWind/2.5.8/performance/repeats/2/result.txt" in keys
    assert not any(key.startswith("PiWind/2.5.8/output/") and "repeats" in key for key in keys)
    assert resolve_repeat_timings(downloaded, None)[2] == [394, 503, 420]


# --- end to end -------------------------------------------------------------------------------

def _write_config(tmp_path, overrides):
    config = {
        "AMI_ID": "id", "SECURITY_GROUP_ID": "group", "SUBNET_ID": "subnet", "IAM_INSTANCE_PROFILE": "profile",
        "REPO_LOCATIONS": [PIWIND], "PATH_TO_OASISLMF_JSON": "./oasislmf.json", "EXECUTION_MODE": "sequential",
        "RESULT_DIRECTORY": str(tmp_path / "runs"), "OASISLMF_VERSIONS": [],
        "OASISLMF_BASELINE_VERSION": "2.5.8", "OASISLMF_TEST_VERSION": "2.5.9", **overrides,
    }
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(config))
    return path


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_reports_medians_and_checks_every_repeats_output(mock_model_main, tmp_path, capsys):
    controller = mock.MagicMock()
    seconds = {"2.5.8": [394, 503, 420], "2.5.9": [455, 466, 471]}
    downloads = []

    def download_results(from_path, to_path):
        version = "2.5.8" if "2.5.8" in to_path else "2.5.9"
        repeat = int(Path(to_path).name) if "repeats" in Path(to_path).parts else 1
        downloads.append((version, repeat))
        output = "a,b\n1,9\n" if (version, repeat) == ("2.5.9", 3) else "a,b\n1,2\n"
        _write_run(to_path, seconds[version][repeat - 1], output)

    controller.download_results.side_effect = download_results
    remote_controller = mock.MagicMock()
    remote_controller.return_value.__enter__.return_value = controller

    with mock.patch("alpaca.benchmark.executor.RemoteController", remote_controller):
        output = main(_write_config(tmp_path, {"REPEATS": 3}))

    printed = capsys.readouterr().out
    assert remote_controller.call_count == 2
    assert len(downloads) == 6
    assert [result["runtime_seconds"] for result in output["results"]] == [420, 466]
    assert "Repeats:\n3 runs of each live target" in printed
    assert "466s median of 3, range 455-471s, +11.0% vs baseline, within run-to-run variation" in printed
    assert "- PiWind 2.5.9: repeat 3 differed from repeat 1" in printed
    assert benchmark_failed(output)


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_rejects_repeats_out_of_range_before_running_anything(mock_model_main, tmp_path):
    with pytest.raises(OasisAlpacaConfigError, match="REPEATS must be between 1 and 10"):
        main(_write_config(tmp_path, {"REPEATS": 0}))
    mock_model_main.assert_not_called()


@mock.patch("alpaca.benchmark.executor.model_main")
def test_main_counts_a_repeat_whose_output_cannot_be_read_as_differing(mock_model_main, tmp_path, caplog):
    controller = mock.MagicMock()

    def download_results(from_path, to_path):
        if "repeats" in Path(to_path).parts:
            Path(to_path).mkdir(parents=True, exist_ok=True)
            (Path(to_path) / "result.txt").write_text("COMPLETED: oasislmf.manager.interface in 400s\n")
        else:
            _write_run(to_path, 400)

    controller.download_results.side_effect = download_results
    remote_controller = mock.MagicMock()
    remote_controller.return_value.__enter__.return_value = controller

    with mock.patch("alpaca.benchmark.executor.RemoteController", remote_controller):
        output = main(_write_config(tmp_path, {"REPEATS": 2}))

    assert [result["repeat_output_differences"] for result in output["results"]] == [["repeat 2"], ["repeat 2"]]
    assert "Could not compare the repeats of PiWind 2.5.8 (baseline)" in caplog.text
