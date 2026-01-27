def api_run_commands(path_to_oasislmf_json):
    commands = [
        f"oasislmf api run --server-url http://localhost:8000/ -C {path_to_oasislmf_json}",
        "mkdir -p ./runs",
        "mv ./analysis_1_output.tar.gz ./runs/analysis_1_output.tar.gz"
    ]
    return commands


def deploy_oasis_server_commands(path_to_docker_compose):
    if path_to_docker_compose.endswith(".sh"):  # Custom bash scripts may be used instead
        commands = [
            f"chmod +x {path_to_docker_compose}",
            f"bash -e {path_to_docker_compose}",
        ]
        return commands

    commands = [
        f"sudo docker compose -f {path_to_docker_compose} --project-directory . up -d --build > /dev/null 2>&1",
    ]
    return commands


def wait_for_oasis_server_commands():
    commands = [
        'delay=5; max=300; elapsed=0; until curl -sf http://localhost:8000/healthcheck; do '
        '[ "$elapsed" -ge "$max" ] && echo "Timed out waiting for service" && exit 1; sleep '
        '"$delay"; elapsed=$((elapsed + delay)); delay=$(( delay < max ? delay * 2 : max )); done'
    ]
    return commands


def docker_install_commands():
    commands = [
        "sudo apt-get update -y",
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl gnupg",
        "sudo mkdir -p /etc/apt/keyrings",
        "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
        'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] '
        'https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null',
        "sudo apt-get update -y",
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin",
        "sudo systemctl enable docker",
        "sudo systemctl start docker",
    ]
    return commands
