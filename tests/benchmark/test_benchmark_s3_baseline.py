from alpaca.benchmark.s3_baseline import (
    download_baseline, resolve_stored_versions, upload_baseline, validate_s3_baseline_config
)
from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from datetime import datetime, timezone
from moto import mock_aws
from unittest import mock

import boto3
import json
import logging
import pytest


REGION = "us-east-1"
CONFIG = {"AWS_REGION": REGION}
PIWIND = "https://github.com/OasisLMF/OasisPiWind"
LEAGUE = "https://github.com/OasisLMF/OasisLeague"


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

    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)

    client = boto3.client("s3", region_name=REGION)
    assert client.get_object(Bucket=bucket, Key="PiWind/2.5.4/output/summary.csv")["Body"].read() == b"a,b\n1,2\n"
    assert client.get_object(Bucket=bucket, Key="PiWind/2.5.4/performance/result.txt")["Body"].read() == b"COMPLETED: x in 1.0s\n"


@mock_aws
def test_upload_baseline_skips_performance_upload_when_no_result_file(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})

    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)

    client = boto3.client("s3", region_name=REGION)
    with pytest.raises(client.exceptions.NoSuchKey):
        client.get_object(Bucket=bucket, Key="PiWind/2.5.4/performance/result.txt")


def _keys(bucket, prefix=""):
    paginator = boto3.client("s3", region_name=REGION).get_paginator("list_objects_v2")
    return sorted(obj["Key"] for page in paginator.paginate(Bucket=bucket, Prefix=prefix) for obj in page.get("Contents", []))


def _publish_at(bucket, published_at, files, tmp_path, name, result_text=None, report_path=None):
    """Publish a PiWind 2.5.4 baseline as though it was published at published_at."""
    run_directory = _write_run_directory(tmp_path / name, files, result_text)
    with mock.patch("alpaca.benchmark.s3_baseline.datetime") as fake_datetime:
        fake_datetime.now.return_value = published_at
        fake_datetime.fromisoformat = datetime.fromisoformat
        upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG, report_path)


@mock_aws
def test_upload_baseline_moves_the_previous_baseline_into_its_history(tmp_path, caplog):
    bucket = _make_bucket()
    first = datetime(2026, 10, 6, 14, 12, 0, tzinfo=timezone.utc)
    _publish_at(bucket, first, {"summary.csv": "old\n"}, tmp_path, "first", result_text="COMPLETED: x in 1.0s\n")

    with caplog.at_level(logging.INFO, logger="alpaca.benchmark.s3_baseline"):
        _publish_at(bucket, datetime(2026, 10, 14, tzinfo=timezone.utc), {"summary.csv": "new\n"}, tmp_path, "second")

    client = boto3.client("s3", region_name=REGION)
    history = "PiWind/2.5.4/history/20261006-141200"
    assert client.get_object(Bucket=bucket, Key=f"{history}/output/summary.csv")["Body"].read() == b"old\n"
    assert client.get_object(Bucket=bucket, Key=f"{history}/performance/result.txt")["Body"].read() == b"COMPLETED: x in 1.0s\n"
    assert json.loads(client.get_object(Bucket=bucket, Key=f"{history}/published.json")["Body"].read())["published_at"] == (
        "2026-10-06T14:12:00+00:00"
    )
    assert client.get_object(Bucket=bucket, Key="PiWind/2.5.4/output/summary.csv")["Body"].read() == b"new\n"
    assert f"Moved the previous PiWind 2.5.4 baseline to s3://{bucket}/{history}" in caplog.text


@mock_aws
def test_upload_baseline_leaves_nothing_of_the_previous_baseline_behind(tmp_path):
    """A file the new run doesn't produce mustn't stay in the current baseline, mixed in with the new run's."""
    bucket = _make_bucket()
    _publish_at(
        bucket, datetime(2026, 10, 6, tzinfo=timezone.utc), {"summary.csv": "old\n", "extra.csv": "old\n"}, tmp_path,
        "first", result_text="COMPLETED: x in 1.0s\n",
    )

    _publish_at(bucket, datetime(2026, 10, 14, tzinfo=timezone.utc), {"summary.csv": "new\n"}, tmp_path, "second")

    current = [key for key in _keys(bucket, "PiWind/2.5.4/") if "/history/" not in key]
    assert current == ["PiWind/2.5.4/output/summary.csv", "PiWind/2.5.4/published.json"]


