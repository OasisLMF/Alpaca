from alpaca.exceptions import OasisAlpacaConfigError
from urllib.parse import urlparse
import logging
import re

logger = logging.getLogger(__name__)

VALID_EXECUTION_MODES = {"parallel", "sequential"}


def model_name_from_location(location):
    """Derive a short, human-readable model name from a repo location.

    Args:
        location: S3 URI (e.g., 's3://bucket/path') or GitHub URL
            (e.g., 'https://github.com/OasisLMF/OasisPiWind').

    Returns:
        str: The final path segment of the location. For GitHub repos, a leading
            'Oasis' is stripped (e.g. 'OasisPiWind' -> 'PiWind'), as that prefix is
            on nearly every model repo and adds nothing to a benchmark plan.
    """
    if location.startswith("s3://"):
        return location.rstrip("/").split("/")[-1]
    if "github.com" in location:
        repo_name = re.split(r"[/.]", urlparse(location).path)[2]
        return re.sub(r"^Oasis", "", repo_name) or repo_name
    return location


def _target_label(branch, version):
    """Build a human-readable install-source label for one benchmark target.

    Args:
        branch: OASISLMF_BRANCH/OASISLMF_BRANCH_COMPARISON for this target, or None.
        version: OASISLMF_VERSION/OASISLMF_VERSION_COMPARISON for this target, or None.

    Returns:
        str: 'OasisLMF branch:{branch}' when a branch is set (it always takes priority
            over a version, see build_model_run_configs), otherwise 'OasisLMF {version}',
            using 'latest' when neither is set.
    """
    if branch:
        return f"OasisLMF branch:{branch}"
    return f"OasisLMF {version or 'latest'}"


def build_benchmark_plan(config):
    """Build a benchmark plan from a validated benchmark config.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        dict: With keys 'models' (model names from REPO_LOCATION and, if present,
            REPO_LOCATION_COMPARISON, deduplicated), 'comparisons' (list of per-target
            install-source labels, see _target_label; when REPO_LOCATION_COMPARISON is
            omitted but OASISLMF_VERSION_COMPARISON is set, that entry is labelled as an
            S3 baseline rather than a second live run) and 'execution_mode'.

    Raises:
        OasisAlpacaConfigError: If EXECUTION_MODE is set to something other than
            'parallel' or 'sequential'.
    """
    locations = [config["REPO_LOCATION"]]
    if config.get("REPO_LOCATION_COMPARISON"):
        locations.append(config["REPO_LOCATION_COMPARISON"])

    models = []
    for location in locations:
        name = model_name_from_location(location)
        if name not in models:
            models.append(name)

    comparisons = [_target_label(config.get("OASISLMF_BRANCH"), config.get("OASISLMF_VERSION"))]
    if config.get("REPO_LOCATION_COMPARISON"):
        comparisons.append(_target_label(config.get("OASISLMF_BRANCH_COMPARISON"), config.get("OASISLMF_VERSION_COMPARISON")))
    else:
        if config.get("OASISLMF_BRANCH_COMPARISON"):
            logger.warning(
                "OASISLMF_BRANCH_COMPARISON only applies in dual-target mode (REPO_LOCATION_COMPARISON "
                "set); ignoring it for this single-run benchmark"
            )
        if config.get("OASISLMF_VERSION_COMPARISON"):
            comparisons.append(f"OasisLMF {config['OASISLMF_VERSION_COMPARISON']} (S3 baseline)")

    execution_mode = config.get("EXECUTION_MODE", "parallel")
    if execution_mode not in VALID_EXECUTION_MODES:
        raise OasisAlpacaConfigError(
            f"EXECUTION_MODE must be one of {sorted(VALID_EXECUTION_MODES)}, got '{execution_mode}'"
        )

    return {"models": models, "comparisons": comparisons, "execution_mode": execution_mode}


def build_execution_plan(config):
    """Build the baseline and comparison execution targets for a benchmark run.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        dict: {'baseline': {'version': ...}, 'comparison': {'version': ...}}. The
            baseline target uses OASISLMF_VERSION and the comparison target uses
            OASISLMF_VERSION_COMPARISON, each falling back to 'latest' when unset,
            matching how a missing OASISLMF_VERSION defaults to the newest PyPI
            release elsewhere in Alpaca.
    """
    return {
        "baseline": {"version": config.get("OASISLMF_VERSION") or "latest"},
        "comparison": {"version": config.get("OASISLMF_VERSION_COMPARISON") or "latest"},
    }


