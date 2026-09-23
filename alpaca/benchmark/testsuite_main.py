from alpaca.pytest.commands import run_pytest_commands
from alpaca.pytest.utils import REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST
from alpaca.remote_controller import RemoteController


def main(run_config):
    """Run one benchmark target's test suite on a new EC2 instance, then download the logs.

    Used by alpaca.benchmark.executor in place of alpaca.model.main.main when a target's
    RUN_TEST_SUITE is set. Reuses alpaca.pytest.main's own approach exactly (upload
    REPO_LOCATION, run 'pytest .' once on the instance, download pytest_logs/) rather than
    duplicating it, so a suite target's tests/*/oasislmf.json configs run one after another
    via whatever test harness that repository provides (see e.g.
    OasisModels/tests/test_model_runs.py for the discovery convention this expects) — Alpaca
    itself has no opinion on what "a test" is beyond "pytest collected and ran it". The
    instance is terminated on the way out.

    A suite that fails raises rather than being reported as a run that passed, matching
    alpaca.model.main.main's behaviour, so alpaca.benchmark.executor can tell a failed suite
    target from a successful one the same way it already does for an ordinary model target.

    Args:
        run_config: One target's run_config dict, as built by
            alpaca.benchmark.scripts.build_benchmark_targets, not a config file path. It
            already carries every key REQUIRED_CONFIG_PYTEST needs, since they're all shared
            benchmark config keys (see SHARED_MODEL_CONFIG_KEYS) plus the target's own
            REPO_LOCATION.

    Raises:
        OasisAlpacaError: If any test fails, or pytest itself can't run.
    """
    with RemoteController(run_config, REQUIRED_CONFIG_PYTEST, OPTIONAL_CONFIG_PYTEST) as controller:
        controller.upload_model(controller.config['REPO_LOCATION'])
        try:
            controller.run_commands(run_pytest_commands(controller.config.get('PYTEST_ARGS', "")), log_condition, check=True)
        finally:
            controller.download_results("/home/ubuntu/pytest_logs", controller.config.get('RESULT_DIRECTORY', None))


def log_condition(cmd):
    """Only flows logs from pytest run, not from the pip installs that mention pytest."""
    return "pytest ." in cmd