@mock_aws
def test_upload_baseline_keeps_every_earlier_baseline(tmp_path):
    bucket = _make_bucket()
    for day in (1, 2, 3):
        _publish_at(bucket, datetime(2026, 10, day, tzinfo=timezone.utc), {"summary.csv": f"{day}\n"}, tmp_path, f"run{day}")

    assert _keys(bucket, "PiWind/2.5.4/history/") == [
        "PiWind/2.5.4/history/20261001-000000/output/summary.csv",
        "PiWind/2.5.4/history/20261001-000000/published.json",
        "PiWind/2.5.4/history/20261002-000000/output/summary.csv",
        "PiWind/2.5.4/history/20261002-000000/published.json",
    ]


@mock_aws
def test_upload_baseline_names_a_baseline_published_before_published_json_by_when_it_was_written(tmp_path):
    bucket = _make_bucket()
    client = boto3.client("s3", region_name=REGION)
    client.put_object(Bucket=bucket, Key="PiWind/2.5.4/output/summary.csv", Body=b"old\n")
    written = client.head_object(Bucket=bucket, Key="PiWind/2.5.4/output/summary.csv")["LastModified"]

    _publish_at(bucket, datetime(2030, 1, 1, tzinfo=timezone.utc), {"summary.csv": "new\n"}, tmp_path, "second")

    stamp = written.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")
    assert _keys(bucket, "PiWind/2.5.4/history/") == [f"PiWind/2.5.4/history/{stamp}/output/summary.csv"]


@mock_aws
def test_upload_baseline_does_not_touch_the_stored_baseline_when_the_run_has_no_output(tmp_path):
    bucket = _make_bucket()
    _publish_at(bucket, datetime(2026, 10, 6, tzinfo=timezone.utc), {"summary.csv": "old\n"}, tmp_path, "first")

    with pytest.raises(OasisAlpacaError):
        upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", tmp_path / "empty", CONFIG)

    assert _keys(bucket) == ["PiWind/2.5.4/output/summary.csv", "PiWind/2.5.4/published.json"]


@mock_aws
def test_upload_baseline_keeps_the_previous_baseline_when_archiving_fails(tmp_path):
    bucket = _make_bucket()
    _publish_at(bucket, datetime(2026, 10, 6, tzinfo=timezone.utc), {"summary.csv": "old\n"}, tmp_path, "first")
    run_directory = _write_run_directory(tmp_path / "second", {"summary.csv": "new\n"})

    failing_client = mock.Mock(wraps=boto3.client("s3", region_name=REGION))
    failing_client.copy.side_effect = RuntimeError("copy failed")
    with mock.patch("alpaca.benchmark.s3_baseline._s3_client", return_value=failing_client):
        with pytest.raises(RuntimeError):
            upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)

    client = boto3.client("s3", region_name=REGION)
    assert client.get_object(Bucket=bucket, Key="PiWind/2.5.4/output/summary.csv")["Body"].read() == b"old\n"


@mock_aws
def test_upload_baseline_publishes_the_report_and_what_was_published(tmp_path):
    bucket = _make_bucket()
    report_path = tmp_path / "benchmark_report.txt"
    report_path.write_text("Benchmark Report\n")
    run_directory = _write_run_directory(tmp_path / "run", {"summary.csv": "a\n"})

    upload_baseline(f"s3://{bucket}", "PiWind", "test_1", "2.5.4", run_directory, CONFIG, report_path)

    client = boto3.client("s3", region_name=REGION)
    assert client.get_object(Bucket=bucket, Key="PiWind/test_1/2.5.4/benchmark_report.txt")["Body"].read() == b"Benchmark Report\n"
    published = json.loads(client.get_object(Bucket=bucket, Key="PiWind/test_1/2.5.4/published.json")["Body"].read())
    assert published["model"] == "PiWind"
    assert published["test"] == "test_1"
    assert published["oasislmf_version"] == "2.5.4"
    assert datetime.fromisoformat(published["published_at"]).tzinfo is not None


