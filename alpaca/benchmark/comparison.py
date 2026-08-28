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
    """Read COMPARISON_TOLERANCE from a benchmark config and check it makes sense.

    The value is already a float by the time it gets here, as alpaca.config.load_config types
    every declared key, so this only supplies the default and rejects a tolerance that can't
    mean anything.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        float: The configured relative tolerance, or DEFAULT_RELATIVE_TOLERANCE if unset. A
            configured zero is kept, meaning outputs have to match exactly.

    Raises:
        OasisAlpacaConfigError: If COMPARISON_TOLERANCE is negative.
    """
    tolerance = config.get("COMPARISON_TOLERANCE")
    if tolerance is None:
        return DEFAULT_RELATIVE_TOLERANCE
    if tolerance < 0:
        raise OasisAlpacaConfigError(f"COMPARISON_TOLERANCE must not be negative, got '{tolerance}'")
    return tolerance


def _file_checksum(path):
    """Compute the SHA-256 checksum of a file's contents.

    Only used to tell whether two output files are byte-identical, so the choice of hash
    doesn't matter much, but SHA-256 is available on FIPS-enabled hosts where MD5 isn't.

    Args:
        path: Path to the file.

    Returns:
        str: Hex digest of the file's contents.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHECKSUM_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _values_match(reference_value, target_value, relative_tolerance):
    """Compare two CSV cell values, allowing numeric tolerance where both parse as floats.

    Args:
        reference_value: Cell value (string) from the reference run's CSV.
        target_value: Cell value (string) from the compared run's CSV.
        relative_tolerance: Relative tolerance passed to math.isclose for numeric cells.

    Returns:
        bool: True if the values are identical, or both parse as floats within tolerance.
            Non-numeric cells (IDs, labels, headers) must match exactly.
    """
    if reference_value == target_value:
        return True
    try:
        reference_number = float(reference_value)
        target_number = float(target_value)
    except ValueError:
        return False
    return math.isclose(reference_number, target_number, rel_tol=relative_tolerance, abs_tol=ABSOLUTE_TOLERANCE)


def _csv_files_match(reference_path, target_path, relative_tolerance):
    """Compare two CSV files row-by-row and cell-by-cell within a numeric tolerance.

    Args:
        reference_path: Path to the reference run's CSV file.
        target_path: Path to the compared run's CSV file.
        relative_tolerance: Relative tolerance for numeric cells, see _values_match.

    Returns:
        bool: True if both files have the same number of rows and every cell matches.
    """
    with open(reference_path, newline="") as reference_file, open(target_path, newline="") as target_file:
        reference_rows = list(csv.reader(reference_file))
        target_rows = list(csv.reader(target_file))

    if len(reference_rows) != len(target_rows):
        return False

    for reference_row, target_row in zip(reference_rows, target_rows):
        if len(reference_row) != len(target_row):
            return False
        if not all(_values_match(b, c, relative_tolerance) for b, c in zip(reference_row, target_row)):
            return False
    return True


def compare_output_dirs(reference_dir, target_dir, relative_tolerance=DEFAULT_RELATIVE_TOLERANCE):
    """Compare every file in two OasisLMF run output directories.

    Each pair of same-named files is checksummed first: a matching MD5 means the files are
    byte-identical, so it's taken as a match without reading them again. Only on a checksum
    mismatch do CSV files get parsed and compared cell-by-cell with numeric tolerance (see
    _values_match) to tell a real difference apart from run-to-run rounding noise; every
    other file with a checksum mismatch is reported as different outright.

    Args:
        reference_dir: The reference target's output directory (see find_output_dir).
        target_dir: The compared target's output directory.
        relative_tolerance: Relative tolerance for numeric CSV cells, see resolve_relative_tolerance.

    Returns:
        list[str]: Sorted names of files that differ between the two directories, either
            because their content doesn't match (beyond tolerance, for CSVs) or because a
            file is present in only one of them. Empty if every file matches.
    """
    reference_files = {path.name: path for path in Path(reference_dir).iterdir() if path.is_file()}
    target_files = {path.name: path for path in Path(target_dir).iterdir() if path.is_file()}

    different = set(reference_files) ^ set(target_files)
    for name in set(reference_files) & set(target_files):
        reference_path, target_path = reference_files[name], target_files[name]
        if _file_checksum(reference_path) == _file_checksum(target_path):
            continue

        matches = name.lower().endswith(".csv") and _csv_files_match(reference_path, target_path, relative_tolerance)
        if not matches:
            different.add(name)

    return sorted(different)


def build_comparison_report(reference_result_directory, target_result_directory, relative_tolerance=DEFAULT_RELATIVE_TOLERANCE):
    """Compare one benchmark target's output directory against the reference target's.

    Args:
        reference_result_directory: Local directory the reference target's results were
            downloaded to (a target's RESULT_DIRECTORY from build_benchmark_targets).
        target_result_directory: Local directory the compared target's results were
            downloaded to.
        relative_tolerance: Relative tolerance for numeric CSV cells, see resolve_relative_tolerance.

    Returns:
        dict: {'status': 'pass' or 'fail', 'different_files': sorted list of file names
            that differ between the two runs' output directories, empty when 'pass'}.

    Raises:
        OasisAlpacaError: If either directory has no 'output' directory under it.
    """
    reference_output = find_output_dir(reference_result_directory)
    target_output = find_output_dir(target_result_directory)
    different_files = compare_output_dirs(reference_output, target_output, relative_tolerance)
    return {
        "status": "pass" if not different_files else "fail",
        "different_files": different_files,
    }


def build_comparison_reports(reference, targets, relative_tolerance=DEFAULT_RELATIVE_TOLERANCE):
    """Compare every other benchmark target's output against the reference target's.

    Args:
        reference: (name, result_directory) for the target every other one is compared
            against, i.e. the fastest run.
        targets: List of (name, result_directory) for the targets being compared.
        relative_tolerance: Relative tolerance for numeric CSV cells, see resolve_relative_tolerance.

    Returns:
        dict: {'reference': the reference target's name, 'status': 'pass' only when every
            target matches the reference, 'comparisons': one entry per target with its
            'target' name plus the 'status'/'different_files' from build_comparison_report}.

    Raises:
        OasisAlpacaError: If any of the directories has no 'output' directory under it.
    """
    reference_name, reference_directory = reference
    comparisons = [
        {"target": name, **build_comparison_report(reference_directory, directory, relative_tolerance)}
        for name, directory in targets
    ]
    return {
        "reference": reference_name,
        "status": "pass" if all(comparison["status"] == "pass" for comparison in comparisons) else "fail",
        "comparisons": comparisons,
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


def format_comparison_reports(report):
    """Format a multi-target comparison report for display.

    Args:
        report: dict as returned by build_comparison_reports, with 'reference', 'status'
            and 'comparisons' keys.

    Returns:
        str: A heading naming the reference run, then each compared target's name followed
            by its own pass/fail block (see format_comparison_report). The heading doesn't
            claim the reference was the quickest, since it stands in as one when no target
            reported a runtime; the report's run summary and timing table show the speeds.
    """
    lines = [f"Output comparison against {report['reference']}:"]
    for comparison in report["comparisons"]:
        lines.append("")
        lines.append(f"{comparison['target']}:")
        lines.append(format_comparison_report(comparison))
    return "\n".join(lines)
