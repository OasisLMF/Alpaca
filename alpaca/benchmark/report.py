from alpaca.benchmark.timing import build_timing_comparison, format_timing_comparison
from alpaca.benchmark.comparison import format_comparison_report
from pathlib import Path

REPORT_FILENAME = "benchmark_report.txt"


def build_report_text(results, comparison_report):
    """Build a single, human-readable report combining both targets' timings and,
    where available, their output comparison.

    Args:
        results: list[dict] as returned by run_benchmark_targets, one entry per target,
            each with 'model', 'version', 'status', 'runtime_seconds' and 'step_timings'.
        comparison_report: dict from build_comparison_report, or None if comparison was
            skipped (e.g. because a target failed).

    Returns:
        str: The full report text: a run summary line per target, a step-by-step timing
            comparison table when both targets succeeded, and the output comparison
            (or a note that it was skipped).
    """
    lines = ["Benchmark Report", "=" * len("Benchmark Report"), "", "Runs:"]
    for result in results:
        lines.append(f"- {result['model']} {result['version']}: {result['status']} ({result['runtime_seconds']}s)")
    lines.append("")

    if len(results) == 2 and all(result["status"] == "success" for result in results):
        baseline, comparison = results
        lines.append(f"Timing comparison ({baseline['version']} vs {comparison['version']}):")
        rows = build_timing_comparison(baseline["step_timings"], comparison["step_timings"])
        lines.append(format_timing_comparison(rows) if rows else "No timing data available.")
        lines.append("")

    if comparison_report is not None:
        lines.append(format_comparison_report(comparison_report))
    else:
        lines.append("Output comparison skipped: at least one target failed.")

    return "\n".join(lines)


def write_report(report_text, result_directory):
    """Write the benchmark report to a file alongside the targets' result directories.

    Args:
        report_text: Text built by build_report_text.
        result_directory: The shared parent directory both targets' RESULT_DIRECTORY
            subfolders live under.

    Returns:
        Path: Where the report was written.
    """
    report_path = Path(result_directory) / REPORT_FILENAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text)
    return report_path
