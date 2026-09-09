from alpaca.benchmark.scripts import (
    LIVE_SOURCE, STORED_SOURCE, benchmark_locations, build_benchmark_plan, build_benchmark_targets,
    format_benchmark_plan, model_name_from_location, oasislmf_sources, resolve_execution_mode
)
from alpaca.exceptions import OasisAlpacaConfigError

import pytest


PIWIND = "https://github.com/OasisLMF/OasisPiWind"
LEAGUE = "https://github.com/OasisLMF/OasisLeague"


def test_model_name_from_location_strips_oasis_prefix_for_github():
    assert model_name_from_location(PIWIND) == "PiWind"


def test_model_name_from_location_keeps_non_oasis_github_repo_name():
    assert model_name_from_location("https://github.com/someorg/mymodel") == "mymodel"


def test_model_name_from_location_uses_last_segment_for_s3():
    assert model_name_from_location("s3://bucket/path/to/model") == "model"


def test_model_name_from_location_strips_trailing_slash_for_s3():
    assert model_name_from_location("s3://bucket/path/to/model/") == "model"


def test_benchmark_locations_dedupes_repeated_locations():
    """Listing the same model twice shouldn't run it twice."""
    assert benchmark_locations({"REPO_LOCATIONS": [PIWIND, PIWIND, LEAGUE]}) == [PIWIND, LEAGUE]


def test_benchmark_locations_allows_a_single_location():
    assert benchmark_locations({"REPO_LOCATIONS": [PIWIND]}) == [PIWIND]


def test_benchmark_locations_returns_empty_when_unset():
    assert benchmark_locations({}) == []


def test_benchmark_locations_returns_empty_for_an_empty_list():
    assert benchmark_locations({"REPO_LOCATIONS": []}) == []


def test_benchmark_locations_ignores_blank_entries():
    assert benchmark_locations({"REPO_LOCATIONS": ["", PIWIND]}) == [PIWIND]


def test_oasislmf_sources_lists_versions_then_branches():
    sources = oasislmf_sources({"OASISLMF_VERSIONS": ["2.5.6", "2.4.9"], "OASISLMF_BRANCHES": ["stable/2.5.x"]})

    assert sources == [(None, "2.5.6"), (None, "2.4.9"), ("stable/2.5.x", None)]


def test_oasislmf_sources_dedupes_repeated_entries():
    assert oasislmf_sources({"OASISLMF_VERSIONS": ["2.5.6", "2.5.6"]}) == [(None, "2.5.6")]


def test_oasislmf_sources_allows_a_single_version():
    """One entry is a valid benchmark: it still gets timed, and can be diffed against a
    stored baseline.
    """
    assert oasislmf_sources({"OASISLMF_VERSIONS": ["2.5.6"]}) == [(None, "2.5.6")]


def test_oasislmf_sources_allows_a_single_branch():
    assert oasislmf_sources({"OASISLMF_BRANCHES": ["stable/2.5.x"]}) == [("stable/2.5.x", None)]


def test_oasislmf_sources_allows_versions_with_no_branches():
    """Either key on its own is enough; the other can be absent or an empty list."""
    assert oasislmf_sources({"OASISLMF_VERSIONS": ["2.5.6"], "OASISLMF_BRANCHES": []}) == [(None, "2.5.6")]


def test_oasislmf_sources_allows_branches_with_no_versions():
    assert oasislmf_sources({"OASISLMF_VERSIONS": [], "OASISLMF_BRANCHES": ["main"]}) == [("main", None)]


def test_oasislmf_sources_raises_when_nothing_is_pinned():
    """Nothing to install is a config error, not a quiet run against whatever PyPI's latest
    release happens to be that day.
    """
    with pytest.raises(OasisAlpacaConfigError):
        oasislmf_sources({})


def test_oasislmf_sources_raises_when_both_lists_are_empty():
    with pytest.raises(OasisAlpacaConfigError):
        oasislmf_sources({"OASISLMF_VERSIONS": [], "OASISLMF_BRANCHES": []})


def test_oasislmf_sources_ignores_blank_entries():
    """A blank entry would otherwise become a target with no version to install."""
    assert oasislmf_sources({"OASISLMF_VERSIONS": ["", "2.5.6"], "OASISLMF_BRANCHES": [""]}) == [(None, "2.5.6")]


