from alpaca.benchmark.comparison import (
    find_output_dir, compare_output_dirs, build_comparison_report, build_comparison_reports,
    format_comparison_report, format_comparison_reports, resolve_relative_tolerance, DEFAULT_RELATIVE_TOLERANCE
)
from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from unittest import mock

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


def test_find_output_dir_picks_most_recently_modified_when_multiple_exist(tmp_path):
    """RESULT_DIRECTORY isn't cleared between runs, so an older 'losses-*' folder from a
    previous benchmark attempt may still be sitting alongside the one just downloaded. The
    alphabetically-first match (an older timestamp) must not win over the newest one.
    """
    import os
    import time

    stale_output = tmp_path / "losses-20260804135955" / "output"
    fresh_output = tmp_path / "losses-20260811133635" / "output"
    _write(stale_output, {"summary.csv": "old\n"})
    _write(fresh_output, {"summary.csv": "new\n"})

    old_time = time.time() - 3600
    os.utime(stale_output, (old_time, old_time))
    os.utime(fresh_output, (time.time(), time.time()))

    assert find_output_dir(tmp_path) == fresh_output


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


def test_compare_output_dirs_treats_tiny_numeric_differences_as_equal(tmp_path):
    """OasisLMF's Monte Carlo sampling means two identical-input runs rarely produce
    byte-identical loss tables, so small numeric differences should not count as a diff.
    """
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"summary.csv": "a,b\n1,2.0000001\n"})
    _write(comparison, {"summary.csv": "a,b\n1,2.0000002\n"})

    assert compare_output_dirs(baseline, comparison) == []


def test_compare_output_dirs_still_flags_differences_beyond_tolerance(tmp_path):
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"summary.csv": "a,b\n1,2.0\n"})
    _write(comparison, {"summary.csv": "a,b\n1,2.04\n"})

    assert compare_output_dirs(baseline, comparison) == ["summary.csv"]


def test_compare_output_dirs_respects_custom_relative_tolerance(tmp_path):
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"summary.csv": "a,b\n1,2.0\n"})
    _write(comparison, {"summary.csv": "a,b\n1,2.001\n"})

    assert compare_output_dirs(baseline, comparison, relative_tolerance=0.01) == []


def test_compare_output_dirs_requires_exact_match_for_non_numeric_cells(tmp_path):
    """A very loose tolerance must not mask a genuine mismatch in a non-numeric cell."""
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"summary.csv": "model,loss\nPiWind,100.0\n"})
    _write(comparison, {"summary.csv": "model,loss\nOtherModel,100.0\n"})

    assert compare_output_dirs(baseline, comparison, relative_tolerance=1.0) == ["summary.csv"]


def test_compare_output_dirs_flags_differing_row_counts(tmp_path):
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"summary.csv": "a,b\n1,2\n3,4\n"})
    _write(comparison, {"summary.csv": "a,b\n1,2\n"})

    assert compare_output_dirs(baseline, comparison) == ["summary.csv"]


def test_compare_output_dirs_uses_exact_match_for_non_csv_files(tmp_path):
    """Non-CSV files (e.g. analysis_settings.json) are compared exactly, tolerance doesn't apply."""
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"analysis_settings.json": '{"a": 1.0000001}'})
    _write(comparison, {"analysis_settings.json": '{"a": 1.0000002}'})

    assert compare_output_dirs(baseline, comparison, relative_tolerance=1.0) == ["analysis_settings.json"]


def test_compare_output_dirs_skips_csv_parsing_when_checksums_match(tmp_path):
    """A matching checksum should short-circuit the cell-by-cell CSV comparison entirely."""
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"summary.csv": "a,b\n1,2\n"})
    _write(comparison, {"summary.csv": "a,b\n1,2\n"})

    with mock.patch("alpaca.benchmark.comparison._csv_files_match") as mock_csv_match:
        assert compare_output_dirs(baseline, comparison) == []

    mock_csv_match.assert_not_called()


def test_compare_output_dirs_falls_back_to_csv_comparison_on_checksum_mismatch(tmp_path):
    """A checksum mismatch on a CSV should still fall through to the tolerant comparison."""
    baseline = tmp_path / "baseline"
    comparison = tmp_path / "comparison"
    _write(baseline, {"summary.csv": "a,b\n1,2.0000001\n"})
    _write(comparison, {"summary.csv": "a,b\n1,2.0000002\n"})

    assert compare_output_dirs(baseline, comparison) == []


def test_resolve_relative_tolerance_defaults_when_unset():
    assert resolve_relative_tolerance({}) == DEFAULT_RELATIVE_TOLERANCE


def test_resolve_relative_tolerance_reads_configured_value():
    assert resolve_relative_tolerance({"COMPARISON_TOLERANCE": "0.01"}) == 0.01


def test_resolve_relative_tolerance_raises_on_non_numeric_value():
    with pytest.raises(OasisAlpacaConfigError):
        resolve_relative_tolerance({"COMPARISON_TOLERANCE": "not-a-number"})


