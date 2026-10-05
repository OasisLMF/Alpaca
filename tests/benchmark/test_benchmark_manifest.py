from alpaca.benchmark.manifest import (
    INPUT_CHECKSUMS_FILENAME, build_manifest, manifest_differences, read_manifest, write_manifest
)

import json


def _target(run_config=None, test="test_1"):
    return {
        "label": "PiWind-test_1-2.5.8", "model": "PiWind", "test": test, "version": "2.5.8",
        "run_config": {"OASISLMF_VERSION": "2.5.8", **(run_config or {})},
    }


def _inputs(model_settings_sha="b" * 64, model_settings_path="meta-data/model_settings.json"):
    return {
        "oasislmf_json": {"path": "tests/test_1/oasislmf.json", "sha256": "a" * 64},
        "analysis_settings_json": {"path": "tests/test_1/analysis_settings.json", "sha256": "c" * 64},
        "model_settings_json": {"path": model_settings_path, "sha256": model_settings_sha},
    }


def _manifest(instance_type="m5.xlarge", ami_id="ami-1", inputs=None):
    return {"instance_type": instance_type, "ami_id": ami_id, "inputs": _inputs() if inputs is None else inputs}


def _write_checksums(directory, inputs):
    """Put the instance's checksums where the results download would leave them."""
    (directory / INPUT_CHECKSUMS_FILENAME).parent.mkdir(parents=True, exist_ok=True)
    (directory / INPUT_CHECKSUMS_FILENAME).write_text(json.dumps(inputs))


def test_build_manifest_records_the_instance_and_the_input_checksums(tmp_path):
    _write_checksums(tmp_path, _inputs())

    manifest = build_manifest(_target({"INSTANCE_TYPE": "m5.xlarge", "AMI_ID": "ami-1"}), tmp_path, created_at="now")

    assert manifest["instance_type"] == "m5.xlarge"
    assert manifest["ami_id"] == "ami-1"
    assert manifest["oasislmf_version"] == "2.5.8"
    assert manifest["test"] == "test_1"
    assert manifest["created_at"] == "now"
    assert manifest["inputs"] == _inputs()


def test_build_manifest_falls_back_to_the_default_instance_settings(tmp_path):
    """A config that leaves INSTANCE_TYPE/AMI_ID out still ran on the defaults, so they're recorded."""
    manifest = build_manifest(_target(), tmp_path)

    assert manifest["instance_type"] == "t3.medium"
    assert manifest["ami_id"].startswith("ami-")


def test_build_manifest_has_no_inputs_when_the_instance_wrote_no_checksums(tmp_path):
    assert build_manifest(_target(), tmp_path)["inputs"] == {}


def test_write_then_read_manifest_round_trips(tmp_path):
    _write_checksums(tmp_path, _inputs())

    written = write_manifest(_target(), tmp_path)

    assert read_manifest(tmp_path) == written


def test_read_manifest_returns_none_without_one(tmp_path):
    assert read_manifest(tmp_path) is None


def test_read_manifest_returns_none_for_an_unreadable_one(tmp_path):
    (tmp_path / "manifest.json").write_text("not json")

    assert read_manifest(tmp_path) is None


def test_manifest_differences_is_empty_when_like_for_like():
    assert manifest_differences(_manifest(), _manifest(), "2.5.7", "2.5.8") == []


def test_manifest_differences_ignores_the_oasislmf_install():
    """A different version is what a benchmark compares, so it's never flagged."""
    reference, other = {**_manifest(), "oasislmf_version": "2.5.7"}, {**_manifest(), "oasislmf_version": "2.5.8"}

    assert manifest_differences(reference, other, "2.5.7", "2.5.8") == []


def test_manifest_differences_flags_a_different_instance_type_and_ami():
    notes = manifest_differences(_manifest(), _manifest(instance_type="t2.xlarge", ami_id="ami-2"), "2.5.7", "2.5.8")

    assert notes == ["instance type differs: m5.xlarge vs t2.xlarge", "AMI differs: ami-1 vs ami-2"]


def test_manifest_differences_flags_changed_model_settings():
    notes = manifest_differences(_manifest(), _manifest(inputs=_inputs(model_settings_sha="d" * 64)), "2.5.7", "2.5.8")

    assert notes == ["model settings changed (meta-data/model_settings.json)"]


def test_manifest_differences_flags_a_moved_model_settings_file():
    other = _manifest(inputs=_inputs(model_settings_path="settings/1.4.0.0/model_settings.json"))

    notes = manifest_differences(_manifest(), other, "2.5.7", "2.5.8")

    assert notes == ["model settings path differs: meta-data/model_settings.json vs settings/1.4.0.0/model_settings.json"]


def test_manifest_differences_flags_a_missing_input_file():
    """The instance records a file oasislmf.json points at but that isn't there with no checksum."""
    other = _manifest(inputs=_inputs(model_settings_sha=None))

    notes = manifest_differences(_manifest(), other, "2.5.7", "2.5.8")

    assert notes == ["model settings file missing for 2.5.8: meta-data/model_settings.json"]


def test_manifest_differences_says_when_a_run_has_no_manifest():
    notes = manifest_differences(None, _manifest(), "2.5.7 (from S3)", "2.5.8")

    assert notes == ["no manifest for 2.5.7 (from S3) (recorded before manifests existed), so its instance and inputs can't be checked"]


def test_manifest_differences_says_when_a_run_has_no_input_checksums():
    notes = manifest_differences(_manifest(), _manifest(inputs={}), "2.5.7", "2.5.8")

    assert notes == ["no input checksums for 2.5.8, so its inputs can't be checked"]
