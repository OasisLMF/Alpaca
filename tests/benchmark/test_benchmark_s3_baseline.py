from alpaca.benchmark.s3_baseline import (
    download_baseline, resolve_stored_versions, upload_baseline, validate_s3_baseline_config
)
from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from moto import mock_aws

import boto3
import logging
import pytest


REGION = "us-east-1"
CONFIG = {"AWS_REGION": REGION}
PIWIND = "https://github.com/OasisLMF/OasisPiWind"


def _make_bucket(name="alpaca-benchmark"):
    boto3.client("s3", region_name=REGION).create_bucket(Bucket=name)
    return name


def _write_run_directory(tmp_path, files, result_text=None):
    output_dir = tmp_path / "losses-x" / "output"
    output_dir.mkdir(parents=True)
    for name, content in files.items():
        (output_dir / name).write_text(content)
    if result_text is not None:
        (tmp_path / "losses-x" / "result.txt").write_text(result_text)
    return tmp_path


@mock_aws
def test_upload_baseline_uploads_output_and_performance_files(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"}, result_text="COMPLETED: x in 1.0s\n")

    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)

    client = boto3.client("s3", region_name=REGION)
    assert client.get_object(Bucket=bucket, Key="2.5.4/output/summary.csv")["Body"].read() == b"a,b\n1,2\n"
    assert client.get_object(Bucket=bucket, Key="2.5.4/performance/result.txt")["Body"].read() == b"COMPLETED: x in 1.0s\n"


@mock_aws
def test_upload_baseline_skips_performance_upload_when_no_result_file(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})

    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)

    client = boto3.client("s3", region_name=REGION)
    with pytest.raises(client.exceptions.NoSuchKey):
        client.get_object(Bucket=bucket, Key="2.5.4/performance/result.txt")


@mock_aws
def test_upload_baseline_warns_when_overwriting_existing_baseline(tmp_path, caplog):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)

    with caplog.at_level(logging.WARNING, logger="alpaca.benchmark.s3_baseline"):
        upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)

    assert "Overwriting existing baseline" in caplog.text


@mock_aws
def test_upload_baseline_supports_bucket_prefix(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})

    upload_baseline(f"s3://{bucket}/some/prefix", "2.5.4", run_directory, CONFIG)

    client = boto3.client("s3", region_name=REGION)
    client.get_object(Bucket=bucket, Key="some/prefix/2.5.4/output/summary.csv")


@mock_aws
def test_download_baseline_downloads_output_and_performance_files(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path / "run", {"summary.csv": "a,b\n1,2\n"}, result_text="COMPLETED: x in 1.0s\n")
    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)

    local_directory = download_baseline(f"s3://{bucket}", "2.5.4", tmp_path / "downloaded", CONFIG)

    assert local_directory == tmp_path / "downloaded"
    assert (local_directory / "output" / "summary.csv").read_text() == "a,b\n1,2\n"
    assert (local_directory / "result.txt").read_text() == "COMPLETED: x in 1.0s\n"


@mock_aws
def test_download_baseline_warns_when_no_performance_data(tmp_path, caplog):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path / "run", {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)

    with caplog.at_level(logging.WARNING, logger="alpaca.benchmark.s3_baseline"):
        download_baseline(f"s3://{bucket}", "2.5.4", tmp_path / "downloaded", CONFIG)

    assert "No stored performance metrics found" in caplog.text
    assert not (tmp_path / "downloaded" / "result.txt").exists()


@mock_aws
def test_download_baseline_raises_when_no_stored_output(tmp_path):
    bucket = _make_bucket()

    with pytest.raises(OasisAlpacaError):
        download_baseline(f"s3://{bucket}", "9.9.9", tmp_path / "downloaded", CONFIG)


@mock_aws
def test_upload_then_download_baseline_round_trip_matches(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(
        tmp_path / "run", {"summary.csv": "a,b\n1,2\n", "other.csv": "x,y\n3,4\n"}, result_text="COMPLETED: x in 1.0s\n"
    )

    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)
    local_directory = download_baseline(f"s3://{bucket}", "2.5.4", tmp_path / "downloaded", CONFIG)

    assert {p.name for p in (local_directory / "output").iterdir()} == {"summary.csv", "other.csv"}


def test_validate_raises_when_publish_baseline_missing_bucket():
    with pytest.raises(OasisAlpacaConfigError):
        validate_s3_baseline_config({"PUBLISH_BASELINE": "True", "OASISLMF_VERSIONS": ["2.5.4"]})


def test_validate_raises_when_publish_baseline_has_no_versions_to_publish_under():
    """A branch target has no version for its baseline to be stored under."""
    with pytest.raises(OasisAlpacaConfigError):
        validate_s3_baseline_config({
            "PUBLISH_BASELINE": "True", "BENCHMARK_BUCKET": "s3://alpaca-benchmark", "OASISLMF_BRANCHES": ["main"],
        })


def test_validate_passes_when_publish_baseline_fully_configured():
    validate_s3_baseline_config({
        "PUBLISH_BASELINE": "True", "BENCHMARK_BUCKET": "s3://alpaca-benchmark", "OASISLMF_VERSIONS": ["2.5.4"],
    })


def test_validate_passes_when_nothing_configured():
    validate_s3_baseline_config({})


