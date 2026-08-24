from alpaca.benchmark.scripts import (
    model_name_from_location, build_benchmark_plan, build_execution_plan, build_model_run_configs, format_benchmark_plan
)
from alpaca.exceptions import OasisAlpacaConfigError

import logging
import pytest


def test_model_name_from_location_strips_oasis_prefix_for_github():
    assert model_name_from_location("https://github.com/OasisLMF/OasisPiWind") == "PiWind"


def test_model_name_from_location_keeps_non_oasis_github_repo_name():
    assert model_name_from_location("https://github.com/someorg/mymodel") == "mymodel"


def test_model_name_from_location_uses_last_segment_for_s3():
    assert model_name_from_location("s3://bucket/path/to/model") == "model"


def test_model_name_from_location_strips_trailing_slash_for_s3():
    assert model_name_from_location("s3://bucket/path/to/model/") == "model"


def test_build_benchmark_plan_dedupes_identical_models():
    config = {
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "OASISLMF_VERSION": "2.4.9",
        "OASISLMF_VERSION_COMPARISON": "2.3.3",
    }
    plan = build_benchmark_plan(config)
    assert plan["models"] == ["PiWind"]
    assert plan["comparisons"] == ["OasisLMF 2.4.9", "OasisLMF 2.3.3"]
    assert plan["execution_mode"] == "parallel"


def test_build_benchmark_plan_single_run_mode_omits_comparison_model():
    """Test that a config without REPO_LOCATION_COMPARISON only lists the one model."""
    config = {"REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind", "OASISLMF_VERSION": "2.5.6"}
    plan = build_benchmark_plan(config)
    assert plan["models"] == ["PiWind"]
    assert plan["comparisons"] == ["OasisLMF 2.5.6"]


def test_build_benchmark_plan_single_run_mode_labels_s3_baseline():
    """Test that an S3-sourced comparison version is labelled distinctly from a live one."""
    config = {
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "OASISLMF_VERSION": "2.5.6",
        "OASISLMF_VERSION_COMPARISON": "2.5.4",
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
    }
    plan = build_benchmark_plan(config)
    assert plan["comparisons"] == ["OasisLMF 2.5.6", "OasisLMF 2.5.4 (S3 baseline)"]


def test_build_benchmark_plan_labels_single_run_mode_branch():
    """Test that OASISLMF_BRANCH is reflected in the plan instead of misleadingly
    falling back to 'OasisLMF latest' when no OASISLMF_VERSION is set.
    """
    config = {"REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind", "OASISLMF_BRANCH": "my-feature-branch"}
    plan = build_benchmark_plan(config)
    assert plan["comparisons"] == ["OasisLMF branch:my-feature-branch"]


def test_build_benchmark_plan_scopes_branch_independently_per_target():
    """Test that OASISLMF_BRANCH only labels the baseline target, and does not leak onto
    the comparison target when OASISLMF_BRANCH_COMPARISON isn't also set.
    """
    config = {
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "OASISLMF_BRANCH": "my-feature-branch",
        "OASISLMF_VERSION_COMPARISON": "2.4.9",
    }
    plan = build_benchmark_plan(config)
    assert plan["comparisons"] == ["OasisLMF branch:my-feature-branch", "OasisLMF 2.4.9"]


def test_build_benchmark_plan_labels_both_branches_when_both_set():
    """Test that two different branches can be benchmarked against each other in one
    dual-target run, each shown with its own label.
    """
    config = {
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "OASISLMF_BRANCH": "stable/2.3.x",
        "OASISLMF_BRANCH_COMPARISON": "stable/2.4.x",
    }
    plan = build_benchmark_plan(config)
    assert plan["comparisons"] == ["OasisLMF branch:stable/2.3.x", "OasisLMF branch:stable/2.4.x"]


def test_build_benchmark_plan_warns_when_branch_comparison_set_in_single_run_mode(caplog):
    """Test that OASISLMF_BRANCH_COMPARISON is a no-op (with a warning) in single-run
    mode, since there's no second live target for it to apply to.
    """
    config = {"REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind", "OASISLMF_BRANCH_COMPARISON": "stable/2.4.x"}
    with caplog.at_level(logging.WARNING, logger="alpaca.benchmark.scripts"):
        plan = build_benchmark_plan(config)
    assert plan["comparisons"] == ["OasisLMF latest"]
    assert "only applies in dual-target mode" in caplog.text


def test_build_benchmark_plan_lists_both_models_when_different():
    config = {
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisLeague",
    }
    plan = build_benchmark_plan(config)
    assert plan["models"] == ["PiWind", "League"]


