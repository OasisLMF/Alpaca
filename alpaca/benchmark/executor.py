from alpaca.model.main import main as model_main
from alpaca.benchmark.timing import resolve_model_runtime

import concurrent.futures
import logging
import time

logger = logging.getLogger(__name__)


def _run_target(run_config_entry):
    """Run one benchmark target's model execution and time its outcome.

    Reuses alpaca.model.main.main for the EC2 lifecycle (upload, run, download, terminate)
    rather than duplicating it, so a benchmark target runs exactly like an ordinary
    'alpaca model' run. The wall-clock time around that call includes EC2 startup, upload
    and download as well as the model run itself, so on success it's replaced as
    'runtime_seconds' by the model's own reported runtime (see resolve_model_runtime),
    with the wall-clock kept separately as 'total_runtime_seconds'.

    Args:
        run_config_entry: One entry as returned by build_benchmark_targets, with 'label',
            'model', 'version' and 'run_config' keys.

    Returns:
        dict: {'label', 'model', 'version', 'status', 'runtime_seconds',
            'total_runtime_seconds', 'step_timings'}. 'label' is the target's own label, so a
            result can be traced back to the target that produced it. 'status' is 'success'
            unless alpaca.model.main.main raises, in which case it is 'failed' and the
            exception is logged. 'step_timings' is a dict
            of every 'COMPLETED: <step> in <seconds>s' OasisLMF reported (e.g.
            'execution.runner.run', 'computation.generate.files.run'), empty on failure or
            when result.txt couldn't be found/parsed.
    """
    start = time.monotonic()
    status = "success"
    try:
        model_main(run_config_entry["run_config"])
    except Exception:
        status = "failed"
        logger.exception(f"Benchmark target '{run_config_entry['label']}' failed")
    total_runtime_seconds = round(time.monotonic() - start)

    runtime_seconds, step_timings = total_runtime_seconds, {}
    if status == "success":
        model_runtime_seconds, step_timings = resolve_model_runtime(
            run_config_entry["run_config"]["RESULT_DIRECTORY"], total_runtime_seconds
        )
        runtime_seconds = round(model_runtime_seconds)

    return {
        "label": run_config_entry["label"],
        "model": run_config_entry["model"],
        "version": run_config_entry["version"],
        "status": status,
        "runtime_seconds": runtime_seconds,
        "total_runtime_seconds": total_runtime_seconds,
        "step_timings": step_timings,
    }


def run_benchmark_targets(run_configs, execution_mode="parallel"):
    """Run every benchmark target's model execution and collect its result.

    Args:
        run_configs: List of entries as returned by build_benchmark_targets.
        execution_mode: 'parallel' runs every target concurrently, each in its own thread
            and on its own EC2 instance. 'sequential' runs them one after another.

    Returns:
        list[dict]: One result per target, in run_configs order, each with 'label', 'model',
            'version', 'status', 'runtime_seconds', 'total_runtime_seconds' and
            'step_timings' (see _run_target).
    """
    if execution_mode == "sequential":
        return [_run_target(entry) for entry in run_configs]

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(run_configs)) as executor:
        futures = [executor.submit(_run_target, entry) for entry in run_configs]
        return [future.result() for future in futures]
