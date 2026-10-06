from alpaca.inputs import AMI_ID, AWS_REGION, INSTANCE_TYPE
from datetime import datetime, timezone
from pathlib import Path

import json
import logging

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
INPUT_CHECKSUMS_FILENAME = "input_checksums.json"
MANIFEST_FORMAT_VERSION = 1

# What a run's inputs are named in a manifest and its report notes, in the order they're
# reported. 'oasislmf_json' is the file the run was started from; the other two are read out
# of it (see alpaca.model.commands.input_checksum_commands).
INPUT_NAMES = {
    "oasislmf_json": "oasislmf.json",
    "analysis_settings_json": "analysis settings",
    "model_settings_json": "model settings",
}


def build_manifest(target, result_directory, created_at=None, tests_per_instance="separate"):
    """Describe the conditions a benchmark target ran under, for checking like for like later.

    Two runs are only comparable when they ran on the same kind of instance from the same
    image, against the same model inputs. The instance details come from the target's own
    run config, and the input checksums from the input_checksums.json the instance wrote
    before the model ran (see alpaca.model.commands.input_checksum_commands), which was
    downloaded with the rest of the run's results.

    Args:
        target: The target, as returned by alpaca.benchmark.scripts.build_benchmark_targets.
        result_directory: Local directory the target's results were downloaded to.
        created_at: When the run happened, as an ISO 8601 string. Defaults to now (UTC).
        tests_per_instance: 'separate' when the run had its instance to itself, 'shared' when
            it ran in turn with other tests on one instance (see TESTS_PER_INSTANCE).

    Returns:
        dict: The manifest. 'inputs' is empty when the instance never got as far as writing
            its checksums (a run that failed during setup, say).
    """
    run_config = target["run_config"]
    return {
        "format_version": MANIFEST_FORMAT_VERSION,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": target["model"],
        "test": target["test"],
        "oasislmf_version": run_config.get("OASISLMF_VERSION") or None,
        "oasislmf_branch": run_config.get("OASISLMF_BRANCH") or None,
        "instance_type": run_config.get(INSTANCE_TYPE[0]) or INSTANCE_TYPE[2],
        "ami_id": run_config.get(AMI_ID[0]) or AMI_ID[2],
        "aws_region": run_config.get(AWS_REGION[0]) or AWS_REGION[2],
        "tests_per_instance": tests_per_instance,
        "inputs": _read_input_checksums(result_directory),
    }


def write_manifest(target, result_directory, tests_per_instance="separate"):
    """Build a target's manifest and save it as manifest.json in its result directory.

    Args:
        target: The target, as returned by alpaca.benchmark.scripts.build_benchmark_targets.
        result_directory: Local directory the target's results were downloaded to.
        tests_per_instance: 'separate' or 'shared', see build_manifest.

    Returns:
        dict: The manifest that was written (see build_manifest).
    """
    manifest = build_manifest(target, result_directory, tests_per_instance=tests_per_instance)
    path = Path(result_directory) / MANIFEST_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=4) + "\n")
    return manifest


def read_manifest(result_directory):
    """Read the manifest.json saved in a target's result directory.

    Args:
        result_directory: Local directory a target's results (or stored baseline) are in.

    Returns:
        dict or None: The manifest, or None when there isn't one (a baseline published
            before manifests were recorded) or it can't be read.
    """
    path = Path(result_directory) / MANIFEST_FILENAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        logger.warning(f"Could not read the manifest at {path}")
        return None


def _read_input_checksums(result_directory):
    """Read the input checksums an instance wrote, wherever under the result directory they landed."""
    matches = sorted(Path(result_directory).rglob(INPUT_CHECKSUMS_FILENAME))
    if not matches:
        return {}
    try:
        return json.loads(matches[0].read_text())
    except (OSError, ValueError):
        logger.warning(f"Could not read the input checksums at {matches[0]}")
        return {}


def manifest_differences(reference, other, reference_name, other_name):
    """List what keeps two runs from being like for like, for the report.

    The OasisLMF install is left out, since a different version or branch is what a benchmark
    is there to compare.

    Args:
        reference: The reference run's manifest, or None if it has none.
        other: The compared run's manifest, or None if it has none.
        reference_name: The reference run's name in the report.
        other_name: The compared run's name in the report.

    Returns:
        list[str]: One note per difference, empty when the two match. A run with no manifest
            gets a single note saying its conditions can't be checked.
    """
    missing = [name for name, manifest in ((reference_name, reference), (other_name, other)) if manifest is None]
    if missing:
        return [f"no manifest for {name} (recorded before manifests existed), so its instance and inputs can't be checked"
                for name in missing]

    notes = []
    for key, label in (("instance_type", "instance type"), ("ami_id", "AMI")):
        if reference.get(key) != other.get(key):
            notes.append(f"{label} differs: {reference.get(key)} vs {other.get(key)}")
    # Manifests from before TESTS_PER_INSTANCE existed were all from instances of their own.
    reference_sharing = reference.get("tests_per_instance") or "separate"
    other_sharing = other.get("tests_per_instance") or "separate"
    if reference_sharing != other_sharing:
        notes.append(f"tests per instance differs: {reference_sharing} vs {other_sharing}")

    reference_inputs, other_inputs = reference.get("inputs") or {}, other.get("inputs") or {}
    if not reference_inputs or not other_inputs:
        for name, inputs in ((reference_name, reference_inputs), (other_name, other_inputs)):
            if not inputs:
                notes.append(f"no input checksums for {name}, so its inputs can't be checked")
        return notes

    for key, label in INPUT_NAMES.items():
        reference_entry, other_entry = reference_inputs.get(key), other_inputs.get(key)
        if reference_entry is None and other_entry is None:
            continue
        reference_entry, other_entry = reference_entry or {}, other_entry or {}
        if reference_entry.get("path") != other_entry.get("path"):
            notes.append(f"{label} path differs: {reference_entry.get('path')} vs {other_entry.get('path')}")
        elif None not in (reference_entry.get("sha256"), other_entry.get("sha256")) and \
                reference_entry.get("sha256") != other_entry.get("sha256"):
            notes.append(f"{label} changed ({other_entry.get('path')})")
    for name, inputs in ((reference_name, reference_inputs), (other_name, other_inputs)):
        for key, label in INPUT_NAMES.items():
            entry = inputs.get(key)
            if entry is not None and entry.get("sha256") is None:
                notes.append(f"{label} file missing for {name}: {entry.get('path')}")
    return notes
