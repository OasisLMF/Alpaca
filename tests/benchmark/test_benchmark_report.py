from alpaca.benchmark.report import build_report_text, write_report


def _result(model, version, status, runtime_seconds, step_timings=None):
    return {
        "model": model, "version": version, "status": status,
        "runtime_seconds": runtime_seconds, "step_timings": step_timings or {},
    }


def test_build_report_text_includes_run_summary_for_each_target():
    results = [
        _result("PiWind", "2.3.3", "success", 210),
        _result("PiWind", "2.4.9", "success", 166),
    ]
    report_text = build_report_text(results, {"status": "pass", "different_files": []})

    assert "- PiWind 2.3.3: success (210s)" in report_text
    assert "- PiWind 2.4.9: success (166s)" in report_text


def test_build_report_text_includes_timing_comparison_when_both_succeed():
    results = [
        _result("PiWind", "2.3.3", "success", 210, {"oasislmf.manager.interface": 210.5}),
        _result("PiWind", "2.4.9", "success", 166, {"oasislmf.manager.interface": 165.75}),
    ]
    report_text = build_report_text(results, {"status": "pass", "different_files": []})

    assert "Timing comparison (2.3.3 vs 2.4.9):" in report_text
    assert "oasislmf.manager.interface" in report_text
    assert "210.50" in report_text
    assert "165.75" in report_text


def test_build_report_text_includes_output_comparison_result():
    results = [_result("PiWind", "2.3.3", "success", 210), _result("PiWind", "2.4.9", "success", 166)]
    report_text = build_report_text(results, {"status": "fail", "different_files": ["summary.csv"]})

    assert "FAIL:" in report_text
    assert "- summary.csv" in report_text


def test_build_report_text_omits_timing_comparison_when_a_target_failed():
    results = [_result("PiWind", "2.3.3", "success", 210), _result("PiWind", "2.4.9", "failed", 5)]
    report_text = build_report_text(results, None)

    assert "Timing comparison" not in report_text
    assert "Output comparison skipped" in report_text


def test_write_report_creates_file_with_report_text(tmp_path):
    report_path = write_report("some report text", tmp_path / "results")

    assert report_path == tmp_path / "results" / "benchmark_report.txt"
    assert report_path.read_text() == "some report text"


def test_write_report_creates_missing_parent_directories(tmp_path):
    report_path = write_report("report", tmp_path / "a" / "b" / "c")

    assert report_path.exists()
