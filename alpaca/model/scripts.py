def model_run_commands(path_to_oasislmf):
    """ Commands to start an oasislmf model run """
    commands = [
        f"oasislmf model run -C {path_to_oasislmf}"
    ]
    return commands
