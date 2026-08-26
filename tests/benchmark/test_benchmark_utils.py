from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK
from alpaca.inputs import (
    REPO_LOCATION, REPO_LOCATIONS, OASISLMF_VERSION, OASISLMF_VERSIONS, BENCHMARK_BUCKET, PUBLISH_BASELINE,
    OASISLMF_BRANCH, OASISLMF_BRANCHES
)


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
    for key in (REPO_LOCATIONS, OASISLMF_VERSIONS, OASISLMF_BRANCHES):
        assert isinstance(key[2], list)


def test_required_and_optional_config_benchmark_do_not_overlap():
    """Test that no config key is listed as both required and optional."""
    required_keys = {key for key, _, _ in REQUIRED_CONFIG_BENCHMARK}
    optional_keys = {key for key, _, _ in OPTIONAL_CONFIG_BENCHMARK}
    assert required_keys.isdisjoint(optional_keys)
