from alpaca.benchmark.utils import (
    REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK, validate_tests_config, validate_tests_per_instance,
    validate_version_pair_config
)
from alpaca.exceptions import OasisAlpacaConfigError
from alpaca.inputs import (
    REPO_LOCATION, REPO_LOCATIONS, OASISLMF_VERSION, OASISLMF_VERSIONS, BENCHMARK_BUCKET, PUBLISH_BASELINE,
    OASISLMF_BRANCH, OASISLMF_BRANCHES, PATH_TO_OASISLMF_JSON, TESTS, OASISLMF_BASELINE_VERSION, OASISLMF_TEST_VERSION
)

import pytest


def test_required_config_benchmark_requires_the_model_locations():
    """Test that a benchmark is configured with a list of locations rather than the single
    REPO_LOCATION the other run modes take.
    """
    assert REPO_LOCATIONS in REQUIRED_CONFIG_BENCHMARK
    assert REPO_LOCATION not in REQUIRED_CONFIG_BENCHMARK
    assert REPO_LOCATION not in OPTIONAL_CONFIG_BENCHMARK


def test_optional_config_benchmark_includes_s3_baseline_keys():
    """Test that the S3 baseline reporting keys are optional."""
    assert BENCHMARK_BUCKET in OPTIONAL_CONFIG_BENCHMARK
    assert PUBLISH_BASELINE in OPTIONAL_CONFIG_BENCHMARK


def test_optional_config_benchmark_takes_lists_of_versions_and_branches():
    """Test that a benchmark takes the plural version/branch keys, and that the singular
    ones are gone, since every target now comes from the lists.
    """
    assert OASISLMF_VERSIONS in OPTIONAL_CONFIG_BENCHMARK
    assert OASISLMF_BRANCHES in OPTIONAL_CONFIG_BENCHMARK
    assert OASISLMF_VERSION not in OPTIONAL_CONFIG_BENCHMARK
    assert OASISLMF_BRANCH not in OPTIONAL_CONFIG_BENCHMARK


def test_list_config_keys_declare_list_defaults():
    """Test that the list-valued keys declare themselves as lists, which is what makes
    alpaca.config parse them as JSON arrays.
    """
    for key in (REPO_LOCATIONS, OASISLMF_VERSIONS, OASISLMF_BRANCHES, TESTS):
        assert isinstance(key[2], list)


def test_required_and_optional_config_benchmark_do_not_overlap():
    """Test that no config key is listed as both required and optional."""
    required_keys = {key for key, _, _ in REQUIRED_CONFIG_BENCHMARK}
    optional_keys = {key for key, _, _ in OPTIONAL_CONFIG_BENCHMARK}
    assert required_keys.isdisjoint(optional_keys)


def test_path_to_oasislmf_json_and_tests_are_both_optional():
    """Either one names what a target runs, so neither is required on its own."""
    assert PATH_TO_OASISLMF_JSON in OPTIONAL_CONFIG_BENCHMARK
    assert TESTS in OPTIONAL_CONFIG_BENCHMARK


def test_validate_tests_config_accepts_path_to_oasislmf_json_alone():
    validate_tests_config({"PATH_TO_OASISLMF_JSON": "./oasislmf.json"})


def test_validate_tests_config_accepts_tests_alone():
    validate_tests_config({"TESTS": ["test_1", "test_2"]})


def test_validate_tests_config_raises_without_either():
    with pytest.raises(OasisAlpacaConfigError, match="PATH_TO_OASISLMF_JSON or TESTS is required"):
        validate_tests_config({"TESTS": []})


def test_validate_tests_config_raises_with_both():
    """A target runs one oasislmf.json, so it's unclear which one to use when both are set."""
    with pytest.raises(OasisAlpacaConfigError, match="not both"):
        validate_tests_config({"PATH_TO_OASISLMF_JSON": "./oasislmf.json", "TESTS": ["test_1"]})


@pytest.mark.parametrize("test", ["tests/test_1", "test_1/oasislmf.json", "..", "."])
def test_validate_tests_config_raises_on_a_test_that_is_not_a_directory_name(test):
    with pytest.raises(OasisAlpacaConfigError, match="directory name under tests/"):
        validate_tests_config({"TESTS": [test]})


def test_optional_config_benchmark_includes_the_baseline_and_test_versions():
    assert OASISLMF_BASELINE_VERSION in OPTIONAL_CONFIG_BENCHMARK
    assert OASISLMF_TEST_VERSION in OPTIONAL_CONFIG_BENCHMARK


def test_validate_version_pair_config_passes_when_neither_is_set():
    validate_version_pair_config({"OASISLMF_VERSIONS": ["2.5.7", "2.5.8"]})


def test_validate_version_pair_config_accepts_the_pair():
    validate_version_pair_config({"OASISLMF_BASELINE_VERSION": "2.5.7", "OASISLMF_TEST_VERSION": "2.5.8"})


def test_validate_version_pair_config_accepts_the_pair_alongside_branches():
    """Branches always run live anyway, so they can join the pair as extra targets."""
    validate_version_pair_config({
        "OASISLMF_BASELINE_VERSION": "2.5.7", "OASISLMF_TEST_VERSION": "2.5.8", "OASISLMF_BRANCHES": ["main"],
    })


@pytest.mark.parametrize("key", ["OASISLMF_BASELINE_VERSION", "OASISLMF_TEST_VERSION"])
def test_validate_version_pair_config_raises_on_half_a_pair(key):
    """A baseline with no test version, or the other way round, has nothing to compare against."""
    with pytest.raises(OasisAlpacaConfigError, match="must be set together"):
        validate_version_pair_config({key: "2.5.7"})


def test_validate_version_pair_config_raises_alongside_oasislmf_versions():
    """It'd be unclear which OASISLMF_VERSIONS entries are baselines and which always run."""
    with pytest.raises(OasisAlpacaConfigError, match="not both"):
        validate_version_pair_config({
            "OASISLMF_BASELINE_VERSION": "2.5.7", "OASISLMF_TEST_VERSION": "2.5.8", "OASISLMF_VERSIONS": ["2.5.6"],
        })


def test_validate_version_pair_config_raises_when_both_are_the_same_version():
    with pytest.raises(OasisAlpacaConfigError, match="both '2.5.7'"):
        validate_version_pair_config({"OASISLMF_BASELINE_VERSION": "2.5.7", "OASISLMF_TEST_VERSION": "2.5.7"})


def test_validate_tests_per_instance_defaults_to_separate():
    assert validate_tests_per_instance({}) == "separate"


def test_validate_tests_per_instance_accepts_shared_with_tests():
    assert validate_tests_per_instance({"TESTS_PER_INSTANCE": "shared", "TESTS": ["test_1"]}) == "shared"


def test_validate_tests_per_instance_raises_on_an_unknown_value():
    with pytest.raises(OasisAlpacaConfigError, match="must be one of separate, shared"):
        validate_tests_per_instance({"TESTS_PER_INSTANCE": "together", "TESTS": ["test_1"]})


def test_validate_tests_per_instance_raises_on_shared_without_tests():
    with pytest.raises(OasisAlpacaConfigError, match="needs TESTS"):
        validate_tests_per_instance({"TESTS_PER_INSTANCE": "shared", "PATH_TO_OASISLMF_JSON": "./oasislmf.json"})