def test_oasislmf_sources_raises_when_every_entry_is_blank():
    with pytest.raises(OasisAlpacaConfigError):
        oasislmf_sources({"OASISLMF_VERSIONS": [""]})


def test_resolve_execution_mode_defaults_to_parallel():
    assert resolve_execution_mode({}) == "parallel"


def test_resolve_execution_mode_reads_configured_mode():
    assert resolve_execution_mode({"EXECUTION_MODE": "sequential"}) == "sequential"


def test_resolve_execution_mode_raises_on_invalid_mode():
    with pytest.raises(OasisAlpacaConfigError):
        resolve_execution_mode({"EXECUTION_MODE": "sideways"})


BASE_BENCHMARK_CONFIG = {
    "AMI_ID": "ami-1",
    "SECURITY_GROUP_ID": "sg-1",
    "SUBNET_ID": "subnet-1",
    "IAM_INSTANCE_PROFILE": "profile",
    "PATH_TO_OASISLMF_JSON": "./oasislmf.json",
    "REPO_LOCATIONS": [PIWIND],
    "OASISLMF_VERSIONS": ["2.3.3", "2.4.9"],
}


def test_build_benchmark_targets_returns_one_target_per_version():
    targets = build_benchmark_targets(BASE_BENCHMARK_CONFIG)

    assert [target["version"] for target in targets] == ["2.3.3", "2.4.9"]
    assert [target["model"] for target in targets] == ["PiWind", "PiWind"]
    assert [target["source"] for target in targets] == [LIVE_SOURCE, LIVE_SOURCE]


def test_build_benchmark_targets_crosses_every_location_with_every_version():
    """Two locations and two versions benchmark all four combinations, location by location."""
    config = {**BASE_BENCHMARK_CONFIG, "REPO_LOCATIONS": [PIWIND, LEAGUE]}
    targets = build_benchmark_targets(config)

    assert [(target["model"], target["version"]) for target in targets] == [
        ("PiWind", "2.3.3"), ("PiWind", "2.4.9"), ("League", "2.3.3"), ("League", "2.4.9"),
    ]


def test_build_benchmark_targets_sets_distinct_version_per_target():
    targets = build_benchmark_targets(BASE_BENCHMARK_CONFIG)

    assert [target["run_config"]["OASISLMF_VERSION"] for target in targets] == ["2.3.3", "2.4.9"]


def test_build_benchmark_targets_gives_each_target_its_own_location():
    config = {**BASE_BENCHMARK_CONFIG, "REPO_LOCATIONS": [PIWIND, LEAGUE], "OASISLMF_VERSIONS": ["2.4.9"]}
    targets = build_benchmark_targets(config)

    assert [target["run_config"]["REPO_LOCATION"] for target in targets] == [PIWIND, LEAGUE]


def test_build_benchmark_targets_carries_over_shared_keys():
    targets = build_benchmark_targets(BASE_BENCHMARK_CONFIG)

    for target in targets:
        run_config = target["run_config"]
        assert run_config["AMI_ID"] == "ami-1"
        assert run_config["SECURITY_GROUP_ID"] == "sg-1"
        assert run_config["SUBNET_ID"] == "subnet-1"
        assert run_config["IAM_INSTANCE_PROFILE"] == "profile"
        assert run_config["PATH_TO_OASISLMF_JSON"] == "./oasislmf.json"


def test_build_benchmark_targets_uses_separate_result_directories():
    targets = build_benchmark_targets(BASE_BENCHMARK_CONFIG)

    directories = [target["run_config"]["RESULT_DIRECTORY"] for target in targets]
    assert directories == ["./runs/PiWind-2.3.3", "./runs/PiWind-2.4.9"]


def test_build_benchmark_targets_respects_configured_result_directory():
    config = {**BASE_BENCHMARK_CONFIG, "RESULT_DIRECTORY": "/local/results"}
    targets = build_benchmark_targets(config)

    assert targets[0]["run_config"]["RESULT_DIRECTORY"] == "/local/results/PiWind-2.3.3"


