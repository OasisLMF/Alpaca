from alpaca.model.commands import shared_test_commands
from alpaca.model.main import log_condition, main as model_main
from alpaca.model.utils import OPTIONAL_CONFIG_MODEL, REQUIRED_CONFIG_MODEL
from alpaca.benchmark.failure import describe_failure, missing_inputs, write_failure
from alpaca.benchmark.manifest import write_manifest
from alpaca.benchmark.scripts import group_name
from alpaca.benchmark.timing import resolve_model_runtime
from alpaca.logging_context import log_target
from alpaca.remote_controller import RemoteController

import concurrent.futures
import logging
import time

logger = logging.getLogger(__name__)

MAX_PARALLEL_TARGETS = 8
SHARED_RUNS_DIRECTORY = "alpaca_tests"


def _finish_target(run_config_entry, error, total_runtime_seconds, tests_per_instance):
    """Turn a finished run into a result, saving its manifest and, if it failed, its evidence.

    Whether the run worked or not, a manifest.json describing its instance and input checksums
    is saved next to its results (see alpaca.benchmark.manifest), so it can be checked for like
    for like. A failed run also gets a failure.txt there (see alpaca.benchmark.failure): which
    stage failed, the telling error line, any input file its oasislmf.json pointed at that
    wasn't there, and the failed command's full output.

    Args:
        run_config_entry: One entry as returned by build_benchmark_targets.
        error: The exception the run raised, or None if it worked.
        total_runtime_seconds: Wall-clock seconds the run took.
        tests_per_instance: 'separate' or 'shared', recorded in the manifest.

    Returns:
        dict: See _run_target.
    """
    result_directory = run_config_entry["run_config"]["RESULT_DIRECTORY"]
    manifest = None
    try:
        manifest = write_manifest(run_config_entry, result_directory, tests_per_instance)
    except Exception:
        logger.exception(f"Could not write the manifest for benchmark target '{run_config_entry['label']}'")

    runtime_seconds, step_timings = total_runtime_seconds, {}
    if error is None:
        model_runtime_seconds, step_timings = resolve_model_runtime(result_directory, total_runtime_seconds)
        runtime_seconds = round(model_runtime_seconds)

    result = {
        "label": run_config_entry["label"],
        "model": run_config_entry["model"],
        "test": run_config_entry["test"],
        "version": run_config_entry["version"],
        "status": "success" if error is None else "failed",
        "runtime_seconds": runtime_seconds,
        "total_runtime_seconds": total_runtime_seconds,
        "step_timings": step_timings,
    }
    if error is not None:
        failure = describe_failure(error)
        missing = missing_inputs(manifest)
        try:
            details = str(write_failure(result_directory, failure, missing))
        except Exception:
            logger.exception(f"Could not write the failure details for benchmark target '{run_config_entry['label']}'")
            details = None
        result["failure"] = {
            "stage": failure["stage"], "message": failure["message"], "missing_inputs": missing, "details": details,
        }
    return result


def _run_target(run_config_entry):
    """Run one benchmark target's model execution on an instance of its own and time its outcome.

    Reuses alpaca.model.main.main for the EC2 lifecycle (upload, run, download, terminate)
    rather than duplicating it, so a benchmark target runs exactly like an ordinary
    'alpaca model' run. The wall-clock time around that call includes EC2 startup, upload
    and download as well as the model run itself, so on success it's replaced as
    'runtime_seconds' by the model's own reported runtime (see resolve_model_runtime),
    with the wall-clock kept separately as 'total_runtime_seconds'. Every log line emitted
    during the call (including from other modules, e.g. alpaca.remote_controller) is tagged
    with this target's model/test/version via log_target, so concurrent targets' interleaved
    console output is distinguishable (see alpaca.logging_context.TargetFilter).

    Args:
        run_config_entry: One entry as returned by build_benchmark_targets, with 'label',
            'model', 'test', 'version' and 'run_config' keys.

    Returns:
        dict: {'label', 'model', 'test', 'version', 'status', 'runtime_seconds',
            'total_runtime_seconds', 'step_timings'}, plus 'failure' for a failed run.
            'label' is the target's own label, so a result can be traced back to the target
            that produced it. 'status' is 'success' unless the run raises, in which case it is
            'failed', the exception is logged, and 'failure' holds its 'stage', 'message',
            'missing_inputs' and the path of its failure.txt ('details'), see _finish_target.
            'step_timings' is a dict of every 'COMPLETED: <step> in <seconds>s' OasisLMF
            reported (e.g. 'execution.runner.run', 'computation.generate.files.run'), empty on
            failure or when result.txt couldn't be found/parsed.
    """
    start = time.monotonic()
    error = None
    name = group_name(run_config_entry["model"], run_config_entry["test"])
    with log_target(f"{name} {run_config_entry['version']}"):
        try:
            model_main(run_config_entry["run_config"])
        except Exception as raised:
            error = raised
            logger.exception(f"Benchmark target '{run_config_entry['label']}' failed")
        return _finish_target(run_config_entry, error, round(time.monotonic() - start), "separate")


