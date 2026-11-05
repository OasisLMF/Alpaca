from pathlib import Path

import csv

MEMORY_FILENAME = "memory.csv"
KIB_PER_GIB = 1024 ** 2


def find_memory_file(run_directory):
    """Locate the memory.csv sampled on the instance while a model ran.

    Args:
        run_directory: Local directory a benchmark target's results were downloaded to.

    Returns:
        Path or None: The most recently modified 'memory.csv' found under run_directory, or
            None if none exists (e.g. a run, or a stored baseline, from before memory was
            sampled).
    """
    memory_files = [path for path in Path(run_directory).rglob(MEMORY_FILENAME) if path.is_file()]
    if not memory_files:
        return None
    return max(memory_files, key=lambda path: path.stat().st_mtime)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def summarise_memory(run_directory):
    """Summarise the memory a model run used, from the samples taken on its instance.

    See alpaca.model.commands.memory_sampled for how the samples are taken. 'used' is the
    whole instance's, so it includes the operating system's own share, which is the same for
    two runs on the same instance type and AMI (see alpaca.benchmark.manifest).

    Args:
        run_directory: Local directory a benchmark target's results were downloaded to.

    Returns:
        dict or None: 'peak_used_kib' (the highest memory use sampled), 'total_kib' (the
            instance's memory), 'peak_swap_used_kib', 'oom_kills' (processes the kernel killed
            for running out of memory while the run went on, 0 when the kernel doesn't count
            them) and 'samples'. None when there's no memory.csv or it has no complete sample,
            e.g. the line being written when the sampler was stopped is skipped.
    """
    memory_file = find_memory_file(run_directory)
    if memory_file is None:
        return None

    rows = []
    with open(memory_file, newline="") as f:
        for row in csv.DictReader(f):
            used, total = _int_or_none(row.get("used_kib")), _int_or_none(row.get("total_kib"))
            swap = _int_or_none(row.get("swap_used_kib"))
            if used is None or total is None or swap is None:
                continue
            rows.append((total, used, swap, _int_or_none(row.get("oom_kills"))))
    if not rows:
        return None

    oom_counts = [oom for *_, oom in rows if oom is not None]
    return {
        "peak_used_kib": max(used for _, used, _, _ in rows),
        "total_kib": rows[0][0],
        "peak_swap_used_kib": max(swap for _, _, swap, _ in rows),
        "oom_kills": oom_counts[-1] - oom_counts[0] if oom_counts else 0,
        "samples": len(rows),
    }


def format_size(kib):
    """Format a KiB figure as GiB to one decimal place, e.g. '9.8 GiB', or as MiB below 0.1 GiB."""
    if kib < KIB_PER_GIB / 10:
        return f"{kib / 1024:.0f} MiB"
    return f"{kib / KIB_PER_GIB:.1f} GiB"


def format_memory(memory):
    """Format a run's memory summary for the report's run summary.

    Args:
        memory: dict from summarise_memory.

    Returns:
        str: e.g. 'peak memory 9.8 GiB of 15.3 GiB'.
    """
    return f"peak memory {format_size(memory['peak_used_kib'])} of {format_size(memory['total_kib'])}"


def memory_warnings(memory):
    """List anything in a run's memory summary that would have slowed it down or broken it.

    Args:
        memory: dict from summarise_memory, or None.

    Returns:
        list[str]: e.g. 'used 1.2 GiB of swap' or 'the kernel killed 1 process for running out
            of memory', empty when there's nothing to warn about.
    """
    if not memory:
        return []
    warnings = []
    if memory["peak_swap_used_kib"] > 0:
        warnings.append(f"used {format_size(memory['peak_swap_used_kib'])} of swap")
    if memory["oom_kills"] > 0:
        processes = "process" if memory["oom_kills"] == 1 else "processes"
        warnings.append(f"the kernel killed {memory['oom_kills']} {processes} for running out of memory")
    return warnings
