from alpaca.exceptions import OasisAlpacaConfigError
from urllib.parse import urlparse
import logging
import re

logger = logging.getLogger(__name__)

VALID_EXECUTION_MODES = {"parallel", "sequential"}
LIVE_SOURCE = "live"
STORED_SOURCE = "stored"


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


def benchmark_locations(config):
    """List the model locations a benchmark runs, in configured order without duplicates.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        list[str]: Every REPO_LOCATIONS entry, deduplicated so listing the same model twice
            doesn't run it twice.
    """
    locations = []
    for location in config.get("REPO_LOCATIONS") or []:
        if location and location not in locations:
            locations.append(location)
    return locations


def oasislmf_sources(config):
    """List the OasisLMF installs a benchmark compares, in configured order.

    Either key on its own is enough, and so is a single entry (which gets a timed run, just
    nothing to compare its output against), but a benchmark with neither has nothing to
    install and is rejected rather than quietly run against whatever PyPI's latest release
    happens to be that day.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        list[tuple]: One (branch, version) pair per install, where exactly one of the two is
            set: OASISLMF_VERSIONS entries first, then OASISLMF_BRANCHES entries, without
            duplicates.

    Raises:
        OasisAlpacaConfigError: If neither OASISLMF_VERSIONS nor OASISLMF_BRANCHES holds an
            entry.
    """
    sources = [(None, version) for version in config.get("OASISLMF_VERSIONS") or [] if version]
    sources.extend((branch, None) for branch in config.get("OASISLMF_BRANCHES") or [] if branch)

    deduplicated = []
    for source in sources:
        if source not in deduplicated:
            deduplicated.append(source)
    if not deduplicated:
        raise OasisAlpacaConfigError("OASISLMF_VERSIONS or OASISLMF_BRANCHES must hold at least one entry to benchmark")
    return deduplicated


def source_label(branch, version):
    """Build a human-readable install-source label for one benchmark target.

    Args:
        branch: OASISLMF_BRANCHES entry for this target, or None when it's a version target.
        version: OASISLMF_VERSIONS entry for this target, or None when it's a branch target.

    Returns:
        str: 'OasisLMF branch:{branch}' for a branch target, otherwise 'OasisLMF {version}'.
    """
    return f"OasisLMF branch:{branch}" if branch else f"OasisLMF {version}"


def resolve_execution_mode(config):
    """Read and validate EXECUTION_MODE from a benchmark config.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        str: 'parallel' (the default) or 'sequential'.

    Raises:
        OasisAlpacaConfigError: If EXECUTION_MODE is set to anything else.
    """
    execution_mode = config.get("EXECUTION_MODE", "parallel")
    if execution_mode not in VALID_EXECUTION_MODES:
        raise OasisAlpacaConfigError(
            f"EXECUTION_MODE must be one of {sorted(VALID_EXECUTION_MODES)}, got '{execution_mode}'"
        )
    return execution_mode


def build_benchmark_plan(config, targets):
    """Build a benchmark plan for display from a validated config and its targets.

    Args:
        config: Validated benchmark configuration dictionary.
        targets: List of targets as returned by build_benchmark_targets.

    Returns:
        dict: With keys 'models' (each distinct model name under benchmark, see
            model_name_from_location), 'targets' (one '{model}: {install source}' line per
            target, marking any target taken from a stored S3 baseline rather than run) and
            'execution_mode'.

    Raises:
        OasisAlpacaConfigError: If EXECUTION_MODE is set to something other than
            'parallel' or 'sequential'.
    """
    models = []
    for target in targets:
        if target["model"] not in models:
            models.append(target["model"])

    target_lines = []
    for target in targets:
        suffix = " (S3 baseline)" if target["source"] == STORED_SOURCE else ""
        target_lines.append(f"{target['model']}: {target['source_label']}{suffix}")

    return {"models": models, "targets": target_lines, "execution_mode": resolve_execution_mode(config)}


SHARED_MODEL_CONFIG_KEYS = [
    "AMI_ID", "SECURITY_GROUP_ID", "SUBNET_ID", "IAM_INSTANCE_PROFILE", "PATH_TO_OASISLMF_JSON",
    "AWS_REGION", "INSTANCE_TYPE", "DISK_GB", "LOG_LEVEL",
    "MAX_LIFETIME_HOURS", "SSH_MAX_RETRIES", "AWS_PROFILE", "DEBUG"
]


