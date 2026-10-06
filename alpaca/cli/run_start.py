from alpaca.model.main import main as model_main
from alpaca.pytest.main import main as pytest_main
from alpaca.api.main import main as api_main
from alpaca.benchmark.main import benchmark_failed, main as benchmark_main
from alpaca.benchmark.report import run_name

import sys

HELP_ARGS = {'h', '-h', 'help', '-help', '--help'}


def run_model(args):
    """Starts model alpaca instance with args[0] as config file."""
    if len(args) == 0 or args[0] in HELP_ARGS:
        print("Usage: 'alpaca model <config.json>'")
    else:
        model_main(args[0])


def run_pytest(args):
    """Starts pytest alpaca instance with args[0] as config file."""
    if len(args) == 0 or args[0] in HELP_ARGS:
        print("Usage: 'alpaca pytest <config.json>'")
    else:
        pytest_main(args[0])


def run_api(args):
    """Starts api alpaca instance with args[0] as config file."""
    if len(args) == 0 or args[0] in HELP_ARGS:
        print("Usage: 'alpaca api <config.json>'")
    else:
        api_main(args[0])


def run_benchmark(args):
    """Runs a benchmark with args[0] as config file, exiting with status 1 if any run or comparison failed."""
    if len(args) == 0 or args[0] in HELP_ARGS:
        print("Usage: 'alpaca benchmark <config.json>'")
    else:
        output = benchmark_main(args[0])
        if benchmark_failed(output):
            print("Benchmark finished with failures: see the report above.")
            print_failure_details(output)
            print("Exiting with status 1.")
            sys.exit(1)


def print_failure_details(output):
    """Point at each failed run's failure.txt, so the evidence doesn't have to be hunted for."""
    failed = [result for result in output["results"] if (result.get("failure") or {}).get("details")]
    if failed:
        print("Failure details:")
        for result in failed:
            print(f"- {run_name(result)}: {result['failure']['details']}")
    if output.get("report_path"):
        print(f"Full report: {output['report_path']}")
