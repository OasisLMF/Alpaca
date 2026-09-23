from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK, validate_test_suite_config
from alpaca.exceptions import OasisAlpacaConfigError
from alpaca.inputs import (
    REPO_LOCATION, REPO_LOCATIONS, OASISLMF_VERSION, OASISLMF_VERSIONS, BENCHMARK_BUCKET, PUBLISH_BASELINE,
    OASISLMF_BRANCH, OASISLMF_BRANCHES, PATH_TO_OASISLMF_JSON, RUN_TEST_SUITE
)

import pytest


def test_required_config_benchmark_requires_the_model_locations():
    """Test that a benchmark is configured with a list of locations rather than the single
    REPO_LOCATION the other run modes take.
    """
    assert REPO_LOCATIONS in REQUIRED_CONFIG_BENCHMARK
    assert REPO_LOCATION not in REQUIRED_CONFIG_BENCHMARK
    assert REPO_LOCATION not in OPTIONAL_CONFIG_BENCHMARK


def test_path_to_oasislmf_json_is_optional_not_required():
    """A RUN_TEST_SUITE target never uses PATH_TO_OASISLMF_JSON, so it can't be required at
    the schema level — validate_test_suite_config enforces it conditionally instead.
    """
    assert PATH_TO_OASISLMF_JSON in OPTIONAL_CONFIG_BENCHMARK
    assert PATH_TO_OASISLMF_JSON not in REQUIRED_CONFIG_BENCHMARK


def test_optional_config_benchmark_includes_run_test_suite():
    assert RUN_TEST_SUITE in OPTIONAL_CONFIG_BENCHMARK


def test_validate_test_suite_config_passes_with_path_to_oasislmf_json():
    validate_test_suite_config({"PATH_TO_OASISLMF_JSON": "./oasislmf.json"})


def test_validate_test_suite_config_raises_without_path_to_oasislmf_json_or_run_test_suite():
    """An ordinary target with neither key has no model config to run at all."""
    with pytest.raises(OasisAlpacaConfigError):
        validate_test_suite_config({})


def test_validate_test_suite_config_allows_missing_path_to_oasislmf_json_when_suite_mode():
    validate_test_suite_config({"RUN_TEST_SUITE": True})


def test_validate_test_suite_config_ignores_run_test_suite_set_false():
    with pytest.raises(OasisAlpacaConfigError):
        validate_test_suite_config({"RUN_TEST_SUITE": False})


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
    for key in (REPO_LOCATIONS, OASISLMF_VERSIONS, OASISLMF_BRANCHES):
        assert isinstance(key[2], list)


def test_required_and_optional_config_benchmark_do_not_overlap():
    """Test that no config key is listed as both required and optional."""
    required_keys = {key for key, _, _ in REQUIRED_CONFIG_BENCHMARK}
    optional_keys = {key for key, _, _ in OPTIONAL_CONFIG_BENCHMARK}
    assert required_keys.isdisjoint(optional_keys)
