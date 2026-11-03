from alpaca.benchmark.releases import (
    PYPI_URL, latest_oasislmf_release, previous_oasislmf_release, resolve_latest_versions
)
from alpaca.exceptions import OasisAlpacaConfigError
from unittest import mock
from urllib.error import URLError

import io
import json
import logging
import pytest


RELEASES = ["2.4.9", "2.5.7", "2.5.8", "2.5.9", "2.5.10rc1"]


def _files(yanked=False):
    return [{"filename": "oasislmf.whl", "yanked": yanked}]


def _pypi(version="2.5.9", releases=None):
    """Patch urlopen to answer like PyPI's JSON API, naming version as the latest release."""
    releases = {release: _files() for release in RELEASES} if releases is None else releases
    body = json.dumps({"info": {"version": version}, "releases": releases}).encode()
    return mock.patch("alpaca.benchmark.releases.urlopen", side_effect=lambda *args, **kwargs: io.BytesIO(body))


def test_latest_oasislmf_release_reads_pypis_latest_version():
    with _pypi("2.5.9") as fake_urlopen:
        assert latest_oasislmf_release() == "2.5.9"
    assert fake_urlopen.call_args.args[0] == PYPI_URL


@pytest.mark.parametrize("error", [URLError("no route"), TimeoutError("timed out")])
def test_latest_oasislmf_release_names_pypi_when_it_cannot_be_reached(error):
    with mock.patch("alpaca.benchmark.releases.urlopen", side_effect=error):
        with pytest.raises(OasisAlpacaConfigError, match="Could not find the OasisLMF releases on https://pypi.org"):
            latest_oasislmf_release()


def test_latest_oasislmf_release_raises_on_an_answer_that_is_not_json():
    with mock.patch("alpaca.benchmark.releases.urlopen", return_value=io.BytesIO(b"not json")):
        with pytest.raises(OasisAlpacaConfigError, match="Could not find the OasisLMF releases"):
            latest_oasislmf_release()


@pytest.mark.parametrize("project", [{"releases": {}}, {"info": None}, {"info": {"version": ""}}, {"info": {"version": 2}}])
def test_latest_oasislmf_release_raises_when_no_version_is_named(project):
    with pytest.raises(OasisAlpacaConfigError, match="didn't name a latest OasisLMF release"):
        latest_oasislmf_release(project)


@pytest.mark.parametrize("version, previous", [("2.5.9", "2.5.8"), ("2.5.8", "2.5.7"), ("2.5.7", "2.4.9"), ("2.5.10", "2.5.9")])
def test_previous_oasislmf_release_goes_by_version_number(version, previous):
    with _pypi():
        assert previous_oasislmf_release(version) == previous


def test_previous_oasislmf_release_ignores_an_older_line_published_later_and_sorts_numerically():
    """Neither upload order nor text order counts: 2.5.10 comes after 2.5.9, and 2.4.11 is still older."""
    releases = {release: _files() for release in ("2.4.11", "2.5.9", "2.5.10", "2.5.11")}

    with _pypi("2.5.11", releases):
        assert previous_oasislmf_release("2.5.11") == "2.5.10"


def test_previous_oasislmf_release_skips_yanked_and_empty_releases_and_pre_releases():
    releases = {
        "2.5.6": _files(), "2.5.7": [], "2.5.8": _files(yanked=True), "2.5.9rc1": _files(), "2.5.9": _files(),
    }

    with _pypi("2.5.9", releases):
        assert previous_oasislmf_release("2.5.9") == "2.5.6"


def test_previous_oasislmf_release_raises_when_nothing_came_before():
    with _pypi():
        with pytest.raises(OasisAlpacaConfigError, match="lists no OasisLMF release before 2.4.9"):
            previous_oasislmf_release("2.4.9")


@pytest.mark.parametrize("project", [{}, {"releases": None}, []])
def test_previous_oasislmf_release_raises_when_pypi_lists_no_releases(project):
    with pytest.raises(OasisAlpacaConfigError, match="lists no OasisLMF release before 2.5.9"):
        previous_oasislmf_release("2.5.9", project)


def test_previous_oasislmf_release_needs_a_plain_release_to_look_before():
    with mock.patch("alpaca.benchmark.releases.urlopen") as fake_urlopen:
        with pytest.raises(OasisAlpacaConfigError, match="needs a plain release to look before, got '2.5.10rc1'"):
            previous_oasislmf_release("2.5.10rc1")
    fake_urlopen.assert_not_called()


