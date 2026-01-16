from alpaca.scripts import setup_python_commands


def test_setup_python_commands_uses_version():
    version = "2.3.4"
    commands = setup_python_commands(version)
    oasislmf_version_used = False
    for command in commands:
        if f"pip install oasislmf=={version}" in command:
            oasislmf_version_used = True
            break
    assert oasislmf_version_used


def test_setup_python_commands_no_version():
    commands = setup_python_commands()
    oasislmf_version_used = False
    for command in commands:
        if "pip install oasislmf " in command:
            oasislmf_version_used = True
            break
    assert oasislmf_version_used