def test_build_benchmark_targets_rejects_an_s3_result_directory():
    """A benchmark reads its timings and outputs back off disk, so results must land locally."""
    config = {**BASE_BENCHMARK_CONFIG, "RESULT_DIRECTORY": "s3://bucket/results"}

    with pytest.raises(OasisAlpacaConfigError):
        build_benchmark_targets(config)


def test_build_benchmark_targets_makes_result_directories_path_safe():
    """A branch name carries slashes, which can't go straight into a directory name."""
    config = {**BASE_BENCHMARK_CONFIG, "OASISLMF_VERSIONS": [], "OASISLMF_BRANCHES": ["stable/2.4.x"]}
    targets = build_benchmark_targets(config)

    assert targets[0]["run_config"]["RESULT_DIRECTORY"] == "./runs/PiWind-branch-stable-2.4.x"


def test_build_benchmark_targets_disambiguates_shared_result_directories():
    """Two locations can share a model name, and must still not share an output directory."""
    config = {**BASE_BENCHMARK_CONFIG, "REPO_LOCATIONS": [PIWIND, "s3://bucket/PiWind"], "OASISLMF_VERSIONS": ["2.4.9"]}
    targets = build_benchmark_targets(config)

    directories = [target["run_config"]["RESULT_DIRECTORY"] for target in targets]
    assert directories == ["./runs/PiWind-2.4.9", "./runs/PiWind-2.4.9-2"]


def test_build_benchmark_targets_sets_a_branch_per_target():
    config = {
        **BASE_BENCHMARK_CONFIG,
        "OASISLMF_VERSIONS": [],
        "OASISLMF_BRANCHES": ["stable/2.3.x", "stable/2.4.x"],
    }
    targets = build_benchmark_targets(config)

    assert [target["run_config"]["OASISLMF_BRANCH"] for target in targets] == ["stable/2.3.x", "stable/2.4.x"]
    assert [target["version"] for target in targets] == ["branch:stable/2.3.x", "branch:stable/2.4.x"]


def test_build_benchmark_targets_branch_omits_version_from_run_config():
    """Test that a branch-driven target doesn't also carry a version, since the branch
    already takes priority at install time and a leftover version would be misleading.
    """
    config = {**BASE_BENCHMARK_CONFIG, "OASISLMF_VERSIONS": [], "OASISLMF_BRANCHES": ["stable/2.3.x"]}
    targets = build_benchmark_targets(config)

    assert "OASISLMF_VERSION" not in targets[0]["run_config"]
    assert targets[0]["run_config"]["OASISLMF_BRANCH"] == "stable/2.3.x"


def test_build_benchmark_targets_benchmarks_versions_and_branches_together():
    config = {**BASE_BENCHMARK_CONFIG, "OASISLMF_VERSIONS": ["2.4.9"], "OASISLMF_BRANCHES": ["my-feature"]}
    targets = build_benchmark_targets(config)

    assert [target["version"] for target in targets] == ["2.4.9", "branch:my-feature"]
    assert "OASISLMF_BRANCH" not in targets[0]["run_config"]
    assert "OASISLMF_VERSION" not in targets[1]["run_config"]


def test_build_benchmark_targets_names_ec2_instances_by_model_and_version():
    """Test that each target's EC2_NAME identifies its model and version, so concurrent
    instances are distinguishable in the AWS console.
    """
    targets = build_benchmark_targets(BASE_BENCHMARK_CONFIG)

    assert [target["run_config"]["EC2_NAME"] for target in targets] == ["Alpaca PiWind 2.3.3", "Alpaca PiWind 2.4.9"]


def test_build_benchmark_targets_ec2_name_overrides_top_level_setting():
    """Test that the derived per-target EC2_NAME takes priority over a top-level EC2_NAME,
    since a single shared name would defeat the point of distinguishing concurrent instances.
    """
    config = {**BASE_BENCHMARK_CONFIG, "EC2_NAME": "MyCustomName"}
    targets = build_benchmark_targets(config)

    for target in targets:
        assert target["run_config"]["EC2_NAME"] != "MyCustomName"