def test_resolve_latest_versions_replaces_the_test_version(caplog):
    config = {"OASISLMF_BASELINE_VERSION": "2.5.8", "OASISLMF_TEST_VERSION": "latest"}

    with _pypi("2.5.9"), caplog.at_level(logging.INFO, logger="alpaca.benchmark.releases"):
        resolve_latest_versions(config)

    assert config == {"OASISLMF_BASELINE_VERSION": "2.5.8", "OASISLMF_TEST_VERSION": "2.5.9"}
    assert "OASISLMF_TEST_VERSION 'latest' is OasisLMF 2.5.9" in caplog.text


def test_resolve_latest_versions_replaces_a_versions_entry_and_drops_a_repeat():
    config = {"OASISLMF_VERSIONS": ["2.5.8", "latest", "2.5.9"]}

    with _pypi("2.5.9"):
        resolve_latest_versions(config)

    assert config["OASISLMF_VERSIONS"] == ["2.5.8", "2.5.9"]


def test_resolve_latest_versions_leaves_pinned_versions_alone_without_asking_pypi():
    config = {"OASISLMF_BASELINE_VERSION": "2.5.8", "OASISLMF_TEST_VERSION": "2.5.9", "OASISLMF_VERSIONS": []}

    with mock.patch("alpaca.benchmark.releases.urlopen") as fake_urlopen:
        resolve_latest_versions(config)

    fake_urlopen.assert_not_called()
    assert config["OASISLMF_TEST_VERSION"] == "2.5.9"


def test_resolve_latest_versions_asks_pypi_once_for_several_keys():
    config = {"OASISLMF_BASELINE_VERSION": "previous", "OASISLMF_TEST_VERSION": "latest", "OASISLMF_VERSIONS": ["latest"]}

    with _pypi("2.5.9") as fake_urlopen:
        resolve_latest_versions(config)

    assert fake_urlopen.call_count == 1
    assert config == {"OASISLMF_BASELINE_VERSION": "2.5.8", "OASISLMF_TEST_VERSION": "2.5.9", "OASISLMF_VERSIONS": ["2.5.9"]}


def test_resolve_latest_versions_stops_when_there_is_no_release_since_the_baseline():
    config = {"OASISLMF_BASELINE_VERSION": "2.5.9", "OASISLMF_TEST_VERSION": "latest"}

    with _pypi("2.5.9"):
        with pytest.raises(OasisAlpacaConfigError, match="'latest' is 2.5.9, the same as OASISLMF_BASELINE_VERSION"):
            resolve_latest_versions(config)


def test_resolve_latest_versions_compares_the_latest_release_with_the_previous_one(caplog):
    config = {"OASISLMF_BASELINE_VERSION": "previous", "OASISLMF_TEST_VERSION": "latest"}

    with _pypi("2.5.9"), caplog.at_level(logging.INFO, logger="alpaca.benchmark.releases"):
        resolve_latest_versions(config)

    assert config == {"OASISLMF_BASELINE_VERSION": "2.5.8", "OASISLMF_TEST_VERSION": "2.5.9"}
    assert "OASISLMF_BASELINE_VERSION 'previous' is OasisLMF 2.5.8, the release before 2.5.9" in caplog.text


def test_resolve_latest_versions_finds_the_release_before_a_pinned_test_version():
    config = {"OASISLMF_BASELINE_VERSION": "previous", "OASISLMF_TEST_VERSION": "2.5.8"}

    with _pypi("2.5.9"):
        resolve_latest_versions(config)

    assert config["OASISLMF_BASELINE_VERSION"] == "2.5.7"


@pytest.mark.parametrize("config, message", [
    ({"OASISLMF_BASELINE_VERSION": "latest", "OASISLMF_TEST_VERSION": "2.5.9"}, "OASISLMF_BASELINE_VERSION can't be 'latest'"),
    ({"OASISLMF_BASELINE_VERSION": "2.5.8", "OASISLMF_TEST_VERSION": "previous"}, "Only OASISLMF_BASELINE_VERSION can be 'previous'"),
    ({"OASISLMF_VERSIONS": ["previous", "2.5.9"]}, "Only OASISLMF_BASELINE_VERSION can be 'previous'"),
    ({"OASISLMF_BASELINE_VERSION": "previous"}, "'previous' needs OASISLMF_TEST_VERSION"),
])
def test_resolve_latest_versions_rejects_a_keyword_where_it_cannot_be_used(config, message):
    with mock.patch("alpaca.benchmark.releases.urlopen") as fake_urlopen:
        with pytest.raises(OasisAlpacaConfigError, match=message):
            resolve_latest_versions(config)
    fake_urlopen.assert_not_called()
