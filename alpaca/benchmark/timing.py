from pathlib import Path

import re

COMPLETED_LINE_PATTERN = re.compile(r"COMPLETED:\s*(?P<step>\S+)\s+in\s+(?P<seconds>[\d.]+)s")
MODEL_RUNTIME_STEP = "oasislmf.manager.interface"


def find_result_file(run_directory):
    """Locate the result.txt file capturing an OasisLMF model run's own timing output.

    Args:
        run_directory: Local directory a benchmark target's results were downloaded to.

    Returns:
        Path or None: The most recently modified 'result.txt' found under run_directory, or
            None if none exists (e.g. an older Alpaca version's run, or one that failed
            before 'oasislmf model run' produced any output).
    """
    result_files = [path for path in Path(run_directory).rglob("result.txt") if path.is_file()]
    if not result_files:
        return None
    return max(result_files, key=lambda path: path.stat().st_mtime)


def parse_step_timings(result_file):
    """Parse OasisLMF's 'COMPLETED: <step> in <seconds>s' lines from a model run's output.

    Args:
        result_file: Path to a result.txt file (see find_result_file).

    Returns:
        dict[str, float]: Step name (e.g. 'oasislmf.manager.interface',
            'execution.runner.run') to duration in seconds. Empty if no COMPLETED lines
            are found.
    """
    text = Path(result_file).read_text(errors="replace")
    return {
        match.group("step"): float(match.group("seconds"))
        for match in COMPLETED_LINE_PATTERN.finditer(text)
    }


def resolve_model_runtime(run_directory, fallback_runtime_seconds):
    """Resolve a target's model-only runtime from its result.txt, where available.

    The wall-clock time around a benchmark target includes EC2 startup, model upload and
    results download, not just the model run itself, so it overstates how long the model
    actually took. OasisLMF's own 'oasislmf.manager.interface' COMPLETED line is the model
    run's true duration; this falls back to the wall-clock runtime when result.txt is
    missing or has no recognisable timing lines, so a target still reports something rather
    than raising.

    Args:
        run_directory: Local directory a benchmark target's results were downloaded to.
        fallback_runtime_seconds: Wall-clock runtime to fall back to.

    Returns:
        tuple[float, dict[str, float]]: (runtime_seconds, step_timings). step_timings is
            empty when falling back to the wall-clock runtime.
    """
    result_file = find_result_file(run_directory)
    if result_file is None:
        return fallback_runtime_seconds, {}

    step_timings = parse_step_timings(result_file)
    if MODEL_RUNTIME_STEP not in step_timings:
        return fallback_runtime_seconds, step_timings

    return step_timings[MODEL_RUNTIME_STEP], step_timings


def build_timing_comparison(baseline_step_timings, comparison_step_timings):
    """Pair up baseline and comparison step timings for side-by-side reporting.

    Args:
        baseline_step_timings: dict as returned by resolve_model_runtime/parse_step_timings
            for the baseline target.
        comparison_step_timings: Same, for the comparison target.

    Returns:
        list[dict]: One entry per step name seen in either run, sorted alphabetically by
            step, each with 'step', 'baseline_seconds' (float or None if that run had no
            timing for this step), 'comparison_seconds' (float or None), 'delta_seconds'
            (comparison minus baseline, or None if either side is missing) and
            'delta_percent' (delta_seconds as a percentage of baseline_seconds, or None if
            either side is missing or baseline_seconds is 0).
    """
    steps = sorted(set(baseline_step_timings) | set(comparison_step_timings))
    rows = []
    for step in steps:
        baseline_seconds = baseline_step_timings.get(step)
        comparison_seconds = comparison_step_timings.get(step)

        delta_seconds = None
        delta_percent = None
        if baseline_seconds is not None and comparison_seconds is not None:
            delta_seconds = comparison_seconds - baseline_seconds
            if baseline_seconds != 0:
                delta_percent = delta_seconds / baseline_seconds * 100

        rows.append({
            "step": step,
            "baseline_seconds": baseline_seconds,
            "comparison_seconds": comparison_seconds,
            "delta_seconds": delta_seconds,
            "delta_percent": delta_percent,
        })
    return rows


def format_timing_comparison(rows):
    """Format a timing comparison as a human-readable, aligned table.

    Args:
        rows: list of dicts as returned by build_timing_comparison.

    Returns:
        str: A table with one row per step, columns for the baseline/comparison durations
            and the delta between them ('n/a' where a step is missing from either run).
            Empty string if rows is empty.
    """
    if not rows:
        return ""

    headers = ("Step", "Baseline (s)", "Comparison (s)", "Delta (s)", "Delta (%)")

    def format_seconds(value):
        return f"{value:.2f}" if value is not None else "n/a"

    def format_delta_seconds(value):
        return f"{value:+.2f}" if value is not None else "n/a"

    def format_delta_percent(value):
        return f"{value:+.1f}%" if value is not None else "n/a"

    table_rows = [
        (
            row["step"],
            format_seconds(row["baseline_seconds"]),
            format_seconds(row["comparison_seconds"]),
            format_delta_seconds(row["delta_seconds"]),
            format_delta_percent(row["delta_percent"]),
        )
        for row in rows
    ]

    widths = [max(len(header), *(len(row[i]) for row in table_rows)) for i, header in enumerate(headers)]

    def format_row(cells):
        return "  ".join(cell.ljust(widths[i]) if i == 0 else cell.rjust(widths[i]) for i, cell in enumerate(cells))

    lines = [format_row(headers), format_row(["-" * width for width in widths])]
    lines.extend(format_row(row) for row in table_rows)
    return "\n".join(lines)
