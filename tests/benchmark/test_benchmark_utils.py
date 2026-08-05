from alpaca.benchmark.utils import REQUIRED_CONFIG_BENCHMARK, OPTIONAL_CONFIG_BENCHMARK
from alpaca.inputs import REPO_LOCATION, REPO_LOCATION_COMPARISON, OASISLMF_VERSION, OASISLMF_VERSION_COMPARISON


def test_required_config_benchmark_includes_both_repo_locations():
    """Test that both the primary and comparison repo locations are required."""
    assert REPO_LOCATION in REQUIRED_CONFIG_BENCHMARK
    assert REPO_LOCATION_COMPARISON in REQUIRED_CONFIG_BENCHMARK


def test_optional_config_benchmark_includes_both_oasislmf_versions():
    """Test that both the primary and comparison OasisLMF versions are optional."""
    assert OASISLMF_VERSION in OPTIONAL_CONFIG_BENCHMARK
    assert OASISLMF_VERSION_COMPARISON in OPTIONAL_CONFIG_BENCHMARK


def test_required_and_optional_config_benchmark_do_not_overlap():
    """Test that no config key is listed as both required and optional."""
    required_keys = {key for key, _, _ in REQUIRED_CONFIG_BENCHMARK}
    optional_keys = {key for key, _, _ in OPTIONAL_CONFIG_BENCHMARK}
    assert required_keys.isdisjoint(optional_keys)
