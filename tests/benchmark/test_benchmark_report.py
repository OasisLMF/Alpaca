from alpaca.benchmark.report import build_report_text, write_report


def _result(model, version, status, runtime_seconds, step_timings=None):
    return {
        "label": f"{model}-{version}", "model": model, "version": version, "status": status,
        "runtime_seconds": runtime_seconds, "step_timings": step_timings or {},
    }


def _comparison(reference, comparisons):
    return {
        "reference": reference,
        "status": "pass" if all(c["status"] == "pass" for c in comparisons) else "fail",
        "comparisons": comparisons,
    }


PASSING_COMPARISON = _comparison("PiWind 2.4.9", [{"target": "PiWind 2.3.3", "status": "pass", "different_files": []}])


def test_build_report_text_includes_run_summary_for_each_target():
    results = [
        _result("PiWind", "2.3.3", "success", 210),
        _result("PiWind", "2.4.9", "success", 166),
    ]
    report_text = build_report_text(results, PASSING_COMPARISON)

    assert "- PiWind 2.3.3: success (210s)" in report_text
    assert "- PiWind 2.4.9: success (166s)" in report_text


def test_build_report_text_lists_the_runs_quickest_first():
    """The report is ordered by speed, not by the order the targets were configured in."""
    results = [
        _result("PiWind", "2.3.3", "success", 210),
        _result("PiWind", "2.4.9", "success", 166),
        _result("PiWind", "2.5.6", "success", 300),
    ]
    run_lines = [line for line in build_report_text(results, PASSING_COMPARISON).splitlines() if line.startswith("- ")]

    assert run_lines == [
        "- PiWind 2.4.9: success (166s)",
        "- PiWind 2.3.3: success (210s)",
        "- PiWind 2.5.6: success (300s)",
    ]


def test_build_report_text_lists_unrankable_runs_last():
    results = [_result("PiWind", "2.3.3", "failed", 5), _result("PiWind", "2.4.9", "success", 166)]
    run_lines = [line for line in build_report_text(results, PASSING_COMPARISON).splitlines() if line.startswith("- ")]

    assert run_lines == ["- PiWind 2.4.9: success (166s)", "- PiWind 2.3.3: failed (5s)"]


def test_build_report_text_puts_every_run_in_one_table_quickest_column_first():
    """One table with a column per run, left to right by overall speed, so any number of
    targets reads the same way.
    """
    results = [
        _result("PiWind", "2.3.3", "success", 210, {"oasislmf.manager.interface": 210.5}),
        _result("PiWind", "2.4.9", "success", 166, {"oasislmf.manager.interface": 165.75}),
        _result("PiWind", "2.5.6", "success", 300, {"oasislmf.manager.interface": 300.25}),
    ]
    report_text = build_report_text(results, PASSING_COMPARISON)
    header = [line for line in report_text.splitlines() if line.startswith("Step ") and "PiWind" in line][0]

    assert report_text.count("Step timings") == 1
    assert header.index("PiWind 2.4.9") < header.index("PiWind 2.3.3") < header.index("PiWind 2.5.6")
    assert "165.75" in report_text
    assert "210.50 (+27.0%)" in report_text
    assert "300.25 (+81.1%)" in report_text


def test_build_report_text_greens_the_quickest_run_and_step(in_green):
    results = [
        _result("PiWind", "2.3.3", "success", 210, {"oasislmf.manager.interface": 210.5, "step": 1.0}),
        _result("PiWind", "2.4.9", "success", 166, {"oasislmf.manager.interface": 165.75, "step": 2.0}),
    ]
    report_text = build_report_text(results, PASSING_COMPARISON, colour=True)

    assert in_green(report_text) == ["- PiWind 2.4.9: success (166s)", "165.75", "1.00"]


def test_build_report_text_greens_nothing_when_no_run_succeeded(in_green):
    results = [_result("PiWind", "2.3.3", "failed", 5), _result("PiWind", "2.4.9", "failed", 7)]

    report_text = build_report_text(results, None, colour=True)

    assert in_green(report_text) == []
    assert "Step timings" not in report_text


