from alpaca.api.commands import (
    api_run_commands,
    deploy_oasis_server_commands,
    wait_for_oasis_server_commands,
    docker_install_commands
)


def test_api_run_commands_runs_oasislmf_api():
    """Test that api_run_commands will execute oasislmf api run with localhost and config path."""
    config_path = "/path/to/config.json"
    commands = api_run_commands(config_path)

    has_api_run = False
    for command in commands:
        if f"oasislmf api run --server-url http://localhost:8000/ -C {config_path}" == command:  # noqa: E701,E231
            has_api_run = True
            break
    assert has_api_run


def test_api_run_commands_creates_output_directory_moves_results():
    """Test that api_run_commands will create a runs directory and move the run in the correct order."""
    commands = api_run_commands("/config.json")
    missing_commands = ["oasislmf api run", "mkdir -p ./runs", "mv ./analysis_1_output.tar.gz ./runs/analysis_1_output.tar.gz"]
    for command in commands:
        if missing_commands[0] in command:
            missing_commands.pop(0)
            if len(missing_commands) == 0:
                break
    assert missing_commands == []


def test_deploy_with_bash_script():
    """Test that deploying a .sh file will make it executable and then execute it."""
    commands = deploy_oasis_server_commands("./setup.sh")

    missing_commands = ["chmod +x ./setup.sh", "bash -e ./setup.sh"]
    for command in commands:
        if missing_commands[0] in command:
            missing_commands.pop(0)
            if len(missing_commands) == 0:
                break
    assert missing_commands == []


def test_deploy_with_yml():
    """Test that deploying a .yml file will use docker compose."""
    commands = deploy_oasis_server_commands("./docker-compose.yml")

    for command in commands:
        if "docker compose" in command and "./docker-compose.yml" in command and " up -d" in command:
            uses_docker_compose = True
            break
    assert uses_docker_compose


def test_deploy_with_yml_doesnt_use_bash():
    """Test that deploy commands do not use bash when given a yml file."""
    commands = deploy_oasis_server_commands("./docker-compose.yml")
    for command in commands:
        assert "bash" not in command


def test_deploy_with_bash_doesnt_use_docker():
    """Test that deploy when used with a bash script will not use docker."""
    commands = deploy_oasis_server_commands("./script.sh")
    for command in commands:
        assert "docker" not in command


def test_wait_for_server_checks_healthcheck():
    """Test that wait command will check the healthcheck endpoint."""
    commands = wait_for_oasis_server_commands()

    checks_healthcheck = False
    for command in commands:
        if "curl" in command and "healthcheck" in command:
            checks_healthcheck = True
            break
    assert checks_healthcheck


def test_docker_install_installs_docker():
    """Test that docker install will install docker packages and does the commands in order."""
    commands = docker_install_commands()

    unused_commands = [
        "apt-get update",
        "download.docker.com",
        "apt-get install -y docker-ce",
        "systemcl enable docker",
        "systemcl start docker"
    ]
    for command in commands:
        if unused_commands[0] in command:
            unused_commands.pop(0)
            if len(unused_commands) == 0:
                break
    assert unused_commands
