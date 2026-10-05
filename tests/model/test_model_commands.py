from alpaca.model.commands import input_checksum_commands, model_run_commands

import hashlib
import json
import subprocess


def test_model_run_commands_runs_oasislmf():
    """Test that model_run_commands will execute oasislmf model run."""
    config_path = "/path/to/config.json"
    commands = model_run_commands(config_path)

    runs_model = any(f"oasislmf model run -C {config_path}" in command for command in commands)
    assert runs_model


def test_model_run_commands_with_relative_path():
    """Test that model_run_commands works with relative paths."""
    config_path = "./config.json"
    commands = model_run_commands(config_path)

    has_command = any(f"oasislmf model run -C {config_path}" in command for command in commands)
    assert has_command


def test_model_run_commands_tees_output_to_result_file():
    """Test that the run's stdout is teed into runs/result.txt, so it rides along with the
    normal recursive results download instead of needing its own download step.
    """
    commands = model_run_commands("/path/to/config.json")

    tees_result_file = any("| tee runs/result.txt" in command for command in commands)
    assert tees_result_file


def test_model_run_commands_creates_runs_dir_before_teeing():
    """Test that 'mkdir -p runs' runs before the piped model run, so tee has somewhere to
    write before OasisLMF creates its own output directory.
    """
    commands = model_run_commands("/path/to/config.json")

    mkdir_index = commands.index("mkdir -p runs")
    run_index = next(i for i, command in enumerate(commands) if "tee runs/result.txt" in command)
    assert mkdir_index < run_index


def test_model_run_commands_reports_the_model_runs_exit_status():
    """Without pipefail the piped run reports tee's exit status, so a failure looks like a pass."""
    command = next(c for c in model_run_commands("/path/to/config.json") if "oasislmf model run" in c)

    assert command.startswith("set -o pipefail; ")


def _run_checksum_command(tmp_path, path_to_oasislmf):
    """Run the checksum command for real, the way the instance would, from the model's base."""
    command = input_checksum_commands(path_to_oasislmf)[0]
    completed = subprocess.run(["bash", "-c", command], cwd=tmp_path)
    return completed.returncode, json.loads((tmp_path / "runs" / "input_checksums.json").read_text())


def test_input_checksum_commands_records_the_oasislmf_json_and_the_settings_it_points_to(tmp_path):
    (tmp_path / "tests" / "test_1").mkdir(parents=True)
    (tmp_path / "meta-data").mkdir()
    (tmp_path / "meta-data" / "model_settings.json").write_text("{}")
    (tmp_path / "tests" / "test_1" / "analysis_settings.json").write_text('{"a": 1}')
    (tmp_path / "tests" / "test_1" / "oasislmf.json").write_text(json.dumps({
        "analysis_settings_json": "analysis_settings.json",
        "model_settings_json": "../../meta-data/model_settings.json",
    }))

    exit_code, checksums = _run_checksum_command(tmp_path, "tests/test_1/oasislmf.json")

    assert exit_code == 0
    assert checksums["oasislmf_json"]["path"] == "tests/test_1/oasislmf.json"
    assert checksums["analysis_settings_json"] == {
        "path": "tests/test_1/analysis_settings.json", "sha256": hashlib.sha256(b'{"a": 1}').hexdigest(),
    }
    assert checksums["model_settings_json"] == {
        "path": "meta-data/model_settings.json", "sha256": hashlib.sha256(b"{}").hexdigest(),
    }


def test_input_checksum_commands_records_a_missing_settings_file_without_failing(tmp_path):
    """A wrong model_settings_json path shows up as a null checksum, and the run still goes ahead."""
    (tmp_path / "tests" / "test_1").mkdir(parents=True)
    (tmp_path / "tests" / "test_1" / "oasislmf.json").write_text(json.dumps({
        "model_settings_json": "../../settings/1.4.0.0/model_settings.json",
    }))

    exit_code, checksums = _run_checksum_command(tmp_path, "tests/test_1/oasislmf.json")

    assert exit_code == 0
    assert checksums["model_settings_json"] == {"path": "settings/1.4.0.0/model_settings.json", "sha256": None}


def test_input_checksum_commands_never_fails_without_an_oasislmf_json(tmp_path):
    exit_code, checksums = _run_checksum_command(tmp_path, "./oasislmf.json")

    assert exit_code == 0
    assert checksums == {"oasislmf_json": {"path": "oasislmf.json", "sha256": None}}


def test_model_run_commands_records_input_checksums_before_running():
    commands = model_run_commands("./oasislmf.json")

    checksum_index = commands.index(input_checksum_commands("./oasislmf.json")[0])
    run_index = next(i for i, command in enumerate(commands) if "oasislmf model run" in command)
    assert checksum_index < run_index
