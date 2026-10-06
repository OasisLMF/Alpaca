from pathlib import Path

import re

FAILURE_FILENAME = "failure.txt"
MAX_MESSAGE_LENGTH = 300

# The last line naming an exception, e.g. 'ods_tools.oed.common.OdsException: Invalid model_settings
# file or file path: ...', which is the most useful single line in a failed run's output.
_EXCEPTION_LINE = re.compile(r"^\s*(?:[\w.]+\.)?\w*(?:Error|Exception|Exit)\b.*")

# Which part of a run failed, recognised from the command or message an exception carries, in
# the order they're checked. Anything else is reported under its exception's own type.
_STAGES = (
    ("Error during instance setup", "instance setup"),
    ("oasislmf model run", "model run"),
    ("Nothing to download", "downloading results"),
)


def describe_failure(error):
    """Summarise why a benchmark run failed, for the report and its failure.txt.

    Args:
        error: The exception the run raised (see alpaca.model.main.main, which raises with the
            failed command's full output, and alpaca.remote_controller.RemoteController).

    Returns:
        dict: 'stage' (which part of the run failed, e.g. 'model run' or 'instance setup'),
            'message' (the most telling single line: the last exception line in the output, or
            else its last non-blank line, cut to MAX_MESSAGE_LENGTH characters) and 'detail'
            (the exception's full text).
    """
    detail = str(error)
    stage = next((stage for marker, stage in _STAGES if marker in detail), type(error).__name__)
    lines = [line.strip() for line in detail.splitlines() if line.strip()]
    exception_lines = [line for line in lines if _EXCEPTION_LINE.match(line)]
    message = (exception_lines or lines or [type(error).__name__])[-1]
    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[:MAX_MESSAGE_LENGTH - 3] + "..."
    return {"stage": stage, "message": message, "detail": detail}


def missing_inputs(manifest):
    """List the input files a run's oasislmf.json pointed at that weren't there, from its manifest.

    Args:
        manifest: The run's manifest (see alpaca.benchmark.manifest), or None.

    Returns:
        list[str]: One path per missing input, e.g. 'settings/1.4.0.0/model_settings.json'.
    """
    inputs = (manifest or {}).get("inputs") or {}
    return [entry.get("path") for entry in inputs.values() if entry and entry.get("sha256") is None]


def write_failure(result_directory, failure, missing=()):
    """Save the evidence for a failed run as failure.txt in its result directory.

    Args:
        result_directory: Local directory the run's results (and partial output) were saved to.
        failure: dict from describe_failure.
        missing: Input files the run's oasislmf.json pointed at that weren't there (see
            missing_inputs), listed first since they're usually the cause.

    Returns:
        Path: Where the file was written.
    """
    lines = [f"Stage: {failure['stage']}", f"Error: {failure['message']}"]
    if missing:
        lines.append("Missing input files:")
        lines.extend(f"- {path}" for path in missing)
    lines.extend(["", "Full output:", failure["detail"]])
    path = Path(result_directory) / FAILURE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path
