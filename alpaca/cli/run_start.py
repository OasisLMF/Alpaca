from alpaca.model.main import main as model_main
from alpaca.pytest.main import main as pytest_main
from alpaca.api.main import main as api_main
from alpaca.benchmark.main import main as benchmark_main
from alpaca.dashboard.main import main as dashboard_main

HELP_ARGS = {'h', '-h', 'help', '-help', '--help'}
DASHBOARD_FLAGS = {'-dashboard', '--dashboard'}


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
    """Validates a benchmark alpaca config with args[0] as config file, and args[1:] as
    optional flags (currently only '--dashboard'/'-dashboard', to build a run dashboard for
    every successful target once the benchmark finishes).
    """
    if len(args) == 0 or args[0] in HELP_ARGS:
        print("Usage: 'alpaca benchmark <config.json> [--dashboard]'")
    else:
        benchmark_main(args[0], generate_dashboard=bool(DASHBOARD_FLAGS.intersection(args[1:])))


def run_dashboard(args):
    """Builds a run dashboard with args[0] as the downloaded run directory."""
    if len(args) == 0 or args[0] in HELP_ARGS:
        print("Usage: 'alpaca dashboard <run-directory>'")
    else:
        dashboard_main(args[0])
