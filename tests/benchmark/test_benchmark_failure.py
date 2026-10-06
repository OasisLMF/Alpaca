from alpaca.benchmark.failure import MAX_MESSAGE_LENGTH, describe_failure, missing_inputs, write_failure
from alpaca.exceptions import OasisAlpacaError


MODEL_SETTINGS_OUTPUT = """Command failed with exit status 1: set -o pipefail; oasislmf model run -C tests/test_1/oasislmf.json | tee runs/result.txt
Traceback (most recent call last):
  File "/usr/local/lib/python3.10/dist-packages/ods_tools/oed/settings.py", line 388, in load
    raise OdsException(f'Invalid {self.settings_type} file or file path: {settings_fp}')
ods_tools.oed.common.OdsException: Invalid model_settings file or file path: /home/ubuntu/tests/test_1/../../settings/1.4.0.0/model_settings.json
"""


def test_describe_failure_picks_out_the_model_run_exception():
    """The error this morning: the useful line is the last exception, not the command or traceback."""
    failure = describe_failure(OasisAlpacaError(MODEL_SETTINGS_OUTPUT))

    assert failure["stage"] == "model run"
    assert failure["message"] == (
        "ods_tools.oed.common.OdsException: Invalid model_settings file or file path: "
        "/home/ubuntu/tests/test_1/../../settings/1.4.0.0/model_settings.json"
    )
    assert failure["detail"] == MODEL_SETTINGS_OUTPUT


def test_describe_failure_recognises_instance_setup():
    failure = describe_failure(OasisAlpacaError("Error during instance setup: An error occurred (InvalidGroup.NotFound)"))

    assert failure["stage"] == "instance setup"
    assert "InvalidGroup.NotFound" in failure["message"]


def test_describe_failure_falls_back_to_the_exception_type_and_last_line():
    failure = describe_failure(RuntimeError("something odd\nlast line"))

    assert failure["stage"] == "RuntimeError"
    assert failure["message"] == "last line"


def test_describe_failure_shortens_a_very_long_message():
    failure = describe_failure(RuntimeError("ValueError: " + "x" * 1000))

    assert len(failure["message"]) == MAX_MESSAGE_LENGTH
    assert failure["message"].endswith("...")


def test_missing_inputs_lists_files_without_a_checksum():
    manifest = {"inputs": {
        "oasislmf_json": {"path": "tests/test_1/oasislmf.json", "sha256": "a" * 64},
        "model_settings_json": {"path": "settings/1.4.0.0/model_settings.json", "sha256": None},
    }}

    assert missing_inputs(manifest) == ["settings/1.4.0.0/model_settings.json"]


def test_missing_inputs_handles_no_manifest():
    assert missing_inputs(None) == []


def test_write_failure_puts_the_cause_first_and_keeps_the_full_output(tmp_path):
    failure = describe_failure(OasisAlpacaError(MODEL_SETTINGS_OUTPUT))

    path = write_failure(tmp_path, failure, ["settings/1.4.0.0/model_settings.json"])
    lines = path.read_text().splitlines()

    assert lines[0] == "Stage: model run"
    assert lines[1].startswith("Error: ods_tools.oed.common.OdsException")
    assert lines[2:4] == ["Missing input files:", "- settings/1.4.0.0/model_settings.json"]
    assert "Traceback (most recent call last):" in path.read_text()
