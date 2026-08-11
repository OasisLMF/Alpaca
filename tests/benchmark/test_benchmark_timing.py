from alpaca.benchmark.timing import (
    find_result_file, parse_step_timings, resolve_model_runtime, build_timing_comparison, format_timing_comparison
)

import os
import time


SAMPLE_RESULT_TEXT = (
    "some unrelated log line\n"
    "COMPLETED: computation.generate.files.run in 12.34s\n"
    "COMPLETED: execution.runner.run in 200.11s\n"
    "COMPLETED: oasislmf.manager.interface in 257.19s\n"
)


def test_find_result_file_locates_nested_result_file(tmp_path):
    result_file = tmp_path / "losses-20260811133635" / "runs" / "result.txt"
    result_file.parent.mkdir(parents=True)
    result_file.write_text(SAMPLE_RESULT_TEXT)

    assert find_result_file(tmp_path) == result_file


def test_find_result_file_returns_none_when_missing(tmp_path):
    assert find_result_file(tmp_path) is None


def test_find_result_file_picks_most_recently_modified_when_multiple_exist(tmp_path):
    stale = tmp_path / "losses-old" / "result.txt"
    fresh = tmp_path / "losses-new" / "result.txt"
    stale.parent.mkdir(parents=True)
    fresh.parent.mkdir(parents=True)
    stale.write_text("old")
    fresh.write_text("new")

    old_time = time.time() - 3600
    os.utime(stale, (old_time, old_time))
    os.utime(fresh, (time.time(), time.time()))

    assert find_result_file(tmp_path) == fresh


def test_parse_step_timings_extracts_every_completed_line(tmp_path):
    result_file = tmp_path / "result.txt"
    result_file.write_text(SAMPLE_RESULT_TEXT)

    assert parse_step_timings(result_file) == {
        "computation.generate.files.run": 12.34,
        "execution.runner.run": 200.11,
        "oasislmf.manager.interface": 257.19,
    }


def test_parse_step_timings_returns_empty_for_no_completed_lines(tmp_path):
    result_file = tmp_path / "result.txt"
    result_file.write_text("model run failed before completing anything\n")

    assert parse_step_timings(result_file) == {}


def test_resolve_model_runtime_uses_manager_interface_step(tmp_path):
    result_file = tmp_path / "losses-x" / "result.txt"
    result_file.parent.mkdir(parents=True)
    result_file.write_text(SAMPLE_RESULT_TEXT)

    runtime_seconds, step_timings = resolve_model_runtime(tmp_path, fallback_runtime_seconds=999)

    assert runtime_seconds == 257.19
    assert step_timings["execution.runner.run"] == 200.11


def test_resolve_model_runtime_falls_back_when_no_result_file(tmp_path):
    runtime_seconds, step_timings = resolve_model_runtime(tmp_path, fallback_runtime_seconds=999)

    assert runtime_seconds == 999
    assert step_timings == {}


def test_resolve_model_runtime_falls_back_when_manager_interface_step_missing(tmp_path):
    result_file = tmp_path / "result.txt"
    result_file.write_text("COMPLETED: computation.generate.files.run in 12.34s\n")

    runtime_seconds, step_timings = resolve_model_runtime(tmp_path, fallback_runtime_seconds=999)

    assert runtime_seconds == 999
    assert step_timings == {"computation.generate.files.run": 12.34}


def test_build_timing_comparison_computes_delta_and_percent():
    baseline = {"oasislmf.manager.interface": 100.0, "execution.runner.run": 80.0}
    comparison = {"oasislmf.manager.interface": 110.0, "execution.runner.run": 76.0}

    rows = build_timing_comparison(baseline, comparison)

    assert rows == [
        {
            "step": "execution.runner.run", "baseline_seconds": 80.0, "comparison_seconds": 76.0,
            "delta_seconds": -4.0, "delta_percent": -5.0,
        },
        {
            "step": "oasislmf.manager.interface", "baseline_seconds": 100.0, "comparison_seconds": 110.0,
            "delta_seconds": 10.0, "delta_percent": 10.0,
        },
    ]


def test_build_timing_comparison_marks_steps_missing_from_one_side():
    baseline = {"only_in_baseline": 5.0, "shared_step": 10.0}
    comparison = {"only_in_comparison": 3.0, "shared_step": 10.0}

    rows = build_timing_comparison(baseline, comparison)
    by_step = {row["step"]: row for row in rows}

    assert by_step["only_in_baseline"]["comparison_seconds"] is None
    assert by_step["only_in_baseline"]["delta_seconds"] is None
    assert by_step["only_in_comparison"]["baseline_seconds"] is None
    assert by_step["shared_step"]["delta_seconds"] == 0.0


def test_build_timing_comparison_avoids_division_by_zero():
    rows = build_timing_comparison({"instant_step": 0.0}, {"instant_step": 0.0})

    assert rows[0]["delta_seconds"] == 0.0
    assert rows[0]["delta_percent"] is None


def test_format_timing_comparison_is_human_readable_and_aligned():
    rows = build_timing_comparison(
        {"oasislmf.manager.interface": 210.5, "short": 1.0},
        {"oasislmf.manager.interface": 165.75, "short": 1.0},
    )

    table = format_timing_comparison(rows)
    lines = table.splitlines()

    assert lines[0].startswith("Step")
    assert "Baseline (s)" in lines[0]
    assert "Comparison (s)" in lines[0]
    assert "Delta (s)" in lines[0]
    assert all(len(line) == len(lines[0]) for line in lines)


def test_format_timing_comparison_marks_missing_values_as_not_available():
    rows = build_timing_comparison({"only_in_baseline": 5.0}, {})

    table = format_timing_comparison(rows)

    assert "n/a" in table


def test_format_timing_comparison_returns_empty_string_for_no_rows():
    assert format_timing_comparison([]) == ""