def test_build_benchmark_targets_builds_one_target_for_one_version():
    config = {**BASE_BENCHMARK_CONFIG, "OASISLMF_VERSIONS": ["2.5.6"]}
    targets = build_benchmark_targets(config)

    assert len(targets) == 1
    assert targets[0]["version"] == "2.5.6"
    assert targets[0]["source_label"] == "OasisLMF 2.5.6"
    assert targets[0]["run_config"]["EC2_NAME"] == "Alpaca PiWind 2.5.6"
    assert targets[0]["run_config"]["OASISLMF_VERSION"] == "2.5.6"


def test_build_benchmark_targets_raises_when_nothing_is_pinned():
    config = {key: value for key, value in BASE_BENCHMARK_CONFIG.items() if key != "OASISLMF_VERSIONS"}

    with pytest.raises(OasisAlpacaConfigError):
        build_benchmark_targets(config)


def test_build_benchmark_targets_names_ec2_instances_by_branch():
    config = {**BASE_BENCHMARK_CONFIG, "OASISLMF_VERSIONS": [], "OASISLMF_BRANCHES": ["stable/2.4.x"]}
    targets = build_benchmark_targets(config)

    assert targets[0]["run_config"]["EC2_NAME"] == "Alpaca PiWind branch:stable/2.4.x"
    assert targets[0]["source_label"] == "OasisLMF branch:stable/2.4.x"


def test_build_benchmark_targets_strips_a_trailing_result_directory_slash():
    config = {**BASE_BENCHMARK_CONFIG, "OASISLMF_VERSIONS": ["2.4.9"], "RESULT_DIRECTORY": "./runs/"}
    targets = build_benchmark_targets(config)

    assert targets[0]["run_config"]["RESULT_DIRECTORY"] == "./runs/PiWind-2.4.9"


def test_build_benchmark_targets_disambiguates_three_way_result_directory_clashes():
    config = {
        **BASE_BENCHMARK_CONFIG,
        "REPO_LOCATIONS": [PIWIND, "s3://bucket/PiWind", "s3://other-bucket/PiWind"],
        "OASISLMF_VERSIONS": ["2.4.9"],
    }
    targets = build_benchmark_targets(config)

    assert [target["label"] for target in targets] == ["PiWind-2.4.9", "PiWind-2.4.9-2", "PiWind-2.4.9-3"]


def test_build_benchmark_targets_marks_stored_versions():
    """A version already in the bucket is taken from there rather than run again."""
    targets = build_benchmark_targets(BASE_BENCHMARK_CONFIG, stored_versions={"2.4.9"})

    assert [target["source"] for target in targets] == [LIVE_SOURCE, STORED_SOURCE]


def test_build_benchmark_targets_never_marks_a_branch_as_stored():
    """Baselines are stored per version, so a branch target always runs."""
    config = {**BASE_BENCHMARK_CONFIG, "OASISLMF_VERSIONS": [], "OASISLMF_BRANCHES": ["stable/2.4.x"]}
    targets = build_benchmark_targets(config, stored_versions={"stable/2.4.x"})

    assert targets[0]["source"] == LIVE_SOURCE


def test_build_benchmark_targets_ignores_stored_versions_it_is_not_running():
    targets = build_benchmark_targets(BASE_BENCHMARK_CONFIG, stored_versions={"9.9.9"})

    assert [target["source"] for target in targets] == [LIVE_SOURCE, LIVE_SOURCE]


def test_build_benchmark_targets_marks_a_stored_version_at_every_location():
    """A location axis doesn't change which versions are already stored."""
    config = {**BASE_BENCHMARK_CONFIG, "REPO_LOCATIONS": [PIWIND, LEAGUE]}
    targets = build_benchmark_targets(config, stored_versions={"2.4.9"})

    assert [target["source"] for target in targets] == [LIVE_SOURCE, STORED_SOURCE, LIVE_SOURCE, STORED_SOURCE]


def test_build_benchmark_targets_raises_without_any_location():
    """An empty REPO_LOCATIONS has nothing to benchmark, and shouldn't read as a valid run."""
    with pytest.raises(OasisAlpacaConfigError):
        build_benchmark_targets({**BASE_BENCHMARK_CONFIG, "REPO_LOCATIONS": []})