def test_build_benchmark_plan_defaults_missing_versions_to_latest():
    config = {
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
    }
    plan = build_benchmark_plan(config)
    assert plan["comparisons"] == ["OasisLMF latest", "OasisLMF latest"]


def test_build_benchmark_plan_respects_configured_execution_mode():
    config = {
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "EXECUTION_MODE": "sequential",
    }
    plan = build_benchmark_plan(config)
    assert plan["execution_mode"] == "sequential"


def test_build_benchmark_plan_raises_on_invalid_execution_mode():
    config = {
        "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "EXECUTION_MODE": "sideways",
    }
    with pytest.raises(OasisAlpacaConfigError):
        build_benchmark_plan(config)


def test_build_execution_plan_matches_documented_shape():
    config = {"OASISLMF_VERSION": "2.3.3", "OASISLMF_VERSION_COMPARISON": "2.4.9"}
    assert build_execution_plan(config) == {
        "baseline": {"version": "2.3.3"},
        "comparison": {"version": "2.4.9"},
    }


def test_build_execution_plan_defaults_missing_versions_to_latest():
    assert build_execution_plan({}) == {
        "baseline": {"version": "latest"},
        "comparison": {"version": "latest"},
    }


BASE_BENCHMARK_CONFIG = {
    "AMI_ID": "ami-1",
    "SECURITY_GROUP_ID": "sg-1",
    "SUBNET_ID": "subnet-1",
    "IAM_INSTANCE_PROFILE": "profile",
    "PATH_TO_OASISLMF_JSON": "./oasislmf.json",
    "REPO_LOCATION": "https://github.com/OasisLMF/OasisPiWind",
    "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
    "OASISLMF_VERSION": "2.3.3",
    "OASISLMF_VERSION_COMPARISON": "2.4.9",
}


def test_build_model_run_configs_returns_baseline_then_comparison():
    run_configs = build_model_run_configs(BASE_BENCHMARK_CONFIG)

    assert [entry["label"] for entry in run_configs] == ["baseline", "comparison"]
    assert [entry["model"] for entry in run_configs] == ["PiWind", "PiWind"]
    assert [entry["version"] for entry in run_configs] == ["2.3.3", "2.4.9"]


def test_build_model_run_configs_sets_distinct_version_per_target():
    run_configs = build_model_run_configs(BASE_BENCHMARK_CONFIG)

    baseline, comparison = run_configs
    assert baseline["run_config"]["OASISLMF_VERSION"] == "2.3.3"
    assert comparison["run_config"]["OASISLMF_VERSION"] == "2.4.9"


def test_build_model_run_configs_carries_over_shared_keys():
    run_configs = build_model_run_configs(BASE_BENCHMARK_CONFIG)

    for entry in run_configs:
        run_config = entry["run_config"]
        assert run_config["AMI_ID"] == "ami-1"
        assert run_config["SECURITY_GROUP_ID"] == "sg-1"
        assert run_config["SUBNET_ID"] == "subnet-1"
        assert run_config["IAM_INSTANCE_PROFILE"] == "profile"
        assert run_config["PATH_TO_OASISLMF_JSON"] == "./oasislmf.json"


def test_build_model_run_configs_uses_separate_result_directories():
    run_configs = build_model_run_configs(BASE_BENCHMARK_CONFIG)

    baseline, comparison = run_configs
    assert baseline["run_config"]["RESULT_DIRECTORY"] == "./runs/baseline"
    assert comparison["run_config"]["RESULT_DIRECTORY"] == "./runs/comparison"
    assert baseline["run_config"]["RESULT_DIRECTORY"] != comparison["run_config"]["RESULT_DIRECTORY"]


def test_build_model_run_configs_sets_independent_branch_per_target():
    """Test that OASISLMF_BRANCH and OASISLMF_BRANCH_COMPARISON install different
    branches on their own target, with no fallback to one another.
    """
    config = {
        **BASE_BENCHMARK_CONFIG,
        "OASISLMF_BRANCH": "stable/2.3.x",
        "OASISLMF_BRANCH_COMPARISON": "stable/2.4.x",
    }
    run_configs = build_model_run_configs(config)

    baseline, comparison = run_configs
    assert baseline["run_config"]["OASISLMF_BRANCH"] == "stable/2.3.x"
    assert comparison["run_config"]["OASISLMF_BRANCH"] == "stable/2.4.x"
    assert baseline["version"] == "branch:stable/2.3.x"
    assert comparison["version"] == "branch:stable/2.4.x"