def _target_slug(model, version_label, taken):
    """Build a unique, path-safe directory name for one benchmark target.

    Args:
        model: Short model name for the target.
        version_label: The target's version label, e.g. '2.5.6' or 'branch:my-branch'.
        taken: Slugs already used by earlier targets, to disambiguate against.

    Returns:
        str: '{model}-{version_label}' with anything outside [A-Za-z0-9._-] replaced by '-',
            suffixed with a counter if an earlier target already claimed that name (two
            locations can share a model name).
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{model}-{version_label}").strip("-")
    if slug not in taken:
        return slug
    suffix = 2
    while f"{slug}-{suffix}" in taken:
        suffix += 1
    return f"{slug}-{suffix}"


def build_benchmark_targets(config, stored_versions=()):
    """Build one benchmark target per model location and OasisLMF install under comparison.

    Targets are peers: every location in REPO_LOCATIONS is paired with every OasisLMF
    install in OASISLMF_VERSIONS/OASISLMF_BRANCHES, and all of them are run, timed and
    diffed against each other (see alpaca.benchmark.main). Each target reuses every shared
    EC2 setting from the benchmark config but gets its own REPO_LOCATION,
    OASISLMF_VERSION/OASISLMF_BRANCH, EC2_NAME and RESULT_DIRECTORY, since the runs execute
    as ordinary, independent 'alpaca model' runs (which may happen concurrently) and must
    not race on the same instance settings or output directory. A branch always takes
    priority over a version on its own target (see alpaca.commands.oasislmf_install_commands),
    so a branch target carries no version at all. EC2_NAME is always derived as
    'Alpaca {model} {version}' (e.g. 'Alpaca PiWind 2.5.4', or 'Alpaca PiWind
    branch:my-branch'), overriding any EC2_NAME set at the top level, so concurrent
    instances are identifiable in the AWS console rather than all sharing one name.

    Args:
        config: Validated benchmark configuration dictionary.
        stored_versions: Versions already held in BENCHMARK_BUCKET (see
            alpaca.benchmark.s3_baseline.resolve_stored_versions). A version target listed
            here is marked as stored, and is downloaded instead of run on EC2.

    Returns:
        list[dict]: One entry per target, location by location, each with keys 'label' (a
            unique, path-safe name for the target), 'model' (short model name, see
            model_name_from_location), 'version' (the pinned version, or 'branch:{name}' when
            a branch is set), 'source_label' (see source_label),
            'source' (LIVE_SOURCE, or STORED_SOURCE when it comes from BENCHMARK_BUCKET) and
            'run_config' (a config dict suitable for alpaca.model.main.main).

    Raises:
        OasisAlpacaConfigError: If REPO_LOCATIONS holds no model to benchmark, or neither
            OASISLMF_VERSIONS nor OASISLMF_BRANCHES holds an entry (see oasislmf_sources).
    """
    locations = benchmark_locations(config)
    if not locations:
        raise OasisAlpacaConfigError("REPO_LOCATIONS must hold at least one model location to benchmark")

    result_directory = config.get("RESULT_DIRECTORY", "./runs").rstrip("/")
    sources = oasislmf_sources(config)

    targets = []
    labels = set()
    for location in locations:
        model = model_name_from_location(location)
        for branch, version in sources:
            version_label = f"branch:{branch}" if branch else version
            label = _target_slug(model, version_label, labels)
            labels.add(label)

            run_config = {key: config[key] for key in SHARED_MODEL_CONFIG_KEYS if key in config}
            run_config["EC2_NAME"] = f"Alpaca {model} {version_label}"
            run_config["REPO_LOCATION"] = location
            run_config["RESULT_DIRECTORY"] = f"{result_directory}/{label}"
            if branch:
                run_config["OASISLMF_BRANCH"] = branch
            else:
                run_config["OASISLMF_VERSION"] = version

            targets.append({
                "label": label,
                "model": model,
                "version": version_label,
                "source_label": source_label(branch, version),
                "source": STORED_SOURCE if version and version in stored_versions else LIVE_SOURCE,
                "run_config": run_config,
            })
    return targets


def format_benchmark_plan(plan):
    """Format a benchmark plan for display.

    Args:
        plan: dict as returned by build_benchmark_plan, with 'models', 'targets' and
            'execution_mode' keys.

    Returns:
        str: Human-readable multi-line benchmark plan.
    """
    lines = ["Benchmark configuration loaded", "", "Models:"]
    lines.extend(f"- {model}" for model in plan["models"])
    lines.append("")
    lines.append("Targets:")
    lines.extend(f"- {target}" for target in plan["targets"])
    lines.append("")
    lines.append("Execution mode:")
    lines.append(plan["execution_mode"])
    return "\n".join(lines)
