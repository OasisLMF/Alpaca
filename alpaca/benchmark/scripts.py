from alpaca.exceptions import OasisAlpacaConfigError
from urllib.parse import urlparse
import re

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


def build_benchmark_plan(config):
    """Build a benchmark plan from a validated benchmark config.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        dict: With keys 'models' (model names from REPO_LOCATION and
            REPO_LOCATION_COMPARISON, deduplicated), 'comparisons' (list of
            'OasisLMF {version}' strings, using 'latest' where a version isn't
            pinned) and 'execution_mode'.

    Raises:
        OasisAlpacaConfigError: If EXECUTION_MODE is set to something other than
            'parallel' or 'sequential'.
    """
    models = []
    for location in (config["REPO_LOCATION"], config["REPO_LOCATION_COMPARISON"]):
        name = model_name_from_location(location)
        if name not in models:
            models.append(name)

    comparisons = [
        f"OasisLMF {config.get('OASISLMF_VERSION') or 'latest'}",
        f"OasisLMF {config.get('OASISLMF_VERSION_COMPARISON') or 'latest'}",
    ]

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