def test_build_model_run_configs_branch_omits_version_from_run_config():
    """Test that a branch-driven target doesn't also carry its OASISLMF_VERSION, since
    the branch already takes priority at install time and a leftover version would be
    misleading in the run_config.
    """
    config = {**BASE_BENCHMARK_CONFIG, "OASISLMF_BRANCH": "stable/2.3.x"}
    run_configs = build_model_run_configs(config)

    baseline = run_configs[0]
    assert "OASISLMF_VERSION" not in baseline["run_config"]
    assert baseline["run_config"]["OASISLMF_BRANCH"] == "stable/2.3.x"


def test_build_model_run_configs_comparison_target_unaffected_by_baseline_branch():
    """Test that OASISLMF_BRANCH set alone (no OASISLMF_BRANCH_COMPARISON) does not leak
    onto the comparison target - it keeps installing its own OASISLMF_VERSION_COMPARISON.
    """
    config = {**BASE_BENCHMARK_CONFIG, "OASISLMF_BRANCH": "stable/2.3.x"}
    run_configs = build_model_run_configs(config)

    comparison = run_configs[1]
    assert "OASISLMF_BRANCH" not in comparison["run_config"]
    assert comparison["run_config"]["OASISLMF_VERSION"] == "2.4.9"


def test_build_model_run_configs_names_ec2_instances_by_model_and_version():
    """Test that each target's EC2_NAME identifies its model and version, so concurrent
    instances are distinguishable in the AWS console.
    """
    run_configs = build_model_run_configs(BASE_BENCHMARK_CONFIG)

    baseline, comparison = run_configs
    assert baseline["run_config"]["EC2_NAME"] == "Alpaca PiWind 2.3.3"
    assert comparison["run_config"]["EC2_NAME"] == "Alpaca PiWind 2.4.9"


def test_build_model_run_configs_ec2_name_overrides_top_level_setting():
    """Test that the derived per-target EC2_NAME takes priority over a top-level
    EC2_NAME, since a single shared name would defeat the point of distinguishing
    concurrent instances.
    """
    config = {**BASE_BENCHMARK_CONFIG, "EC2_NAME": "MyCustomName"}
    run_configs = build_model_run_configs(config)

    for entry in run_configs:
        assert entry["run_config"]["EC2_NAME"] != "MyCustomName"


def test_build_model_run_configs_ec2_name_defaults_version_to_latest():
    config = {key: value for key, value in BASE_BENCHMARK_CONFIG.items() if not key.startswith("OASISLMF_VERSION")}
    run_configs = build_model_run_configs(config)

    baseline, comparison = run_configs
    assert baseline["run_config"]["EC2_NAME"] == "Alpaca PiWind latest"
    assert comparison["run_config"]["EC2_NAME"] == "Alpaca PiWind latest"


def test_build_model_run_configs_respects_configured_result_directory():
    config = {**BASE_BENCHMARK_CONFIG, "RESULT_DIRECTORY": "s3://bucket/results"}
    run_configs = build_model_run_configs(config)

    baseline, comparison = run_configs
    assert baseline["run_config"]["RESULT_DIRECTORY"] == "s3://bucket/results/baseline"
    assert comparison["run_config"]["RESULT_DIRECTORY"] == "s3://bucket/results/comparison"


def test_build_model_run_configs_omits_version_when_unset():
    config = {key: value for key, value in BASE_BENCHMARK_CONFIG.items() if not key.startswith("OASISLMF_VERSION")}
    run_configs = build_model_run_configs(config)

    baseline, comparison = run_configs
    assert "OASISLMF_VERSION" not in baseline["run_config"]
    assert "OASISLMF_VERSION" not in comparison["run_config"]
    assert baseline["version"] == "latest"
    assert comparison["version"] == "latest"


def test_build_model_run_configs_returns_single_target_without_comparison_repo():
    """Test that omitting REPO_LOCATION_COMPARISON produces a single-run-mode target."""
    config = {key: value for key, value in BASE_BENCHMARK_CONFIG.items() if not key.startswith("REPO_LOCATION_C")}
    run_configs = build_model_run_configs(config)

    assert [entry["label"] for entry in run_configs] == ["baseline"]
    assert run_configs[0]["run_config"]["RESULT_DIRECTORY"] == "./runs/baseline"


def test_format_benchmark_plan_matches_documented_layout():
    plan = {
        "models": ["PiWind"],
        "comparisons": ["OasisLMF 2.4.9", "OasisLMF 2.3.3"],
        "execution_mode": "parallel",
    }
    assert format_benchmark_plan(plan) == (
        "Benchmark configuration loaded\n"
        "\n"
        "Models:\n"
        "- PiWind\n"
        "\n"
        "Comparison:\n"
        "- OasisLMF 2.4.9\n"
        "- OasisLMF 2.3.3\n"
        "\n"
        "Execution mode:\n"
        "parallel"
    )
