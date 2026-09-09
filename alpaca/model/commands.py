def model_run_commands(path_to_oasislmf):
    """Generate commands to execute an OasisLMF model run.

    The run's own stdout - including the 'COMPLETED: <step> in <seconds>s' lines OasisLMF
    reports for each stage (e.g. 'oasislmf.manager.interface', 'execution.runner.run') - is
    teed into runs/result.txt alongside the run's usual output. 'mkdir -p runs' runs first
    so tee has somewhere to write before OasisLMF creates its own 'runs/losses-<timestamp>'
    output directory. Since result.txt lands inside runs/, it's picked up by the same
    recursive download as everything else there, with no separate download step needed.

    'set -o pipefail' makes the command report OasisLMF's exit status rather than tee's,
    which is always zero, so a failed run can be told apart from a successful one.

    Args:
        path_to_oasislmf: Path to the oasislmf.json file

    Returns:
        list[str]: Shell commands to execute.
    """
    commands = [
        "mkdir -p runs",
        f"set -o pipefail; oasislmf model run -C {path_to_oasislmf} | tee runs/result.txt"
    ]
    return commands
