from alpaca.exceptions import OasisAlpacaConfigError
from urllib.error import URLError
from urllib.request import urlopen

import json
import logging
import re

logger = logging.getLogger(__name__)

LATEST = "latest"
PREVIOUS = "previous"
PYPI_URL = "https://pypi.org/pypi/oasislmf/json"
PYPI_TIMEOUT_SECONDS = 30
RELEASE_VERSION = re.compile(r"^\d+(\.\d+)*$")


def _pypi_project():
    """Fetch OasisLMF's project details from PyPI's JSON API.

    Returns:
        dict: PyPI's answer, with 'info' (holding the latest 'version') and 'releases'
            (version -> list of uploaded files, each with a 'yanked' flag).

    Raises:
        OasisAlpacaConfigError: If PyPI can't be reached or doesn't answer with JSON. This runs
            before any EC2 spend, so a benchmark that can't tell what to run stops there.
    """
    try:
        with urlopen(PYPI_URL, timeout=PYPI_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (URLError, OSError, ValueError) as error:
        raise OasisAlpacaConfigError(f"Could not find the OasisLMF releases on {PYPI_URL}: {error}")


def latest_oasislmf_release(project=None):
    """Find the newest OasisLMF release on PyPI.

    Args:
        project: PyPI's answer from _pypi_project, or None to fetch it.

    Returns:
        str: PyPI's own 'latest' version for oasislmf, e.g. '2.5.9', which leaves out
            pre-releases and yanked releases, so it's what 'pip install oasislmf' would install.

    Raises:
        OasisAlpacaConfigError: If PyPI can't be reached or doesn't name a version.
    """
    project = _pypi_project() if project is None else project
    try:
        version = project["info"]["version"]
    except (KeyError, TypeError):
        version = None
    if not isinstance(version, str) or not version:
        raise OasisAlpacaConfigError(f"{PYPI_URL} didn't name a latest OasisLMF release")
    return version


def _release_key(version):
    """Turn a plain release version, e.g. '2.5.10', into something that sorts by version number.

    Returns:
        tuple[int, ...] or None: (2, 5, 10), or None for anything that isn't a plain release,
            e.g. a pre-release such as '2.5.0rc1'.
    """
    return tuple(int(part) for part in version.split(".")) if RELEASE_VERSION.match(version) else None


def previous_oasislmf_release(version, project=None):
    """Find the OasisLMF release just before a version, by version number rather than upload date.

    A maintenance release of an older line (a 2.4.x published after 2.5.9, say) is never the
    release before 2.5.9, and nor is a pre-release or a release whose files were all yanked.

    Args:
        version: The release to look before, e.g. '2.5.9'.
        project: PyPI's answer from _pypi_project, or None to fetch it.

    Returns:
        str: The highest plain release lower than version, e.g. '2.5.8'.

    Raises:
        OasisAlpacaConfigError: If PyPI can't be reached, version isn't a plain release, or
            there's no release before it.
    """
    target = _release_key(version)
    if target is None:
        raise OasisAlpacaConfigError(f"OASISLMF_BASELINE_VERSION 'previous' needs a plain release to look before, got '{version}'")
    project = _pypi_project() if project is None else project
    releases = project.get("releases") if isinstance(project, dict) else None
    earlier = [
        (key, release)
        for release, files in (releases or {}).items()
        if (key := _release_key(release)) is not None and key < target
        and files and not all(file.get("yanked") for file in files)
    ]
    if not earlier:
        raise OasisAlpacaConfigError(f"{PYPI_URL} lists no OasisLMF release before {version}")
    return max(earlier)[1]


def resolve_latest_versions(config):
    """Replace 'latest' and 'previous' in a benchmark config with real OasisLMF releases, before anything else reads it.

    'latest' (the newest release) can be OASISLMF_TEST_VERSION, so a scheduled benchmark tests
    each new release without its config being edited, or an OASISLMF_VERSIONS entry.
    'previous' can only be OASISLMF_BASELINE_VERSION: the release just before the test version
    (see previous_oasislmf_release), so each release is compared with the one it replaced.
    PyPI is only asked once, however many keys need it.

    Args:
        config: Validated benchmark configuration dictionary, updated in place.

    Raises:
        OasisAlpacaConfigError: If 'latest' or 'previous' is given where it can't be used, if
            PyPI can't answer, if there's no release before the test version, or if
            OASISLMF_TEST_VERSION is 'latest' and that's the baseline version, i.e. there's been
            no release since the baseline.
    """
    baseline = config.get("OASISLMF_BASELINE_VERSION")
    test = config.get("OASISLMF_TEST_VERSION")
    versions = config.get("OASISLMF_VERSIONS") or []
    if baseline == LATEST:
        raise OasisAlpacaConfigError(
            "OASISLMF_BASELINE_VERSION can't be 'latest'; set it to the stored version new releases are compared "
            "against, or 'previous' for the release before OASISLMF_TEST_VERSION"
        )
    if test == PREVIOUS or PREVIOUS in versions:
        raise OasisAlpacaConfigError("Only OASISLMF_BASELINE_VERSION can be 'previous', as the release before OASISLMF_TEST_VERSION")
    if baseline == PREVIOUS and not test:
        raise OasisAlpacaConfigError("OASISLMF_BASELINE_VERSION 'previous' needs OASISLMF_TEST_VERSION, the release it's the one before")
    if test != LATEST and LATEST not in versions and baseline != PREVIOUS:
        return

    project = _pypi_project()
    if test == LATEST:
        latest = latest_oasislmf_release(project)
        if latest == baseline:
            raise OasisAlpacaConfigError(
                f"OASISLMF_TEST_VERSION 'latest' is {latest}, the same as OASISLMF_BASELINE_VERSION, so there's no "
                f"newer release to benchmark"
            )
        config["OASISLMF_TEST_VERSION"] = test = latest
        logger.info(f"OASISLMF_TEST_VERSION 'latest' is OasisLMF {latest}")
    if baseline == PREVIOUS:
        config["OASISLMF_BASELINE_VERSION"] = previous = previous_oasislmf_release(test, project)
        logger.info(f"OASISLMF_BASELINE_VERSION 'previous' is OasisLMF {previous}, the release before {test}")
    if LATEST in versions:
        latest = latest_oasislmf_release(project)
        resolved = []
        for version in versions:
            version = latest if version == LATEST else version
            if version not in resolved:
                resolved.append(version)
        config["OASISLMF_VERSIONS"] = resolved
        logger.info(f"OASISLMF_VERSIONS 'latest' is OasisLMF {latest}")
