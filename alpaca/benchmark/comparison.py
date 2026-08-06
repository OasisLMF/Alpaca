from alpaca.exceptions import OasisAlpacaError
from pathlib import Path

import filecmp


def find_output_dir(run_directory):
    """Locate the 'output' directory produced by an OasisLMF model run.

    OasisLMF nests a run's output under a generated 'losses-<timestamp>' directory (e.g.
    RESULT_DIRECTORY/losses-20260804135955/output), so this walks the downloaded run
    directory to find it rather than assuming a fixed depth.

    Args:
        run_directory: Local directory a benchmark target's results were downloaded to.

    Returns:
        Path: The 'output' directory found under run_directory.

    Raises:
        OasisAlpacaError: If no 'output' directory is found under run_directory.
    """
    for path in sorted(Path(run_directory).rglob("output")):
        if path.is_dir():
            return path
    raise OasisAlpacaError(f"No 'output' directory found under {run_directory}")


def compare_output_dirs(baseline_dir, comparison_dir):
    """Compare every file in two OasisLMF run output directories.

    Args:
        baseline_dir: The baseline target's output directory (see find_output_dir).
        comparison_dir: The comparison target's output directory.

    Returns:
        list[str]: Sorted names of files that differ between the two directories, either
            because their content doesn't match or because a file is present in only one
            of them. Empty if every file is identical.
    """
    baseline_files = {path.name: path for path in Path(baseline_dir).iterdir() if path.is_file()}
    comparison_files = {path.name: path for path in Path(comparison_dir).iterdir() if path.is_file()}

    different = set(baseline_files) ^ set(comparison_files)
    for name in set(baseline_files) & set(comparison_files):
        if not filecmp.cmp(baseline_files[name], comparison_files[name], shallow=False):
            different.add(name)

    return sorted(different)


def build_comparison_report(baseline_result_directory, comparison_result_directory):
    """Compare a benchmark's baseline and comparison output directories.

    Args:
        baseline_result_directory: Local directory the baseline target's results were
            downloaded to (a target's RESULT_DIRECTORY from build_model_run_configs).
        comparison_result_directory: Local directory the comparison target's results were
            downloaded to.

    Returns:
        dict: {'status': 'pass' or 'fail', 'different_files': sorted list of file names
            that differ between the two runs' output directories, empty when 'pass'}.

    Raises:
        OasisAlpacaError: If either directory has no 'output' directory under it.
    """
    baseline_output = find_output_dir(baseline_result_directory)
    comparison_output = find_output_dir(comparison_result_directory)
    different_files = compare_output_dirs(baseline_output, comparison_output)
    return {
        "status": "pass" if not different_files else "fail",
        "different_files": different_files,
    }


def format_comparison_report(report):
    """Format a comparison report for display.

    Args:
        report: dict as returned by build_comparison_report, with 'status' and
            'different_files' keys.

    Returns:
        str: 'PASS:\\nOutputs identical' when the outputs match, otherwise
            'FAIL:\\nFiles different:' followed by a bulleted list of file names.
    """
    if report["status"] == "pass":
        return "PASS:\nOutputs identical"
    lines = ["FAIL:", "Files different:"]
    lines.extend(f"- {name}" for name in report["different_files"])
    return "\n".join(lines)
