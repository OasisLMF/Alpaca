def model_run_commands(path_to_oasislmf):
    """Generate commands to execute an OasisLMF model run.

    Args:
        path_to_oasislmf: Path to the oasislmf.json file

    Returns:
        list[str]: Shell commands to execute.
    """
    commands = [
        f"oasislmf model run -C {path_to_oasislmf}"
    ]
    return commands
