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
output = sys.argv[2] if len(sys.argv) > 2 else "runs/input_checksums.json"
checksums = {"oasislmf_json": entry(oasislmf_json)}
try:
    with open(oasislmf_json) as f:
        settings = json.load(f)
except (OSError, ValueError):
    settings = {}
for key in ("analysis_settings_json", "model_settings_json"):
    if settings.get(key):
        checksums[key] = entry(os.path.normpath(os.path.join(os.path.dirname(oasislmf_json), settings[key])))
os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
with open(output, "w") as f:
    json.dump(checksums, f, indent=4)
"""


def input_checksum_commands(path_to_oasislmf, output_path="runs/input_checksums.json"):
    """Generate a command recording checksums of the model inputs a run is about to use.

    Writes runs/input_checksums.json with a SHA-256 of the oasislmf.json the run starts from,
    and of the analysis_settings_json and model_settings_json it points to, each path
    resolved the way OasisLMF resolves them (relative to the oasislmf.json's own directory).
    A file that isn't there is recorded with a null checksum rather than skipped, so a run
    that fails on a bad path shows which one. It lands in runs/ and so comes back with the
    rest of the results, where a benchmark reads it into the run's manifest (see
    alpaca.benchmark.manifest). The command always exits zero: recording checksums is never
    a reason to stop a run.

    Paths are recorded relative to the model's base (the instance's home directory, where every
    command starts), so the same input gets the same path however the run was laid out.

    Args:
        path_to_oasislmf: Path to the oasislmf.json file, relative to the model's base.
        output_path: Where to write the checksums, relative to the model's base.

    Returns:
        list[str]: Shell commands to execute.
    """
    encoded = base64.b64encode(_INPUT_CHECKSUM_SCRIPT.encode()).decode()
    return [
        f"echo {encoded} | base64 -d | python3 - {shlex.quote(path_to_oasislmf)} {shlex.quote(output_path)} || true"
    ]


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


DROP_FILE_CACHE_COMMAND = "sync && sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches' || true"

# OasisLMF compiles its Numba functions the first time they run and caches the result on disk:
# next to the package's own source when that's writable, otherwise in the user's cache. A test
# after the first on a shared instance would otherwise skip that compile time and look much
# faster than the same test on an instance of its own, so the cache is cleared from both places.
CLEAR_COMPILE_CACHE_COMMAND = (
    "d=$(python3 -c 'import os, oasislmf; print(os.path.dirname(oasislmf.__file__))' 2>/dev/null); "
    "if [ -n \"$d\" ]; then find \"$d\" \\( -name '*.nbi' -o -name '*.nbc' \\) -delete 2>/dev/null "
    "|| sudo -n find \"$d\" \\( -name '*.nbi' -o -name '*.nbc' \\) -delete; fi; "
    "rm -rf \"$HOME/.cache/numba\"; true"
)


def shared_test_commands(path_to_oasislmf, run_directory):
    """Generate commands to run one of several tests sharing an instance, in its own directory.

    A shared instance (TESTS_PER_INSTANCE 'shared') installs OasisLMF and pulls the model once,
    then runs each test in turn. Each test runs from its own run_directory, so OasisLMF's
    runs/losses-<timestamp> output, result.txt and the input checksums of one test never mix
    with another's, and each can be downloaded to its own target's RESULT_DIRECTORY. The
    instance's file cache is dropped first, so a later test doesn't start with the earlier
    tests' model data already in memory and look faster than it would on an instance of its
    own, and OasisLMF's compiled-code cache is cleared, so a later test pays the same one-off
    compile time as it would on a fresh instance (see CLEAR_COMPILE_CACHE_COMMAND); neither
    ever stops the run if it can't be done.

    Args:
        path_to_oasislmf: Path to the test's oasislmf.json, relative to the model's base
            (e.g. 'tests/test_1/oasislmf.json').
        run_directory: Directory, relative to the model's base, this test's results go under
            (e.g. 'alpaca_tests/test_1'); its runs/ subdirectory is what gets downloaded.

    Returns:
        list[str]: Shell commands to execute.
    """
    runs = f"{run_directory}/runs"
    return [
        f"mkdir -p {shlex.quote(runs)}",
        *input_checksum_commands(path_to_oasislmf, f"{runs}/input_checksums.json"),
        CLEAR_COMPILE_CACHE_COMMAND,
        DROP_FILE_CACHE_COMMAND,
        f"set -o pipefail; cd {shlex.quote(run_directory)} && "
        f"oasislmf model run -C \"$HOME\"/{shlex.quote(path_to_oasislmf)} | tee runs/result.txt",
    ]
