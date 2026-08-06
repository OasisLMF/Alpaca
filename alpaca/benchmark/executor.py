from alpaca.model.main import main as model_main

import concurrent.futures
import logging
import time

logger = logging.getLogger(__name__)


def _run_target(run_config_entry):
    """Run one benchmark target's model execution and time its outcome.

    Reuses alpaca.model.main.main for the EC2 lifecycle (upload, run, download, terminate)
    rather than duplicating it, so a benchmark target runs exactly like an ordinary
    'alpaca model' run.

    Args:
        run_config_entry: One entry as returned by build_model_run_configs, with 'label',
            'model', 'version' and 'run_config' keys.

    Returns:
        dict: {'model', 'version', 'status', 'runtime_seconds'}. 'status' is 'success'
            unless alpaca.model.main.main raises, in which case it is 'failed' and the
            exception is logged.
    """
    start = time.monotonic()
    status = "success"
    try:
        model_main(run_config_entry["run_config"])
    except Exception:
        status = "failed"
        logger.exception(f"Benchmark target '{run_config_entry['label']}' failed")
    runtime_seconds = round(time.monotonic() - start)
    return {
        "model": run_config_entry["model"],
        "version": run_config_entry["version"],
        "status": status,
        "runtime_seconds": runtime_seconds,
    }


def run_benchmark_targets(run_configs, execution_mode="parallel"):
    """Run every benchmark target's model execution and collect its result.

    Args:
        run_configs: List of entries as returned by build_model_run_configs.
        execution_mode: 'parallel' runs every target concurrently, each in its own thread
            and on its own EC2 instance. 'sequential' runs them one after another.

    Returns:
        list[dict]: One result per target, in run_configs order, each with 'model',
            'version', 'status' and 'runtime_seconds'.
    """
    if execution_mode == "sequential":
        return [_run_target(entry) for entry in run_configs]

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(run_configs)) as executor:
        futures = [executor.submit(_run_target, entry) for entry in run_configs]
        return [future.result() for future in futures]