SHARED_MODEL_CONFIG_KEYS = [
    "AMI_ID", "SECURITY_GROUP_ID", "SUBNET_ID", "IAM_INSTANCE_PROFILE", "PATH_TO_OASISLMF_JSON",
    "AWS_REGION", "INSTANCE_TYPE", "DISK_GB", "LOG_LEVEL",
    "MAX_LIFETIME_HOURS", "SSH_MAX_RETRIES", "AWS_PROFILE", "DEBUG"
]


def build_model_run_configs(config):
    """Build a per-target model-run config for each side of a benchmark.

    Each target reuses every shared EC2 setting from the benchmark config, but gets its
    own REPO_LOCATION, OASISLMF_VERSION/OASISLMF_BRANCH, EC2_NAME and RESULT_DIRECTORY,
    since the runs execute as ordinary, independent 'alpaca model' runs (which may happen
    concurrently) and must not race on the same instance settings or output directory.
    OASISLMF_BRANCH (baseline) and OASISLMF_BRANCH_COMPARISON (comparison) are scoped the
    same way as OASISLMF_VERSION/OASISLMF_VERSION_COMPARISON - independently per target,
    with no fallback to one another - and a branch always takes priority over a version
    on its own target (see alpaca.scripts.oasislmf_install_commands). EC2_NAME is always
    derived as 'Alpaca {model} {version}' (e.g. 'Alpaca PiWind 2.5.4', or 'Alpaca PiWind
    branch:my-branch'), overriding any EC2_NAME set at the top level, so concurrent
    instances are identifiable in the AWS console rather than all sharing one name.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        list[dict]: One entry (single-run mode) if REPO_LOCATION_COMPARISON is unset, or
            two entries in baseline-then-comparison order otherwise, each with keys
            'label' ('baseline' or 'comparison'), 'model' (short model name, see
            model_name_from_location), 'version' (the pinned version, 'branch:{name}' when
            a branch is set, or 'latest' when neither is) and 'run_config' (a config dict
            suitable for alpaca.model.main.main).
    """
    targets = [("baseline", config["REPO_LOCATION"], config.get("OASISLMF_VERSION"), config.get("OASISLMF_BRANCH"))]
    if config.get("REPO_LOCATION_COMPARISON"):
        targets.append((
            "comparison", config["REPO_LOCATION_COMPARISON"],
            config.get("OASISLMF_VERSION_COMPARISON"), config.get("OASISLMF_BRANCH_COMPARISON"),
        ))
    result_directory = config.get("RESULT_DIRECTORY", "./runs").rstrip("/")

    run_configs = []
    for label, repo_location, version, branch in targets:
        model = model_name_from_location(repo_location)
        version_label = f"branch:{branch}" if branch else (version or "latest")
        run_config = {key: config[key] for key in SHARED_MODEL_CONFIG_KEYS if key in config}
        run_config["EC2_NAME"] = f"Alpaca {model} {version_label}"
        run_config["REPO_LOCATION"] = repo_location
        run_config["RESULT_DIRECTORY"] = f"{result_directory}/{label}"
        if branch:
            run_config["OASISLMF_BRANCH"] = branch
        elif version:
            run_config["OASISLMF_VERSION"] = version
        run_configs.append({
            "label": label,
            "model": model,
            "version": version_label,
            "run_config": run_config,
        })
    return run_configs


def format_benchmark_plan(plan):
    """Format a benchmark plan for display.

    Args:
        plan: dict as returned by build_benchmark_plan, with 'models',
            'comparisons' and 'execution_mode' keys.

    Returns:
        str: Human-readable multi-line benchmark plan.
    """
    lines = ["Benchmark configuration loaded", "", "Models:"]
    lines.extend(f"- {model}" for model in plan["models"])
    lines.append("")
    lines.append("Comparison:")
    lines.extend(f"- {comparison}" for comparison in plan["comparisons"])
    lines.append("")
    lines.append("Execution mode:")
    lines.append(plan["execution_mode"])
    return "\n".join(lines)
