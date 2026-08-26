from alpaca.benchmark.timing import build_timing_table, fastest_result, format_timing_table, green, sort_results_by_speed
from alpaca.benchmark.comparison import format_comparison_reports
from pathlib import Path

REPORT_FILENAME = "benchmark_report.txt"


def run_name(result):
    """Name a run as it appears throughout the report.

    Args:
        result: One entry as returned by run_benchmark_targets.

    Returns:
        str: '{model} {version}', e.g. 'PiWind 2.5.6'.
    """
    return f"{result['model']} {result['version']}"


def format_runtime(runtime_seconds):
    """Format a run's runtime for the report's run summary.

    Args:
        runtime_seconds: Runtime in seconds, or None when a stored baseline has no
            recorded performance metrics to read a runtime from.

    Returns:
        str: e.g. '210s', or 'runtime unknown' when there's no runtime to show.
    """
    return "runtime unknown" if runtime_seconds is None else f"{runtime_seconds}s"


def build_report_text(results, comparison_report, skip_reason="at least one target failed", colour=False):
    """Build a single, human-readable report combining every target's timings and,
    where available, their output comparison.

    Every run is a peer, so the report is ordered by speed rather than by config: the run
    summary lists the quickest first, and the timing table's columns run left to right from
    quickest to slowest, with any run that couldn't be ranked (failed, or a stored baseline
    with no recorded runtime) last. A benchmark of two targets and one of five read the same
    way.

    Args:
        results: list[dict] as returned by run_benchmark_targets, one entry per target,
            each with 'model', 'version', 'status', 'runtime_seconds' and 'step_timings'.
            Targets taken from a stored S3 baseline appear here too, so they're timed and
            compared exactly like a run that just executed.
        comparison_report: dict from build_comparison_reports, or None if comparison was
            skipped.
        skip_reason: Why comparison_report is None, e.g. "at least one target failed" or
            "only one target succeeded". Ignored when comparison_report is set.
        colour: Whether to highlight the quickest run overall, and the quickest run of each
            step, in green. Left off for the saved report, which is read as plain text.

    Returns:
        str: The full report text: a run summary line per target quickest first, a
            step-by-step timing table with a column per target, and the output comparison
            (or a note explaining why it was skipped).
    """
    ordered = sort_results_by_speed(results)
    fastest = fastest_result(results)

    lines = ["Benchmark Report", "=" * len("Benchmark Report"), "", "Runs:"]
    for result in ordered:
        line = f"- {run_name(result)}: {result['status']} ({format_runtime(result['runtime_seconds'])})"
        lines.append(green(line) if colour and result is fastest else line)
    lines.append("")

    successful = [result for result in ordered if result["status"] == "success"]
    if fastest is not None and len(successful) > 1:
        lines.append("Step timings (quickest run first, left to right):")
        rows = build_timing_table([(run_name(result), result["step_timings"]) for result in successful])
        names = [run_name(result) for result in successful]
        lines.append(format_timing_table(names, rows, colour) if rows else "No timing data available.")
        lines.append("")

    if comparison_report is not None:
        lines.append(format_comparison_reports(comparison_report))
    else:
        lines.append(f"Output comparison skipped: {skip_reason}.")

    return "\n".join(lines)


def write_report(report_text, result_directory):
    """Write the benchmark report to a file alongside the targets' result directories.

    Args:
        report_text: Text built by build_report_text.
        result_directory: The shared parent directory every target's RESULT_DIRECTORY
            subfolder lives under.

    Returns:
        Path: Where the report was written.
    """
    report_path = Path(result_directory) / REPORT_FILENAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text)
    return report_path
