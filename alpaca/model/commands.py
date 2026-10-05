import base64
import shlex

# Run on the instance with the model's oasislmf.json as its one argument (see
# input_checksum_commands). Written as a plain script and base64-encoded into the command, so
# it reaches the instance's python3 without any shell quoting to get wrong.
_INPUT_CHECKSUM_SCRIPT = """
import hashlib, json, os, sys

def entry(path):
    try:
        with open(path, "rb") as f:
            return {"path": path, "sha256": hashlib.sha256(f.read()).hexdigest()}
    except OSError:
        return {"path": path, "sha256": None}

oasislmf_json = os.path.normpath(sys.argv[1])
checksums = {"oasislmf_json": entry(oasislmf_json)}
try:
    with open(oasislmf_json) as f:
        settings = json.load(f)
except (OSError, ValueError):
    settings = {}
for key in ("analysis_settings_json", "model_settings_json"):
    if settings.get(key):
        checksums[key] = entry(os.path.normpath(os.path.join(os.path.dirname(oasislmf_json), settings[key])))
os.makedirs("runs", exist_ok=True)
with open("runs/input_checksums.json", "w") as f:
    json.dump(checksums, f, indent=4)
"""


def input_checksum_commands(path_to_oasislmf):
    """Generate a command recording checksums of the model inputs a run is about to use.

    Writes runs/input_checksums.json with a SHA-256 of the oasislmf.json the run starts from,
    and of the analysis_settings_json and model_settings_json it points to, each path
    resolved the way OasisLMF resolves them (relative to the oasislmf.json's own directory).
    A file that isn't there is recorded with a null checksum rather than skipped, so a run
    that fails on a bad path shows which one. It lands in runs/ and so comes back with the
    rest of the results, where a benchmark reads it into the run's manifest (see
    alpaca.benchmark.manifest). The command always exits zero: recording checksums is never
    a reason to stop a run.

    Args:
        path_to_oasislmf: Path to the oasislmf.json file, relative to the model's base.

    Returns:
        list[str]: Shell commands to execute.
    """
    encoded = base64.b64encode(_INPUT_CHECKSUM_SCRIPT.encode()).decode()
    return [f"echo {encoded} | base64 -d | python3 - {shlex.quote(path_to_oasislmf)} || true"]


def model_run_commands(path_to_oasislmf):
    """Generate commands to execute an OasisLMF model run.

    The run's own stdout - including the 'COMPLETED: <step> in <seconds>s' lines OasisLMF
    reports for each stage (e.g. 'oasislmf.manager.interface', 'execution.runner.run') - is
    teed into runs/result.txt alongside the run's usual output. 'mkdir -p runs' runs first
    so tee has somewhere to write before OasisLMF creates its own 'runs/losses-<timestamp>'
    output directory. Checksums of the run's inputs are recorded first (see
    input_checksum_commands). Since result.txt lands inside runs/, it's picked up by the same
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
        *input_checksum_commands(path_to_oasislmf),
        f"set -o pipefail; oasislmf model run -C {path_to_oasislmf} | tee runs/result.txt"
    ]
    return commands