@mock_aws
def test_stored_baseline_is_still_found_and_downloaded_with_a_history(tmp_path):
    bucket = _make_bucket()
    _publish_at(bucket, datetime(2026, 10, 6, tzinfo=timezone.utc), {"summary.csv": "old\n"}, tmp_path, "first")
    _publish_at(bucket, datetime(2026, 10, 14, tzinfo=timezone.utc), {"summary.csv": "new\n"}, tmp_path, "second")
    config = {**CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND], "OASISLMF_VERSIONS": ["2.5.4"]}

    assert resolve_stored_versions(config) == {("PiWind", None, "2.5.4")}
    download_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", tmp_path / "download", CONFIG)

    downloaded = sorted(str(path.relative_to(tmp_path / "download")) for path in (tmp_path / "download").rglob("*") if path.is_file())
    assert downloaded == ["output/summary.csv"]
    assert (tmp_path / "download" / "output" / "summary.csv").read_text() == "new\n"


@mock_aws
def test_upload_baseline_supports_bucket_prefix(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})

    upload_baseline(f"s3://{bucket}/some/prefix", "PiWind", None, "2.5.4", run_directory, CONFIG)

    client = boto3.client("s3", region_name=REGION)
    client.get_object(Bucket=bucket, Key="some/prefix/PiWind/2.5.4/output/summary.csv")


@mock_aws
def test_upload_baseline_keeps_different_models_separate(tmp_path):
    """The same version published for two different models must not collide."""
    bucket = _make_bucket()
    piwind_directory = _write_run_directory(tmp_path / "piwind", {"summary.csv": "a,b\n1,2\n"})
    league_directory = _write_run_directory(tmp_path / "league", {"summary.csv": "x,y\n3,4\n"})

    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", piwind_directory, CONFIG)
    upload_baseline(f"s3://{bucket}", "League", None, "2.5.4", league_directory, CONFIG)

    client = boto3.client("s3", region_name=REGION)
    assert client.get_object(Bucket=bucket, Key="PiWind/2.5.4/output/summary.csv")["Body"].read() == b"a,b\n1,2\n"
    assert client.get_object(Bucket=bucket, Key="League/2.5.4/output/summary.csv")["Body"].read() == b"x,y\n3,4\n"


@mock_aws
def test_download_baseline_downloads_output_and_performance_files(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path / "run", {"summary.csv": "a,b\n1,2\n"}, result_text="COMPLETED: x in 1.0s\n")
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)

    local_directory = download_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", tmp_path / "downloaded", CONFIG)

    assert local_directory == tmp_path / "downloaded"
    assert (local_directory / "output" / "summary.csv").read_text() == "a,b\n1,2\n"
    assert (local_directory / "result.txt").read_text() == "COMPLETED: x in 1.0s\n"


@mock_aws
def test_download_baseline_warns_when_no_performance_data(tmp_path, caplog):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path / "run", {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)

    with caplog.at_level(logging.WARNING, logger="alpaca.benchmark.s3_baseline"):
        download_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", tmp_path / "downloaded", CONFIG)

    assert "No stored performance metrics found" in caplog.text
    assert not (tmp_path / "downloaded" / "result.txt").exists()


@mock_aws
def test_download_baseline_raises_when_no_stored_output(tmp_path):
    bucket = _make_bucket()

    with pytest.raises(OasisAlpacaError):
        download_baseline(f"s3://{bucket}", "PiWind", None, "9.9.9", tmp_path / "downloaded", CONFIG)


@mock_aws
def test_download_baseline_raises_when_version_exists_under_a_different_model(tmp_path):
    """A model/version baseline can't be downloaded under the wrong model."""
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path / "run", {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)

    with pytest.raises(OasisAlpacaError):
        download_baseline(f"s3://{bucket}", "League", None, "2.5.4", tmp_path / "downloaded", CONFIG)


