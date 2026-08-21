from alpaca.benchmark.s3_baseline import validate_s3_baseline_config, upload_baseline, download_baseline
from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from moto import mock_aws
from pathlib import Path

import boto3
import logging
import pytest


REGION = "us-east-1"
CONFIG = {"AWS_REGION": REGION}


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
        validate_s3_baseline_config({"PUBLISH_BASELINE": "True", "OASISLMF_VERSION": "2.5.4"})


def test_validate_raises_when_publish_baseline_missing_version():
    with pytest.raises(OasisAlpacaConfigError):
        validate_s3_baseline_config({"PUBLISH_BASELINE": "True", "BENCHMARK_BUCKET": "s3://alpaca-benchmark"})


def test_validate_raises_when_comparison_version_missing_bucket_in_single_run_mode():
    with pytest.raises(OasisAlpacaConfigError):
        validate_s3_baseline_config({"OASISLMF_VERSION_COMPARISON": "2.5.4"})


def test_validate_passes_when_publish_baseline_fully_configured():
    validate_s3_baseline_config({
        "PUBLISH_BASELINE": "True", "BENCHMARK_BUCKET": "s3://alpaca-benchmark", "OASISLMF_VERSION": "2.5.4",
    })


def test_validate_passes_when_nothing_configured():
    validate_s3_baseline_config({})


def test_validate_warns_and_passes_when_s3_keys_set_in_dual_target_mode(caplog):
    config = {
        "REPO_LOCATION_COMPARISON": "https://github.com/OasisLMF/OasisPiWind",
        "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
    }
    with caplog.at_level(logging.WARNING, logger="alpaca.benchmark.s3_baseline"):
        validate_s3_baseline_config(config)

    assert "only apply in single-run mode" in caplog.text