@mock_aws
def test_resolve_stored_versions_finds_only_the_stored_versions(tmp_path):
    """A version already in the bucket is reused; one that isn't has to be run."""
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)

    stored = resolve_stored_versions({
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND],
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
    })

    assert stored == {"2.5.4"}


@mock_aws
def test_resolve_stored_versions_supports_bucket_prefix(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}/some/prefix", "2.5.4", run_directory, CONFIG)

    stored = resolve_stored_versions({
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}/some/prefix", "REPO_LOCATIONS": [PIWIND],
        "OASISLMF_VERSIONS": ["2.5.4"],
    })

    assert stored == {"2.5.4"}


def test_resolve_stored_versions_returns_nothing_without_a_bucket():
    assert resolve_stored_versions({"OASISLMF_VERSIONS": ["2.5.4"], "REPO_LOCATIONS": [PIWIND]}) == set()


def test_resolve_stored_versions_returns_nothing_without_any_versions():
    """A branch-only benchmark has nothing that could be keyed to a stored baseline, so the
    bucket is never even queried.
    """
    config = {"BENCHMARK_BUCKET": "s3://alpaca-benchmark", "OASISLMF_BRANCHES": ["main"], "REPO_LOCATIONS": [PIWIND]}

    assert resolve_stored_versions(config) == set()


@mock_aws
def test_resolve_stored_versions_names_a_bucket_it_cannot_read():
    """A mistyped or unauthorised bucket should be corrected, not reported as a botocore error."""
    config = {**CONFIG, "BENCHMARK_BUCKET": "s3://not-a-real-bucket", "OASISLMF_VERSIONS": ["2.5.4"],
              "REPO_LOCATIONS": [PIWIND]}

    with pytest.raises(OasisAlpacaConfigError, match="not-a-real-bucket"):
        resolve_stored_versions(config)


@mock_aws
def test_resolve_stored_versions_returns_nothing_when_the_bucket_is_empty():
    bucket = _make_bucket()
    config = {
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND],
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
    }

    assert resolve_stored_versions(config) == set()


@mock_aws
def test_resolve_stored_versions_ignores_a_version_stored_without_output(tmp_path):
    """Performance metrics alone aren't a baseline: there'd be nothing to compare outputs
    against, so that version still has to run.
    """
    bucket = _make_bucket()
    boto3.client("s3", region_name=REGION).put_object(
        Bucket=bucket, Key="2.5.4/performance/result.txt", Body=b"COMPLETED: x in 1.0s\n"
    )
    config = {
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND], "OASISLMF_VERSIONS": ["2.5.4"],
    }

    assert resolve_stored_versions(config) == set()


@mock_aws
def test_resolve_stored_versions_skips_reuse_when_publishing(tmp_path, caplog):
    """Republishing a version means running it, not reusing what's already stored."""
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)
    config = {
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND],
        "OASISLMF_VERSIONS": ["2.5.4"], "PUBLISH_BASELINE": "True",
    }

    with caplog.at_level(logging.INFO, logger="alpaca.benchmark.s3_baseline"):
        assert resolve_stored_versions(config) == set()

    assert "PUBLISH_BASELINE is set" in caplog.text


@mock_aws
def test_resolve_stored_versions_skips_reuse_for_multiple_locations(tmp_path, caplog):
    """Baselines are keyed by version alone, so they can't stand in for a specific model."""
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)
    config = {
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "OASISLMF_VERSIONS": ["2.5.4"],
        "REPO_LOCATIONS": [PIWIND, "https://github.com/OasisLMF/OasisLeague"],
    }

    with caplog.at_level(logging.WARNING, logger="alpaca.benchmark.s3_baseline"):
        assert resolve_stored_versions(config) == set()

    assert "keyed by OasisLMF version only" in caplog.text


@mock_aws
def test_resolve_stored_versions_finds_several_stored_versions(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)
    upload_baseline(f"s3://{bucket}", "2.5.6", run_directory, CONFIG)

    stored = resolve_stored_versions({
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND],
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4", "2.4.9"],
    })

    assert stored == {"2.5.6", "2.5.4"}


@mock_aws
def test_download_baseline_skips_a_directory_marker_key(tmp_path):
    """A console-created folder shows up as a key ending in '/', which isn't a file."""
    bucket = _make_bucket()
    client = boto3.client("s3", region_name=REGION)
    client.put_object(Bucket=bucket, Key="2.5.4/output/", Body=b"")
    client.put_object(Bucket=bucket, Key="2.5.4/output/summary.csv", Body=b"a,b\n1,2\n")

    local_directory = download_baseline(f"s3://{bucket}", "2.5.4", tmp_path / "downloaded", CONFIG)

    assert [path.name for path in (local_directory / "output").iterdir()] == ["summary.csv"]


@mock_aws
def test_upload_baseline_skips_directories_inside_the_output_directory(tmp_path):
    """Only the output files themselves are published; a nested directory is not walked."""
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    (run_directory / "losses-x" / "output" / "nested").mkdir()

    upload_baseline(f"s3://{bucket}", "2.5.4", run_directory, CONFIG)

    listing = boto3.client("s3", region_name=REGION).list_objects_v2(Bucket=bucket, Prefix="2.5.4/output/")
    assert [obj["Key"] for obj in listing["Contents"]] == ["2.5.4/output/summary.csv"]