@mock_aws
def test_upload_then_download_baseline_round_trip_matches(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(
        tmp_path / "run", {"summary.csv": "a,b\n1,2\n", "other.csv": "x,y\n3,4\n"}, result_text="COMPLETED: x in 1.0s\n"
    )

    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)
    local_directory = download_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", tmp_path / "downloaded", CONFIG)

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
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)

    stored = resolve_stored_versions({
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND],
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4"],
    })

    assert stored == {("PiWind", None, "2.5.4")}


@mock_aws
def test_resolve_stored_versions_supports_bucket_prefix(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}/some/prefix", "PiWind", None, "2.5.4", run_directory, CONFIG)

    stored = resolve_stored_versions({
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}/some/prefix", "REPO_LOCATIONS": [PIWIND],
        "OASISLMF_VERSIONS": ["2.5.4"],
    })

    assert stored == {("PiWind", None, "2.5.4")}


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
        Bucket=bucket, Key="PiWind/2.5.4/performance/result.txt", Body=b"COMPLETED: x in 1.0s\n"
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
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)
    config = {
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND],
        "OASISLMF_VERSIONS": ["2.5.4"], "PUBLISH_BASELINE": "True",
    }

    with caplog.at_level(logging.INFO, logger="alpaca.benchmark.s3_baseline"):
        assert resolve_stored_versions(config) == set()

    assert "PUBLISH_BASELINE is set" in caplog.text


@mock_aws
def test_resolve_stored_versions_finds_baselines_per_model_with_multiple_locations(tmp_path):
    """Baselines are keyed by model and version together, so each REPO_LOCATIONS entry is
    checked on its own: a baseline stored for one model doesn't stand in for another.
    """
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)
    config = {
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "OASISLMF_VERSIONS": ["2.5.4"],
        "REPO_LOCATIONS": [PIWIND, LEAGUE],
    }

    assert resolve_stored_versions(config) == {("PiWind", None, "2.5.4")}


@mock_aws
def test_resolve_stored_versions_finds_several_stored_versions(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.6", run_directory, CONFIG)

    stored = resolve_stored_versions({
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND],
        "OASISLMF_VERSIONS": ["2.5.6", "2.5.4", "2.4.9"],
    })

    assert stored == {("PiWind", None, "2.5.6"), ("PiWind", None, "2.5.4")}


@mock_aws
def test_download_baseline_skips_a_directory_marker_key(tmp_path):
    """A console-created folder shows up as a key ending in '/', which isn't a file."""
    bucket = _make_bucket()
    client = boto3.client("s3", region_name=REGION)
    client.put_object(Bucket=bucket, Key="PiWind/2.5.4/output/", Body=b"")
    client.put_object(Bucket=bucket, Key="PiWind/2.5.4/output/summary.csv", Body=b"a,b\n1,2\n")

    local_directory = download_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", tmp_path / "downloaded", CONFIG)

    assert [path.name for path in (local_directory / "output").iterdir()] == ["summary.csv"]


@mock_aws
def test_upload_baseline_skips_directories_inside_the_output_directory(tmp_path):
    """Only the output files themselves are published; a nested directory is not walked."""
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    (run_directory / "losses-x" / "output" / "nested").mkdir()

    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)

    listing = boto3.client("s3", region_name=REGION).list_objects_v2(Bucket=bucket, Prefix="PiWind/2.5.4/output/")
    assert [obj["Key"] for obj in listing["Contents"]] == ["PiWind/2.5.4/output/summary.csv"]


@mock_aws
def test_upload_baseline_keys_a_test_baseline_by_model_then_test_then_version(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"}, result_text="COMPLETED: x in 1.0s\n")

    upload_baseline(f"s3://{bucket}", "PiWind", "test_1", "2.5.4", run_directory, CONFIG)

    client = boto3.client("s3", region_name=REGION)
    keys = sorted(obj["Key"] for obj in client.list_objects_v2(Bucket=bucket)["Contents"])
    assert keys == [
        "PiWind/test_1/2.5.4/output/summary.csv", "PiWind/test_1/2.5.4/performance/result.txt",
        "PiWind/test_1/2.5.4/published.json",
    ]


@mock_aws
def test_download_baseline_does_not_mix_up_tests(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "PiWind", "test_1", "2.5.4", run_directory, CONFIG)

    with pytest.raises(OasisAlpacaError):
        download_baseline(f"s3://{bucket}", "PiWind", "test_2", "2.5.4", tmp_path / "downloaded", CONFIG)


@mock_aws
def test_resolve_stored_versions_checks_every_test(tmp_path):
    """Each TESTS entry has its own baselines, so a stored test_1 doesn't stand in for test_2."""
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "PiWind", "test_1", "2.5.4", run_directory, CONFIG)
    config = {
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "OASISLMF_VERSIONS": ["2.5.4", "2.5.6"],
        "REPO_LOCATIONS": [PIWIND], "TESTS": ["test_1", "test_2"],
    }

    assert resolve_stored_versions(config) == {("PiWind", "test_1", "2.5.4")}