def test_resolve_relative_tolerance_raises_on_negative_value():
    with pytest.raises(OasisAlpacaConfigError):
        resolve_relative_tolerance({"COMPARISON_TOLERANCE": "-1"})


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


def test_build_comparison_report_passes_within_custom_tolerance(tmp_path):
    baseline = tmp_path / "baseline" / "output"
    comparison = tmp_path / "comparison" / "output"
    _write(baseline, {"summary.csv": "a,b\n1,2.0\n"})
    _write(comparison, {"summary.csv": "a,b\n1,2.001\n"})

    report = build_comparison_report(tmp_path / "baseline", tmp_path / "comparison", relative_tolerance=0.01)

    assert report == {"status": "pass", "different_files": []}


def test_build_comparison_reports_compares_every_target_against_the_reference(tmp_path):
    _write(tmp_path / "fastest" / "output", {"summary.csv": "a,b\n1,2\n"})
    _write(tmp_path / "same" / "output", {"summary.csv": "a,b\n1,2\n"})
    _write(tmp_path / "different" / "output", {"summary.csv": "a,b\n1,3\n"})

    report = build_comparison_reports(
        ("PiWind 2.4.9", tmp_path / "fastest"),
        [("PiWind 2.5.6", tmp_path / "same"), ("PiWind 2.3.3", tmp_path / "different")],
    )

    assert report == {
        "reference": "PiWind 2.4.9",
        "status": "fail",
        "comparisons": [
            {"target": "PiWind 2.5.6", "status": "pass", "different_files": []},
            {"target": "PiWind 2.3.3", "status": "fail", "different_files": ["summary.csv"]},
        ],
    }


def test_build_comparison_reports_passes_only_when_every_target_matches(tmp_path):
    _write(tmp_path / "fastest" / "output", {"summary.csv": "a,b\n1,2\n"})
    _write(tmp_path / "other" / "output", {"summary.csv": "a,b\n1,2\n"})

    report = build_comparison_reports(("PiWind 2.4.9", tmp_path / "fastest"), [("PiWind 2.5.6", tmp_path / "other")])

    assert report["status"] == "pass"


def test_build_comparison_reports_handles_a_single_target(tmp_path):
    _write(tmp_path / "fastest" / "output", {"summary.csv": "a,b\n1,2\n"})
    _write(tmp_path / "other" / "output", {"summary.csv": "a,b\n1,3\n"})

    report = build_comparison_reports(("PiWind 2.4.9", tmp_path / "fastest"), [("PiWind 2.5.6", tmp_path / "other")])

    assert report["comparisons"] == [{"target": "PiWind 2.5.6", "status": "fail", "different_files": ["summary.csv"]}]


def test_build_comparison_reports_passes_with_nothing_to_compare(tmp_path):
    """Nothing to compare can't fail; main skips the comparison entirely in that case."""
    _write(tmp_path / "fastest" / "output", {"summary.csv": "a,b\n1,2\n"})

    report = build_comparison_reports(("PiWind 2.4.9", tmp_path / "fastest"), [])

    assert report == {"reference": "PiWind 2.4.9", "status": "pass", "comparisons": []}


def test_build_comparison_reports_raises_when_a_target_has_no_output(tmp_path):
    _write(tmp_path / "fastest" / "output", {"summary.csv": "a,b\n1,2\n"})

    with pytest.raises(OasisAlpacaError):
        build_comparison_reports(("PiWind 2.4.9", tmp_path / "fastest"), [("PiWind 2.5.6", tmp_path / "missing")])


def test_build_comparison_reports_respects_custom_tolerance(tmp_path):
    _write(tmp_path / "fastest" / "output", {"summary.csv": "a,b\n1,2.0\n"})
    _write(tmp_path / "other" / "output", {"summary.csv": "a,b\n1,2.001\n"})

    report = build_comparison_reports(
        ("PiWind 2.4.9", tmp_path / "fastest"), [("PiWind 2.5.6", tmp_path / "other")], relative_tolerance=0.01
    )

    assert report["status"] == "pass"


def test_format_comparison_reports_names_the_reference_and_every_target():
    report = {
        "reference": "PiWind 2.4.9",
        "status": "fail",
        "comparisons": [
            {"target": "PiWind 2.5.6", "status": "pass", "different_files": []},
            {"target": "PiWind 2.3.3", "status": "fail", "different_files": ["summary.csv"]},
        ],
    }
    assert format_comparison_reports(report) == (
        "Output comparison against PiWind 2.4.9:\n"
        "\n"
        "PiWind 2.5.6:\n"
        "PASS:\n"
        "Outputs identical\n"
        "\n"
        "PiWind 2.3.3:\n"
        "FAIL:\n"
        "Files different:\n"
        "- summary.csv"
    )


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


def test_csv_files_with_the_same_row_count_but_different_columns_are_different(tmp_path):
    """A row that gained or lost a column is a real difference, not a value to compare."""
    reference = tmp_path / "reference"
    target = tmp_path / "target"
    _write(reference, {"summary.csv": "a,b\n1,2\n"})
    _write(target, {"summary.csv": "a,b,c\n1,2,3\n"})

    assert compare_output_dirs(reference, target) == ["summary.csv"]
