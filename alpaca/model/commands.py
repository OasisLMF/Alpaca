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


# Run on the instance in the background for as long as the model runs (see memory_sampled).
# Once a second it appends the instance's memory use to a CSV: 'used_kib' is MemTotal less
# MemAvailable, i.e. memory that couldn't be handed back without swapping, so the file cache
# isn't counted, and 'oom_kills' is the kernel's running count of processes it killed for
# running out of memory. Each line is flushed as it's written, so stopping it loses nothing.
_MEMORY_SAMPLER_SCRIPT = """
import os, sys, time

output = sys.argv[1]
interval = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

def meminfo():
    values = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            values[key] = int(rest.split()[0])
    return values

def oom_kills():
    try:
        with open("/proc/vmstat") as f:
            for line in f:
                if line.startswith("oom_kill "):
                    return line.split()[1]
    except OSError:
        pass
    return ""

os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
with open(output, "w") as f:
    f.write("timestamp,total_kib,used_kib,swap_used_kib,oom_kills\\n")
    while True:
        m = meminfo()
        f.write("%.1f,%d,%d,%d,%s\\n" % (
            time.time(), m["MemTotal"], m["MemTotal"] - m["MemAvailable"],
            m.get("SwapTotal", 0) - m.get("SwapFree", 0), oom_kills(),
        ))
        f.flush()
        time.sleep(interval)
"""
MEMORY_SAMPLER_PATH = ".alpaca_memory_sampler.py"


def memory_sampler_install_commands():
    """Generate a command saving the memory sampler script to the instance's home directory.

    Saved rather than passed inline so the model run's own command, which is logged and shown
    in failure.txt, stays readable. The command always exits zero: a run without memory
    figures is still worth having.

    Returns:
        list[str]: Shell commands to execute.
    """
    encoded = base64.b64encode(_MEMORY_SAMPLER_SCRIPT.encode()).decode()
    return [f"echo {encoded} | base64 -d > \"$HOME\"/{MEMORY_SAMPLER_PATH} || true"]


def memory_sampled(run_command, memory_csv):
    """Wrap a model run command so the instance's memory use is sampled while it runs.

    The sampler starts in the background just before the run and is stopped as soon as it
    finishes, however it finishes, and the wrapped command exits with the run's own status. A
    sampler that can't start doesn't affect the run.

    Args:
        run_command: The command running the model, ending in its piped tee.
        memory_csv: Where the samples go, relative to the model's base, so it lands in the
            run's runs/ directory and is downloaded with everything else.

    Returns:
        str: The wrapped command.
    """
    return (
        f"python3 \"$HOME\"/{MEMORY_SAMPLER_PATH} {shlex.quote(memory_csv)} & sampler=$!; "
        f"{run_command}; status=$?; kill $sampler 2>/dev/null; exit $status"
    )


def model_run_commands(path_to_oasislmf):
    """Generate commands to execute an OasisLMF model run.

    The run's own stdout - including the 'COMPLETED: <step> in <seconds>s' lines OasisLMF
    reports for each stage (e.g. 'oasislmf.manager.interface', 'execution.runner.run') - is
    teed into runs/result.txt alongside the run's usual output. 'mkdir -p runs' runs first
    so tee has somewhere to write before OasisLMF creates its own 'runs/losses-<timestamp>'
    output directory. Checksums of the run's inputs are recorded first (see
    input_checksum_commands), and the instance's memory use is sampled into runs/memory.csv for
    as long as the model runs (see memory_sampled). Since result.txt and memory.csv land inside
    runs/, they're picked up by the same recursive download as everything else there, with no
    separate download step needed.

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
        *memory_sampler_install_commands(),
        "set -o pipefail; "
        + memory_sampled(f"oasislmf model run -C {path_to_oasislmf} | tee runs/result.txt", "runs/memory.csv"),
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
    ever stops the run if it can't be done. Memory use is sampled into the test's own
    runs/memory.csv while it runs (see memory_sampled).

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
        *memory_sampler_install_commands(),
        CLEAR_COMPILE_CACHE_COMMAND,
        DROP_FILE_CACHE_COMMAND,
        "set -o pipefail; " + memory_sampled(
            f"cd {shlex.quote(run_directory)} && "
            f"oasislmf model run -C \"$HOME\"/{shlex.quote(path_to_oasislmf)} | tee runs/result.txt",
            f"{runs}/memory.csv",
        ),
    ]