@mock_aws
def test_resolve_stored_versions_ignores_an_untested_baseline_when_tests_are_set(tmp_path):
    """A baseline stored without a test is a PATH_TO_OASISLMF_JSON run, not any one test's."""
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.4", run_directory, CONFIG)
    config = {
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "OASISLMF_VERSIONS": ["2.5.4"],
        "REPO_LOCATIONS": [PIWIND], "TESTS": ["test_1"],
    }

    assert resolve_stored_versions(config) == set()


@mock_aws
def test_resolve_stored_versions_never_reuses_the_test_version(tmp_path):
    """With both versions stored, the baseline is reused but the test version still runs."""
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.7", run_directory, CONFIG)
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.8", run_directory, CONFIG)

    stored = resolve_stored_versions({
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND],
        "OASISLMF_BASELINE_VERSION": "2.5.7", "OASISLMF_TEST_VERSION": "2.5.8",
    })

    assert stored == {("PiWind", None, "2.5.7")}


@mock_aws
def test_resolve_stored_versions_never_reuses_the_test_version_of_any_test(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path, {"summary.csv": "a,b\n1,2\n"})
    for test in ("test_1", "test_2"):
        for version in ("2.5.7", "2.5.8"):
            upload_baseline(f"s3://{bucket}", "PiWind", test, version, run_directory, CONFIG)

    stored = resolve_stored_versions({
        **CONFIG, "BENCHMARK_BUCKET": f"s3://{bucket}", "REPO_LOCATIONS": [PIWIND], "TESTS": ["test_1", "test_2"],
        "OASISLMF_BASELINE_VERSION": "2.5.7", "OASISLMF_TEST_VERSION": "2.5.8",
    })

    assert stored == {("PiWind", "test_1", "2.5.7"), ("PiWind", "test_2", "2.5.7")}


def test_validate_passes_when_publishing_the_baseline_and_test_versions():
    validate_s3_baseline_config({
        "PUBLISH_BASELINE": "True", "BENCHMARK_BUCKET": "s3://alpaca-benchmark",
        "OASISLMF_BASELINE_VERSION": "2.5.7", "OASISLMF_TEST_VERSION": "2.5.8",
    })


@mock_aws
def test_upload_then_download_baseline_carries_the_manifest(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path / "run", {"summary.csv": "a,b\n1,2\n"}, "COMPLETED: x in 1s")
    (run_directory / "manifest.json").write_text('{"instance_type": "m5.xlarge"}')

    upload_baseline(f"s3://{bucket}", "PiWind", "test_1", "2.5.8", run_directory, CONFIG)
    local_directory = download_baseline(f"s3://{bucket}", "PiWind", "test_1", "2.5.8", tmp_path / "down", CONFIG)

    assert (local_directory / "manifest.json").read_text() == '{"instance_type": "m5.xlarge"}'


@mock_aws
def test_download_baseline_works_for_a_baseline_published_before_manifests(tmp_path):
    bucket = _make_bucket()
    run_directory = _write_run_directory(tmp_path / "run", {"summary.csv": "a,b\n1,2\n"}, "COMPLETED: x in 1s")
    upload_baseline(f"s3://{bucket}", "PiWind", None, "2.5.7", run_directory, CONFIG)

    local_directory = download_baseline(f"s3://{bucket}", "PiWind", None, "2.5.7", tmp_path / "down", CONFIG)

    assert not (local_directory / "manifest.json").exists()
    assert (local_directory / "output" / "summary.csv").is_file()
