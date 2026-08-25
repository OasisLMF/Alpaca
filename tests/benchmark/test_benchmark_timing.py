from alpaca.benchmark.timing import (
    build_timing_table, fastest_result, find_result_file, format_timing_table, parse_step_timings,
    resolve_model_runtime, sort_results_by_speed
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


def test_resolve_model_runtime_passes_through_a_none_fallback(tmp_path):
    """A stored baseline has no wall-clock time to fall back on, so it reports no runtime
    rather than a made-up one.
    """
    runtime_seconds, step_timings = resolve_model_runtime(tmp_path, fallback_runtime_seconds=None)

    assert runtime_seconds is None
    assert step_timings == {}


def test_resolve_model_runtime_falls_back_when_manager_interface_step_missing(tmp_path):
    result_file = tmp_path / "result.txt"
    result_file.write_text("COMPLETED: computation.generate.files.run in 12.34s\n")

    runtime_seconds, step_timings = resolve_model_runtime(tmp_path, fallback_runtime_seconds=999)

    assert runtime_seconds == 999
    assert step_timings == {"computation.generate.files.run": 12.34}


def _result(version, status, runtime_seconds):
    return {"label": version, "model": "PiWind", "version": version, "status": status, "runtime_seconds": runtime_seconds}


def test_fastest_result_picks_the_quickest_successful_run():
    results = [_result("2.3.3", "success", 210), _result("2.4.9", "success", 166), _result("2.5.6", "success", 300)]

    assert fastest_result(results)["version"] == "2.4.9"


def test_fastest_result_ignores_failed_runs():
    """A target that fell over early is not the fastest run, it's a failure."""
    results = [_result("2.3.3", "success", 210), _result("2.4.9", "failed", 5)]

    assert fastest_result(results)["version"] == "2.3.3"


def test_fastest_result_ignores_runs_without_a_known_runtime():
    """A stored baseline published without performance metrics can't be ranked."""
    results = [_result("2.3.3", "success", 210), _result("2.4.9", "success", None)]

    assert fastest_result(results)["version"] == "2.3.3"


def test_fastest_result_returns_none_when_nothing_succeeded():
    assert fastest_result([_result("2.3.3", "failed", 5)]) is None


def test_fastest_result_keeps_the_earlier_target_on_a_tie():
    results = [_result("2.3.3", "success", 200), _result("2.4.9", "success", 200)]

    assert fastest_result(results)["version"] == "2.3.3"


def test_sort_results_by_speed_orders_quickest_first():
    results = [_result("2.3.3", "success", 210), _result("2.4.9", "success", 166), _result("2.5.6", "success", 300)]

    assert [result["version"] for result in sort_results_by_speed(results)] == ["2.4.9", "2.3.3", "2.5.6"]


def test_sort_results_by_speed_puts_unrankable_runs_last():
    """A failed run, or a stored baseline with no recorded runtime, has no place in the
    ranking, but still belongs in the report.
    """
    results = [_result("2.3.3", "failed", 5), _result("2.4.9", "success", None), _result("2.5.6", "success", 300)]

    assert [result["version"] for result in sort_results_by_speed(results)] == ["2.5.6", "2.3.3", "2.4.9"]


def test_sort_results_by_speed_keeps_configured_order_on_a_tie():
    results = [_result("2.3.3", "success", 200), _result("2.4.9", "success", 200)]

    assert [result["version"] for result in sort_results_by_speed(results)] == ["2.3.3", "2.4.9"]


def test_sort_results_by_speed_ranks_a_zero_second_run():
    """0s is a runtime, so it ranks (and wins), unlike a missing one."""
    results = [_result("2.3.3", "success", 166), _result("2.4.9", "success", 0)]

    assert [result["version"] for result in sort_results_by_speed(results)] == ["2.4.9", "2.3.3"]
    assert fastest_result(results)["version"] == "2.4.9"


def test_sort_results_by_speed_handles_a_single_run():
    assert [result["version"] for result in sort_results_by_speed([_result("2.4.9", "success", 166)])] == ["2.4.9"]


def test_sort_results_by_speed_handles_no_runs():
    assert sort_results_by_speed([]) == []


def test_fastest_result_returns_none_for_no_runs():
    assert fastest_result([]) is None


def test_build_timing_table_lines_up_every_run_per_step():
    runs = [
        ("2.4.9", {"oasislmf.manager.interface": 100.0, "execution.runner.run": 80.0}),
        ("2.5.6", {"oasislmf.manager.interface": 110.0, "execution.runner.run": 76.0}),
    ]

    assert build_timing_table(runs) == [
        {"step": "execution.runner.run", "seconds": [80.0, 76.0], "fastest_seconds": 76.0},
        {"step": "oasislmf.manager.interface", "seconds": [100.0, 110.0], "fastest_seconds": 100.0},
    ]


def test_build_timing_table_marks_steps_missing_from_a_run():
    runs = [("2.4.9", {"only_in_first": 5.0, "shared_step": 10.0}), ("2.5.6", {"shared_step": 12.0})]
    by_step = {row["step"]: row for row in build_timing_table(runs)}

    assert by_step["only_in_first"]["seconds"] == [5.0, None]
    assert by_step["only_in_first"]["fastest_seconds"] == 5.0
    assert by_step["shared_step"]["fastest_seconds"] == 10.0


def test_build_timing_table_has_no_rows_when_no_run_was_timed():
    assert build_timing_table([("2.4.9", {}), ("2.5.6", {})]) == []


def test_build_timing_table_has_no_rows_for_no_runs():
    assert build_timing_table([]) == []


def test_build_timing_table_handles_a_single_run():
    """One target still gets a timing table, it just has nothing to be behind."""
    assert build_timing_table([("2.4.9", {"step": 100.0})]) == [
        {"step": "step", "seconds": [100.0], "fastest_seconds": 100.0},
    ]


def test_format_timing_table_handles_a_single_run():
    table = format_timing_table(["2.4.9"], build_timing_table([("2.4.9", {"step": 100.0})]))

    assert "100.00" in table
    assert "%" not in table


def test_format_timing_table_handles_a_row_no_run_timed():
    """A hand-built row with nothing to compare must not claim a winner."""
    rows = [{"step": "step", "seconds": [None, None], "fastest_seconds": None}]

    table = format_timing_table(["first", "second"], rows, colour=True)

    assert table.splitlines()[2].count("n/a") == 2
    assert "\x1b" not in table


def test_format_timing_table_is_human_readable_and_aligned():
    runs = [("PiWind 2.4.9", {"oasislmf.manager.interface": 165.75, "short": 1.0}),
            ("PiWind 2.5.6", {"oasislmf.manager.interface": 210.5, "short": 1.0})]

    table = format_timing_table([name for name, _ in runs], build_timing_table(runs))
    lines = table.splitlines()

    assert lines[0].startswith("Step")
    assert "PiWind 2.4.9" in lines[0]
    assert "PiWind 2.5.6" in lines[0]
    assert all(len(line) == len(lines[0]) for line in lines)


def test_format_timing_table_columns_follow_the_order_given():
    """The caller orders the runs by speed, and the table must not resort them."""
    runs = [("slowest", {"step": 300.0}), ("quickest", {"step": 100.0})]

    header = format_timing_table([name for name, _ in runs], build_timing_table(runs)).splitlines()[0]

    assert header.index("slowest") < header.index("quickest")


def test_format_timing_table_shows_how_far_behind_the_quickest_each_run_was():
    runs = [("quickest", {"step": 100.0}), ("slower", {"step": 110.0})]

    table = format_timing_table([name for name, _ in runs], build_timing_table(runs))

    assert "100.00" in table
    assert "110.00 (+10.0%)" in table


def test_format_timing_table_avoids_division_by_zero():
    runs = [("quickest", {"instant_step": 0.0}), ("slower", {"instant_step": 1.0})]

    table = format_timing_table([name for name, _ in runs], build_timing_table(runs))

    assert "1.00" in table
    assert "%" not in table


def test_format_timing_table_greens_the_quickest_run_of_each_step(in_green):
    """Each step is its own race, so the winning cell is highlighted per row rather than
    per column - a run can win one step and lose another.
    """
    runs = [("first", {"step_a": 100.0, "step_b": 50.0}), ("second", {"step_a": 90.0, "step_b": 80.0})]

    table = format_timing_table([name for name, _ in runs], build_timing_table(runs), colour=True)
    step_a, step_b = table.splitlines()[2], table.splitlines()[3]

    assert in_green(step_a) == ["90.00"]
    assert in_green(step_b) == ["50.00"]


def test_format_timing_table_is_plain_text_by_default(in_green):
    """The saved report is read as text, so it must never carry colour codes."""
    runs = [("first", {"step": 100.0}), ("second", {"step": 90.0})]

    table = format_timing_table([name for name, _ in runs], build_timing_table(runs))

    assert "\x1b" not in table


def test_format_timing_table_does_not_green_a_missing_value(in_green):
    runs = [("first", {"other_step": 1.0}), ("second", {"step": 90.0})]

    table = format_timing_table([name for name, _ in runs], build_timing_table(runs), colour=True)
    other_step_row = [line for line in table.splitlines() if line.startswith("other_step")][0]

    assert "n/a" in other_step_row
    assert in_green(other_step_row) == ["1.00"]


def test_format_timing_table_returns_empty_string_for_no_rows():
    assert format_timing_table(["2.4.9"], []) == ""
