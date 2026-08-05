from alpaca.model.scripts import model_run_commands


def test_model_run_commands_runs_oasislmf():
    """Test that model_run_commands will execute oasislmf model run."""
    config_path = "/path/to/config.json"
    commands = model_run_commands(config_path)

    runs_model = False
    for command in commands:
        if command == f"oasislmf model run -C {config_path}":
            runs_model = True
            break
    assert runs_model


def test_model_run_commands_with_relative_path():
    """Test that model_run_commands works with relative paths."""
    config_path = "./config.json"
    commands = model_run_commands(config_path)

    has_command = False
    for command in commands:
        if command == f"oasislmf model run -C {config_path}":
            has_command = True
            break
    assert has_command
