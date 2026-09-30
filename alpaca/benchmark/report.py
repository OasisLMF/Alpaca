from alpaca.benchmark.timing import build_timing_table, fastest_result, format_timing_table, green, sort_results_by_speed
from alpaca.benchmark.comparison import format_comparison_reports
from alpaca.benchmark.scripts import group_name
from pathlib import Path

REPORT_FILENAME = "benchmark_report.txt"


def run_name(result):
    """Name a run as it appears throughout the report.

    Args:
        result: One entry as returned by run_benchmark_targets.

    Returns:
        str: '{model} {version}', e.g. 'PiWind 2.5.6', or '{model} {test} {version}' (e.g.
            'PiWind test_1 2.5.6') when the run is one of a TESTS benchmark's.
    """
    return f"{group_name(result['model'], result['test'])} {result['version']}"


def format_runtime(runtime_seconds):
    """Format a run's runtime for the report's run summary.

    Args:
        runtime_seconds: Runtime in seconds, or None when a stored baseline has no
            recorded performance metrics to read a runtime from.

    Returns:
        str: e.g. '210s', or 'runtime unknown' when there's no runtime to show.
    """
    return "runtime unknown" if runtime_seconds is None else f"{runtime_seconds}s"


def _group_results(results):
    """Group results by model and test (see group_name), preserving first-seen order.

    Args:
        results: list[dict] as returned by run_benchmark_targets.

    Returns:
        list[tuple[str, list[dict]]]: (group name, group_results) per distinct model and
            test, in the order each group's first result appears in results.
    """
    order = []
    groups = {}
    for result in results:
        name = group_name(result["model"], result["test"])
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append(result)
    return [(name, groups[name]) for name in order]


def build_report_text(results, comparison_groups, colour=False):
    """Build a single, human-readable report combining every target's timings and,
    where available, their output comparison.

    Every run is a peer within its own group (model and test, see group_name), so each
    group's section is ordered by speed rather than by config: the run summary lists each
    group's targets quickest first, and a group's timing table columns run left to right
    from quickest to slowest, with any run that couldn't be ranked (failed, or a stored
    baseline with no recorded runtime) last. Comparison - both timing and output - is scoped
    per group (see alpaca.benchmark.main._compare_targets): a group's targets are only ever
    compared against other targets of that *same* model and test (different
    OASISLMF_VERSIONS/BRANCHES of it), never against a different model's or test's targets,
    since those are expected to produce different output and take a different amount of
    time - that's not a regression, just a different thing. A benchmark spanning only one
    group (still the most common case) reads as a single flat report, with no redundant
    group heading.

    Args:
        results: list[dict] as returned by run_benchmark_targets, one entry per target,
            each with 'model', 'version', 'status', 'runtime_seconds' and 'step_timings'.
            Targets taken from a stored S3 baseline appear here too, so they're timed and
            compared exactly like a run that just executed.
        comparison_groups: list[dict] from alpaca.benchmark.main._compare_targets, one
            {'group', 'report', 'skip_reason'} entry per distinct model and test. 'report' is
            a dict from build_comparison_reports, or None if comparison was skipped for that
            group (see 'skip_reason' then).
        colour: Whether to highlight the quickest run of each group, and the quickest run of
            each step, in green. Left off for the saved report, which is read as plain text.

    Returns:
        str: The full report text: a run summary line per target (quickest first within its
            group), then one section per group with its own step-by-step timing table and
            output comparison (or a note explaining why either was skipped).
    """
    result_groups = _group_results(results)
    multi_group = len(result_groups) > 1
    comparison_by_group = {group["group"]: group for group in comparison_groups}

    lines = ["Benchmark Report", "=" * len("Benchmark Report"), "", "Runs:"]
    for _, group_results in result_groups:
        ordered = sort_results_by_speed(group_results)
        fastest = fastest_result(group_results)
        for result in ordered:
            line = f"- {run_name(result)}: {result['status']} ({format_runtime(result['runtime_seconds'])})"
            lines.append(green(line) if colour and result is fastest else line)
    lines.append("")

    sections = []
    for name, group_results in result_groups:
        section = []
        if multi_group:
            section.append(name)
            section.append("-" * len(name))

        successful = [result for result in group_results if result["status"] == "success"]
        fastest = fastest_result(group_results)
        if fastest is not None and len(successful) > 1:
            ordered_successful = [result for result in sort_results_by_speed(group_results) if result["status"] == "success"]
            section.append("Step timings (quickest run first, left to right):")
            rows = build_timing_table([(run_name(result), result["step_timings"]) for result in ordered_successful])
            names = [run_name(result) for result in ordered_successful]
            section.append(format_timing_table(names, rows, colour) if rows else "No timing data available.")
            section.append("")

        comparison = comparison_by_group.get(name)
        if comparison is not None and comparison["report"] is not None:
            section.append(format_comparison_reports(comparison["report"]))
        else:
            skip_reason = comparison["skip_reason"] if comparison is not None else "no comparison data for this group"
            section.append(f"Output comparison skipped: {skip_reason}.")

        sections.append(section)

    for index, section in enumerate(sections):
        lines.extend(section)
        if index < len(sections) - 1:
            lines.append("")

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
