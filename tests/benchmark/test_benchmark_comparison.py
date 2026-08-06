from alpaca.benchmark.comparison import (
    find_output_dir, compare_output_dirs, build_comparison_report, format_comparison_report
)
from alpaca.exceptions import OasisAlpacaError

import pytest


def _write(directory, files):
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (directory / name).write_text(content)


def test_find_output_dir_locates_nested_output_directory():
    """OasisLMF nests output under a generated 'losses-<timestamp>' directory."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        output_dir = run_dir / "losses-20260804135955" / "output"
        _write(output_dir, {"summary.csv": "a,b\n1,2\n"})

        assert find_output_dir(run_dir) == output_dir


def test_find_output_dir_raises_when_missing(tmp_path):
    with pytest.raises(OasisAlpacaError):
        find_output_dir(tmp_path)


def test_compare_output_dirs_returns_empty_when_identical(tmp_path):
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"summary.csv": "a,b\n1,2\n", "gul_summary.csv": "x\n1\n"})
    _write(comparison, {"summary.csv": "a,b\n1,2\n", "gul_summary.csv": "x\n1\n"})

    assert compare_output_dirs(baseline, comparison) == []


def test_compare_output_dirs_reports_files_with_different_content(tmp_path):
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"summary.csv": "a,b\n1,2\n", "gul_summary.csv": "x\n1\n"})
    _write(comparison, {"summary.csv": "a,b\n1,3\n", "gul_summary.csv": "x\n1\n"})

    assert compare_output_dirs(baseline, comparison) == ["summary.csv"]


def test_compare_output_dirs_reports_files_present_on_only_one_side(tmp_path):
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"summary.csv": "a,b\n1,2\n", "only_baseline.csv": "z\n"})
    _write(comparison, {"summary.csv": "a,b\n1,2\n"})

    assert compare_output_dirs(baseline, comparison) == ["only_baseline.csv"]


def test_build_comparison_report_passes_when_identical(tmp_path):
    baseline = tmp_path / "baseline" / "output"
    comparison = tmp_path / "comparison" / "output"
    _write(baseline, {"summary.csv": "a,b\n1,2\n"})
    _write(comparison, {"summary.csv": "a,b\n1,2\n"})

    report = build_comparison_report(tmp_path / "baseline", tmp_path / "comparison")

    assert report == {"status": "pass", "different_files": []}


def test_build_comparison_report_fails_when_different(tmp_path):
    baseline = tmp_path / "baseline" / "output"
    comparison = tmp_path / "comparison" / "output"
    _write(baseline, {"summary.csv": "a,b\n1,2\n", "gul_summary.csv": "x\n1\n"})
    _write(comparison, {"summary.csv": "a,b\n1,3\n", "gul_summary.csv": "x\n2\n"})

    report = build_comparison_report(tmp_path / "baseline", tmp_path / "comparison")

    assert report == {"status": "fail", "different_files": ["gul_summary.csv", "summary.csv"]}


def test_format_comparison_report_pass():
    assert format_comparison_report({"status": "pass", "different_files": []}) == "PASS:\nOutputs identical"


def test_format_comparison_report_fail_matches_documented_layout():
    report = {"status": "fail", "different_files": ["summary.csv", "gul_summary.csv"]}
    assert format_comparison_report(report) == (
        "FAIL:\n"
        "Files different:\n"
        "- summary.csv\n"
        "- gul_summary.csv"
    )
