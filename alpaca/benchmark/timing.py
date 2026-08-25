from pathlib import Path
from termcolor import colored

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


def green(text):
    """Mark text as a winning value in the report.

    Args:
        text: Text to colour.

    Returns:
        str: The text in green, or unchanged when the output can't take colour (piped to a
            file, or NO_COLOR set), which termcolor decides.
    """
    return colored(text, "green")


def sort_results_by_speed(results):
    """Order runs fastest first, so a report reads best-to-worst.

    Args:
        results: list[dict] as returned by run_benchmark_targets, one entry per target.

    Returns:
        list[dict]: The runs that can be ranked, ordered by ascending runtime_seconds,
            followed by the ones that can't (failed, or a stored baseline with no recorded
            runtime) in their original order. Ties keep their original order too.
    """
    ranked, unranked = [], []
    for result in results:
        rankable = result["status"] == "success" and result["runtime_seconds"] is not None
        (ranked if rankable else unranked).append(result)
    return sorted(ranked, key=lambda result: result["runtime_seconds"]) + unranked


def fastest_result(results):
    """Pick the fastest successful run, which every other run is reported relative to.

    Args:
        results: list[dict] as returned by run_benchmark_targets, one entry per target.

    Returns:
        dict or None: The successful result with the lowest runtime_seconds, or None if no
            target succeeded with a known runtime (a stored baseline with no performance
            metrics has none to rank). Ties keep the earlier target, so the reference is
            stable.
    """
    successful = [
        result for result in results
        if result["status"] == "success" and result["runtime_seconds"] is not None
    ]
    if not successful:
        return None
    return min(successful, key=lambda result: result["runtime_seconds"])


def build_timing_table(runs):
    """Line every run's step timings up in one row per step, for side-by-side reporting.

    Args:
        runs: list[tuple] of (name, step_timings) in the order their columns should appear,
            i.e. fastest run first (see sort_results_by_speed). step_timings is a dict as
            returned by resolve_model_runtime/parse_step_timings.

    Returns:
        list[dict]: One entry per step name seen in any run, sorted alphabetically by step,
            each with 'step', 'seconds' (one value per run, in the same order as runs, None
            where that run had no timing for this step) and 'fastest_seconds' (the lowest of
            them, or None when no run timed this step).
    """
    steps = sorted({step for _, step_timings in runs for step in step_timings})
    rows = []
    for step in steps:
        seconds = [step_timings.get(step) for _, step_timings in runs]
        timed = [value for value in seconds if value is not None]
        rows.append({"step": step, "seconds": seconds, "fastest_seconds": min(timed) if timed else None})
    return rows


def format_timing_table(names, rows, colour=False):
    """Format a timing table as a human-readable, aligned table.

    Args:
        names: One column name per run, in the same order as the rows' 'seconds' values.
        rows: list of dicts as returned by build_timing_table.
        colour: Whether to highlight the quickest run of each step in green. Left off for
            the report file, which is read as plain text.

    Returns:
        str: A table with one row per step and one column per run, each cell showing that
            run's duration and, unless it was the quickest, how far behind the quickest it
            was ('n/a' where a step is missing from a run). Empty string if rows is empty.
    """
    if not rows:
        return ""

    headers = ["Step", *names]

    def format_cell(value, fastest_seconds):
        if value is None:
            return "n/a"
        if fastest_seconds in (None, 0) or value == fastest_seconds:
            return f"{value:.2f}"
        return f"{value:.2f} ({(value - fastest_seconds) / fastest_seconds * 100:+.1f}%)"

    table_rows = [
        [row["step"], *(format_cell(value, row["fastest_seconds"]) for value in row["seconds"])]
        for row in rows
    ]

    widths = [max(len(header), *(len(row[index]) for row in table_rows)) for index, header in enumerate(headers)]

    def pad(cell, index):
        return cell.ljust(widths[index]) if index == 0 else cell.rjust(widths[index])

    lines = ["  ".join(pad(header, index) for index, header in enumerate(headers))]
    lines.append("  ".join(pad("-" * width, index) for index, width in enumerate(widths)))
    for row, cells in zip(rows, table_rows):
        def is_quickest(index, row=row):
            return index > 0 and row["fastest_seconds"] is not None and row["seconds"][index - 1] == row["fastest_seconds"]

        padded = [pad(cell, index) for index, cell in enumerate(cells)]
        lines.append("  ".join(
            green(cell) if colour and is_quickest(index) else cell for index, cell in enumerate(padded)
        ))
    return "\n".join(lines)