def test_build_benchmark_targets_switches_debug_off_when_parallel():
    """Concurrent targets would all prompt for input at once, so debug mode can't apply."""
    config = {**BASE_BENCHMARK_CONFIG, "DEBUG": True, "EXECUTION_MODE": "parallel"}

    targets = build_benchmark_targets(config)

    assert [target["run_config"]["DEBUG"] for target in targets] == [False, False]
    assert config["DEBUG"] is False


def test_build_benchmark_targets_keeps_debug_when_sequential():
    """Sequential targets run one at a time, so there is a single prompt to answer."""
    config = {**BASE_BENCHMARK_CONFIG, "DEBUG": True, "EXECUTION_MODE": "sequential"}

    targets = build_benchmark_targets(config)

    assert all(target["run_config"]["DEBUG"] is True for target in targets)


def test_build_benchmark_plan_lists_each_model_once_and_every_target():
    config = {**BASE_BENCHMARK_CONFIG, "REPO_LOCATIONS": [PIWIND, PIWIND]}
    plan = build_benchmark_plan(config, build_benchmark_targets(config))

    assert plan["models"] == ["PiWind"]
    assert plan["targets"] == ["PiWind: OasisLMF 2.3.3", "PiWind: OasisLMF 2.4.9"]
    assert plan["execution_mode"] == "parallel"


def test_build_benchmark_plan_lists_both_models_when_different():
    config = {**BASE_BENCHMARK_CONFIG, "REPO_LOCATIONS": [PIWIND, LEAGUE], "OASISLMF_VERSIONS": ["2.4.9"]}
    plan = build_benchmark_plan(config, build_benchmark_targets(config))

    assert plan["models"] == ["PiWind", "League"]


def test_build_benchmark_plan_labels_branch_targets():
    config = {**BASE_BENCHMARK_CONFIG, "OASISLMF_VERSIONS": [], "OASISLMF_BRANCHES": ["my-feature-branch"]}
    plan = build_benchmark_plan(config, build_benchmark_targets(config))

    assert plan["targets"] == ["PiWind: OasisLMF branch:my-feature-branch"]


def test_build_benchmark_plan_labels_stored_targets_distinctly():
    """A target read from the bucket isn't a live run, and shouldn't read like one."""
    targets = build_benchmark_targets(BASE_BENCHMARK_CONFIG, stored_versions={"2.4.9"})
    plan = build_benchmark_plan(BASE_BENCHMARK_CONFIG, targets)

    assert plan["targets"] == ["PiWind: OasisLMF 2.3.3", "PiWind: OasisLMF 2.4.9 (S3 baseline)"]


def test_build_benchmark_plan_respects_configured_execution_mode():
    config = {**BASE_BENCHMARK_CONFIG, "EXECUTION_MODE": "sequential"}
    plan = build_benchmark_plan(config, build_benchmark_targets(config))

    assert plan["execution_mode"] == "sequential"


def test_build_benchmark_plan_raises_on_invalid_execution_mode():
    config = {**BASE_BENCHMARK_CONFIG, "EXECUTION_MODE": "sideways"}

    with pytest.raises(OasisAlpacaConfigError):
        build_benchmark_plan(config, build_benchmark_targets(config))


def test_format_benchmark_plan_matches_documented_layout():
    plan = {
        "models": ["PiWind"],
        "targets": ["PiWind: OasisLMF 2.4.9", "PiWind: OasisLMF 2.3.3"],
        "execution_mode": "parallel",
    }
    assert format_benchmark_plan(plan) == (
        "Benchmark configuration loaded\n"
        "\n"
        "Models:\n"
        "- PiWind\n"
        "\n"
        "Targets:\n"
        "- PiWind: OasisLMF 2.4.9\n"
        "- PiWind: OasisLMF 2.3.3\n"
        "\n"
        "Execution mode:\n"
        "parallel"
    )


def test_model_name_from_location_keeps_a_repo_named_only_oasis():
    """Stripping the 'Oasis' prefix must not leave a model with no name at all."""
    assert model_name_from_location("https://github.com/OasisLMF/Oasis") == "Oasis"


def test_model_name_from_location_falls_back_to_the_location_itself():
    """A location that's neither S3 nor GitHub has no repo name to derive, so it names
    itself rather than coming out blank in the report.
    """
    assert model_name_from_location("/mnt/models/mymodel") == "/mnt/models/mymodel"