def _run_shared_instance(entries):
    """Run several tests of one model at one OasisLMF install, in turn, on a single instance.

    OasisLMF is installed and the model pulled once, then each test runs from its own
    directory on the instance (see alpaca.model.commands.shared_test_commands) and is
    downloaded to its own target's RESULT_DIRECTORY, so from there on each test is a result
    like any other: timed, diffed, published and given a manifest on its own. A test that fails
    doesn't stop the ones after it. If the instance itself can't be set up, every test on it
    is reported as failed with that error.

    Args:
        entries: The targets sharing the instance, as returned by build_benchmark_targets: one
            model, one OasisLMF version or branch, a different test each.

    Returns:
        list[dict]: One result per entry, in entries order (see _run_target).
    """
    first = entries[0]
    results = {}
    start = time.monotonic()
    with log_target(f"{first['model']} {first['version']} (shared instance)"):
        try:
            with RemoteController(first["run_config"], REQUIRED_CONFIG_MODEL, OPTIONAL_CONFIG_MODEL) as controller:
                controller.upload_model(first["run_config"]["REPO_LOCATION"])
                for entry in entries:
                    results[entry["label"]] = _run_shared_test(controller, entry)
        except Exception as error:
            logger.exception(f"Shared instance for {first['model']} {first['version']} failed")
            for entry in entries:
                if entry["label"] not in results:
                    results[entry["label"]] = _finish_target(entry, error, round(time.monotonic() - start), "shared")
    return [results[entry["label"]] for entry in entries]


def _run_shared_test(controller, entry):
    """Run one test on a shared instance and download its results, without raising.

    Args:
        controller: The shared instance's RemoteController, already set up with the model.
        entry: The test's target, as returned by build_benchmark_targets.

    Returns:
        dict: The test's result (see _run_target).
    """
    run_directory = f"{SHARED_RUNS_DIRECTORY}/{entry['test']}"
    start = time.monotonic()
    error = None
    with log_target(f"{group_name(entry['model'], entry['test'])} {entry['version']}"):
        try:
            controller.run_commands(
                shared_test_commands(entry["run_config"]["PATH_TO_OASISLMF_JSON"], run_directory), log_condition, check=True
            )
        except Exception as raised:
            error = raised
            logger.exception(f"Benchmark target '{entry['label']}' failed")
        try:
            controller.download_results(f"/home/ubuntu/{run_directory}/runs", entry["run_config"]["RESULT_DIRECTORY"])
        except Exception as raised:
            logger.exception(f"Downloading the results of benchmark target '{entry['label']}' failed")
            error = error or raised
        return _finish_target(entry, error, round(time.monotonic() - start), "shared")


def instance_groups(run_configs, tests_per_instance="separate"):
    """Split targets into the groups that each run on one EC2 instance.

    Args:
        run_configs: List of entries as returned by build_benchmark_targets.
        tests_per_instance: 'separate' puts every target on an instance of its own; 'shared'
            puts every test of one model location at one OasisLMF version or branch together.

    Returns:
        list[list[dict]]: One list of targets per instance, in the order each instance's first
            target appears in run_configs.
    """
    if tests_per_instance != "shared":
        return [[entry] for entry in run_configs]
    groups = {}
    for entry in run_configs:
        run_config = entry["run_config"]
        key = (run_config["REPO_LOCATION"], run_config.get("OASISLMF_VERSION"), run_config.get("OASISLMF_BRANCH"))
        groups.setdefault(key, []).append(entry)
    return list(groups.values())


def _run_instance(group):
    """Run one instance's worth of targets: a target of its own, or several sharing it."""
    if len(group) == 1 and group[0].get("tests_per_instance", "separate") != "shared":
        return [_run_target(group[0])]
    return _run_shared_instance(group)


def run_benchmark_targets(run_configs, execution_mode="parallel", tests_per_instance="separate"):
    """Run every benchmark target's model execution and collect its result.

    Args:
        run_configs: List of entries as returned by build_benchmark_targets.
        execution_mode: 'parallel' runs instances concurrently, each in its own thread, up to
            MAX_PARALLEL_TARGETS at a time so that a large benchmark doesn't launch dozens of
            instances at once and run into an EC2 limit. Any beyond that wait for a slot.
            'sequential' runs them one after another.
        tests_per_instance: 'separate' (the default) runs every target on its own instance;
            'shared' runs a model's tests at one OasisLMF version in turn on one instance (see
            instance_groups and _run_shared_instance).

    Returns:
        list[dict]: One result per target, in run_configs order, each with 'label', 'model', 'test',
            'version', 'status', 'runtime_seconds', 'total_runtime_seconds' and
            'step_timings', plus 'failure' for a failed one (see _run_target).
    """
    groups = instance_groups(run_configs, tests_per_instance)
    if tests_per_instance == "shared":
        for group in groups:
            for entry in group:
                entry["tests_per_instance"] = "shared"

    if execution_mode == "sequential":
        group_results = [_run_instance(group) for group in groups]
    else:
        max_workers = min(len(groups), MAX_PARALLEL_TARGETS) or 1
        if len(groups) > max_workers:
            logger.info(f"Running {len(groups)} benchmark instances {max_workers} at a time")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_run_instance, group) for group in groups]
            group_results = [future.result() for future in futures]

    by_label = {result["label"]: result for results in group_results for result in results}
    return [by_label[entry["label"]] for entry in run_configs]