def test_build_report_text_reports_a_zero_second_runtime_as_a_runtime():
    """0s is a runtime, unlike a stored baseline's missing one."""
    results = [_result("PiWind", "2.3.3", "success", 0), _result("PiWind", "2.4.9", "success", 166)]
    report_text = build_report_text(results, PASSING_COMPARISON)

    assert "- PiWind 2.3.3: success (0s)" in report_text
    assert "runtime unknown" not in report_text


def test_build_report_text_is_plain_text_by_default(in_green):
    """The saved report is read as text, so it must never carry colour codes."""
    results = [_result("PiWind", "2.3.3", "success", 210), _result("PiWind", "2.4.9", "success", 166)]

    assert "\x1b" not in build_report_text(results, PASSING_COMPARISON)


def test_build_report_text_notes_when_a_run_has_no_timing_data():
    results = [_result("PiWind", "2.3.3", "success", 210), _result("PiWind", "2.4.9", "success", 166)]
    report_text = build_report_text(results, PASSING_COMPARISON)

    assert "No timing data available." in report_text


def test_build_report_text_leaves_failed_runs_out_of_the_timing_table():
    """A failed run has no timings to compare, but still belongs in the run summary."""
    results = [
        _result("PiWind", "2.3.3", "success", 210, {"oasislmf.manager.interface": 210.5}),
        _result("PiWind", "2.4.9", "success", 166, {"oasislmf.manager.interface": 165.75}),
        _result("PiWind", "2.5.6", "failed", 5),
    ]
    report_text = build_report_text(results, PASSING_COMPARISON)
    header = [line for line in report_text.splitlines() if line.startswith("Step ") and "PiWind" in line][0]

    assert "- PiWind 2.5.6: failed (5s)" in report_text
    assert "PiWind 2.5.6" not in header


def test_build_report_text_shows_a_stored_baseline_without_a_runtime():
    """A baseline published with no performance metrics has no runtime to report, so it
    can't be ranked against the runs that have one.
    """
    results = [
        _result("PiWind", "2.4.9 (S3 baseline)", "success", None),
        _result("PiWind", "2.3.3", "success", 210),
    ]
    run_lines = [line for line in build_report_text(results, PASSING_COMPARISON).splitlines() if line.startswith("- ")]

    assert run_lines == [
        "- PiWind 2.3.3: success (210s)",
        "- PiWind 2.4.9 (S3 baseline): success (runtime unknown)",
    ]


def test_build_report_text_includes_output_comparison_result():
    results = [_result("PiWind", "2.3.3", "success", 210), _result("PiWind", "2.4.9", "success", 166)]
    comparison = _comparison("PiWind 2.4.9", [{"target": "PiWind 2.3.3", "status": "fail", "different_files": ["summary.csv"]}])
    report_text = build_report_text(results, comparison)

    assert "Output comparison against PiWind 2.4.9:" in report_text
    assert "FAIL:" in report_text
    assert "- summary.csv" in report_text


def test_build_report_text_omits_timing_comparison_when_only_one_target_succeeded():
    results = [_result("PiWind", "2.3.3", "success", 210), _result("PiWind", "2.4.9", "failed", 5)]
    report_text = build_report_text(results, None)

    assert "Timing comparison" not in report_text
    assert "Output comparison skipped" in report_text


def test_build_report_text_uses_custom_skip_reason():
    """Test that a caller-supplied skip_reason overrides the default failure message."""
    results = [_result("PiWind", "2.5.6", "success", 210)]
    report_text = build_report_text(results, None, skip_reason="only one target was configured")

    assert "Output comparison skipped: only one target was configured." in report_text


def test_write_report_creates_file_with_report_text(tmp_path):
    report_path = write_report("some report text", tmp_path / "results")

    assert report_path == tmp_path / "results" / "benchmark_report.txt"
    assert report_path.read_text() == "some report text"


def test_write_report_creates_missing_parent_directories(tmp_path):
    report_path = write_report("report", tmp_path / "a" / "b" / "c")

    assert report_path.exists()
