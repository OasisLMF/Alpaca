from alpaca.model.scripts import model_run_commands


def test_model_run_commands_runs_oasislmf():
    """Test that model_run_commands will execute oasislmf model run."""
    config_path = "/path/to/config.json"
    commands = model_run_commands(config_path)

    runs_model = any(command.startswith(f"oasislmf model run -C {config_path}") for command in commands)
    assert runs_model


def test_model_run_commands_with_relative_path():
    """Test that model_run_commands works with relative paths."""
    config_path = "./config.json"
    commands = model_run_commands(config_path)

    has_command = any(command.startswith(f"oasislmf model run -C {config_path}") for command in commands)
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
