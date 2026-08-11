from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from pathlib import Path

import csv
import hashlib
import math

DEFAULT_RELATIVE_TOLERANCE = 1e-6
ABSOLUTE_TOLERANCE = 1e-9
CHECKSUM_CHUNK_SIZE = 65536


def find_output_dir(run_directory):
    """Locate the 'output' directory produced by an OasisLMF model run.

    OasisLMF nests a run's output under a generated 'losses-<timestamp>' directory (e.g.
    RESULT_DIRECTORY/losses-20260804135955/output), so this walks the downloaded run
    directory to find it rather than assuming a fixed depth. RESULT_DIRECTORY isn't cleared
    between benchmark runs, so older 'losses-*' folders from previous attempts may still be
    present; the most recently modified 'output' directory is used, since that's the one the
    run that just finished downloaded into.

    Args:
        run_directory: Local directory a benchmark target's results were downloaded to.

    Returns:
        Path: The most recently modified 'output' directory found under run_directory.

    Raises:
        OasisAlpacaError: If no 'output' directory is found under run_directory.
    """
    output_dirs = [path for path in Path(run_directory).rglob("output") if path.is_dir()]
    if not output_dirs:
        raise OasisAlpacaError(f"No 'output' directory found under {run_directory}")
    return max(output_dirs, key=lambda path: path.stat().st_mtime)


def resolve_relative_tolerance(config):
    """Read and validate COMPARISON_TOLERANCE from a benchmark config.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        float: The configured relative tolerance, or DEFAULT_RELATIVE_TOLERANCE if unset.

    Raises:
        OasisAlpacaConfigError: If COMPARISON_TOLERANCE is set but isn't a non-negative number.
    """
    raw_value = config.get("COMPARISON_TOLERANCE")
    if not raw_value:
        return DEFAULT_RELATIVE_TOLERANCE
    try:
        tolerance = float(raw_value)
    except (TypeError, ValueError):
        raise OasisAlpacaConfigError(f"COMPARISON_TOLERANCE must be a number, got '{raw_value}'")
    if tolerance < 0:
        raise OasisAlpacaConfigError(f"COMPARISON_TOLERANCE must not be negative, got '{raw_value}'")
    return tolerance


def _file_checksum(path):
    """Compute the MD5 checksum of a file's contents.

    Args:
        path: Path to the file.

    Returns:
        str: Hex digest of the file's contents.
    """
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHECKSUM_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _values_match(baseline_value, comparison_value, relative_tolerance):
    """Compare two CSV cell values, allowing numeric tolerance where both parse as floats.

    Args:
        baseline_value: Cell value (string) from the baseline CSV.
        comparison_value: Cell value (string) from the comparison CSV.
        relative_tolerance: Relative tolerance passed to math.isclose for numeric cells.

    Returns:
        bool: True if the values are identical, or both parse as floats within tolerance.
            Non-numeric cells (IDs, labels, headers) must match exactly.
    """
    if baseline_value == comparison_value:
        return True
    try:
        baseline_number = float(baseline_value)
        comparison_number = float(comparison_value)
    except ValueError:
        return False
    return math.isclose(baseline_number, comparison_number, rel_tol=relative_tolerance, abs_tol=ABSOLUTE_TOLERANCE)


def _csv_files_match(baseline_path, comparison_path, relative_tolerance):
    """Compare two CSV files row-by-row and cell-by-cell within a numeric tolerance.

    Args:
        baseline_path: Path to the baseline CSV file.
        comparison_path: Path to the comparison CSV file.
        relative_tolerance: Relative tolerance for numeric cells, see _values_match.

    Returns:
        bool: True if both files have the same number of rows and every cell matches.
    """
    with open(baseline_path, newline="") as baseline_file, open(comparison_path, newline="") as comparison_file:
        baseline_rows = list(csv.reader(baseline_file))
        comparison_rows = list(csv.reader(comparison_file))

    if len(baseline_rows) != len(comparison_rows):
        return False

    for baseline_row, comparison_row in zip(baseline_rows, comparison_rows):
        if len(baseline_row) != len(comparison_row):
            return False
        if not all(_values_match(b, c, relative_tolerance) for b, c in zip(baseline_row, comparison_row)):
            return False
    return True


def compare_output_dirs(baseline_dir, comparison_dir, relative_tolerance=DEFAULT_RELATIVE_TOLERANCE):
    """Compare every file in two OasisLMF run output directories.

    Each pair of same-named files is checksummed first: a matching MD5 means the files are
    byte-identical, so it's taken as a match without reading them again. Only on a checksum
    mismatch do CSV files get parsed and compared cell-by-cell with numeric tolerance (see
    _values_match) to tell a real difference apart from run-to-run rounding noise; every
    other file with a checksum mismatch is reported as different outright.

    Args:
        baseline_dir: The baseline target's output directory (see find_output_dir).
        comparison_dir: The comparison target's output directory.
        relative_tolerance: Relative tolerance for numeric CSV cells, see resolve_relative_tolerance.

    Returns:
        list[str]: Sorted names of files that differ between the two directories, either
            because their content doesn't match (beyond tolerance, for CSVs) or because a
            file is present in only one of them. Empty if every file matches.
    """
    baseline_files = {path.name: path for path in Path(baseline_dir).iterdir() if path.is_file()}
    comparison_files = {path.name: path for path in Path(comparison_dir).iterdir() if path.is_file()}

    different = set(baseline_files) ^ set(comparison_files)
    for name in set(baseline_files) & set(comparison_files):
        baseline_path, comparison_path = baseline_files[name], comparison_files[name]
        if _file_checksum(baseline_path) == _file_checksum(comparison_path):
            continue

        matches = name.lower().endswith(".csv") and _csv_files_match(baseline_path, comparison_path, relative_tolerance)
        if not matches:
            different.add(name)

    return sorted(different)


def build_comparison_report(baseline_result_directory, comparison_result_directory, relative_tolerance=DEFAULT_RELATIVE_TOLERANCE):
    """Compare a benchmark's baseline and comparison output directories.

    Args:
        baseline_result_directory: Local directory the baseline target's results were
            downloaded to (a target's RESULT_DIRECTORY from build_model_run_configs).
        comparison_result_directory: Local directory the comparison target's results were
            downloaded to.
        relative_tolerance: Relative tolerance for numeric CSV cells, see resolve_relative_tolerance.

    Returns:
        dict: {'status': 'pass' or 'fail', 'different_files': sorted list of file names
            that differ between the two runs' output directories, empty when 'pass'}.

    Raises:
        OasisAlpacaError: If either directory has no 'output' directory under it.
    """
    baseline_output = find_output_dir(baseline_result_directory)
    comparison_output = find_output_dir(comparison_result_directory)
    different_files = compare_output_dirs(baseline_output, comparison_output, relative_tolerance)
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
