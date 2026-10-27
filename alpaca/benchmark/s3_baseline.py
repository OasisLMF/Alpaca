from alpaca.benchmark.comparison import find_output_dir
from alpaca.benchmark.manifest import MANIFEST_FILENAME
from alpaca.benchmark.report import REPORT_FILENAME
from alpaca.benchmark.scripts import (
    benchmark_locations, benchmark_tests, benchmark_versions, group_name, model_name_from_location
)
from alpaca.benchmark.timing import find_result_file
from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import boto3
import json
import logging

logger = logging.getLogger(__name__)

PERFORMANCE_RESULT_FILENAME = "result.txt"
PUBLISHED_FILENAME = "published.json"
HISTORY_DIRECTORY = "history"
HISTORY_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
DELETE_BATCH_SIZE = 1000


def _parse_bucket_uri(bucket_uri):
    """Split an S3 bucket URI into its bucket name and any prefix.

    Args:
        bucket_uri: e.g. 's3://alpaca-benchmark' or 's3://alpaca-benchmark/some/prefix'.

    Returns:
        tuple[str, str]: (bucket, prefix). prefix is '' when the URI has no extra path.
    """
    parsed = urlparse(bucket_uri)
    return parsed.netloc, parsed.path.strip("/")


def _baseline_prefix(bucket_uri, model, test, version):
    """Build the (bucket, key_prefix) a model/test/version's baseline is stored under.

    Args:
        bucket_uri: S3 bucket URI, see _parse_bucket_uri.
        model: Short model name the baseline was run against, see
            alpaca.benchmark.scripts.model_name_from_location.
        test: TESTS entry the baseline was run from, or None when it was run from
            PATH_TO_OASISLMF_JSON.
        version: OasisLMF version the baseline is stored under.

    Returns:
        tuple[str, str]: (bucket, prefix), with any bucket-level prefix, the model, the test
            and the version joined together as '<prefix>/<model>/<test>/<version>', or
            '<prefix>/<model>/<version>' when there's no test.
    """
    bucket, prefix = _parse_bucket_uri(bucket_uri)
    return bucket, "/".join(part for part in (prefix, model, test, version) if part)


def _s3_client(config):
    """Create a boto3 S3 client from a benchmark config's AWS settings.

    Mirrors alpaca.remote_controller.RemoteController._aws_client, but for local
    (non-EC2) S3 access from the controller machine, which nothing else in Alpaca does
    today (all other S3 access runs as 'aws s3 cp' shell commands on the EC2 instance).

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        botocore.client.BaseClient: S3 client bound to the configured region/profile.
    """
    session = boto3.Session(
        profile_name=config.get("AWS_PROFILE") or None,
        region_name=config.get("AWS_REGION", "eu-west-1"),
    )
    return session.client("s3")


def validate_s3_baseline_config(config):
    """Validate BENCHMARK_BUCKET/PUBLISH_BASELINE combinations before any EC2 spend.

    Args:
        config: Validated benchmark configuration dictionary.

    Raises:
        OasisAlpacaConfigError: If PUBLISH_BASELINE is set without BENCHMARK_BUCKET, or
            without any version to publish under (see
            alpaca.benchmark.scripts.benchmark_versions), since a baseline is stored under a
            version and a branch target hasn't got one.
    """
    if not config.get("PUBLISH_BASELINE", False):
        return

    if not config.get("BENCHMARK_BUCKET"):
        raise OasisAlpacaConfigError("PUBLISH_BASELINE requires BENCHMARK_BUCKET to be set")
    if not benchmark_versions(config):
        raise OasisAlpacaConfigError("PUBLISH_BASELINE requires OASISLMF_VERSIONS entries, as a branch has no version to publish under")


def validate_baseline_as_of(config):
    """Validate BASELINE_AS_OF before any EC2 spend.

    Args:
        config: Validated benchmark configuration dictionary.

    Raises:
        OasisAlpacaConfigError: If BASELINE_AS_OF is set without BENCHMARK_BUCKET or
            OASISLMF_BASELINE_VERSION (it picks which stored baseline that version is compared
            from, so means nothing for OASISLMF_VERSIONS peers), alongside PUBLISH_BASELINE
            (which runs every version rather than reusing any stored one), or isn't a date or
            history stamp, see parse_baseline_as_of.
    """
    as_of = config.get("BASELINE_AS_OF")
    if not as_of:
        return
    parse_baseline_as_of(as_of)
    if not config.get("BENCHMARK_BUCKET"):
        raise OasisAlpacaConfigError("BASELINE_AS_OF requires BENCHMARK_BUCKET to be set")
    if not config.get("OASISLMF_BASELINE_VERSION"):
        raise OasisAlpacaConfigError("BASELINE_AS_OF requires OASISLMF_BASELINE_VERSION and OASISLMF_TEST_VERSION to be set")
    if config.get("PUBLISH_BASELINE", False):
        raise OasisAlpacaConfigError("Set either BASELINE_AS_OF or PUBLISH_BASELINE, not both")


def parse_baseline_as_of(as_of):
    """Turn a BASELINE_AS_OF value into the moment a baseline must have been published before.

    Args:
        as_of: A date, '2026-10-08', meaning the baseline that was current at the end of that day
            (UTC), or a history stamp, '20261008-141200', meaning the one current at that second
            (UTC), so a baseline's own history folder name picks exactly that baseline.

    Returns:
        datetime: The UTC cutoff; a baseline published strictly before it qualifies.

    Raises:
        OasisAlpacaConfigError: If as_of is neither. A day-first or two-digit-year date such as
            '8/10/26' is ambiguous, so isn't guessed at.
    """
    for value_format, step in (("%Y-%m-%d", timedelta(days=1)), (HISTORY_TIMESTAMP_FORMAT, timedelta(seconds=1))):
        try:
            return datetime.strptime(as_of, value_format).replace(tzinfo=timezone.utc) + step
        except ValueError:
            continue
    raise OasisAlpacaConfigError(
        f"BASELINE_AS_OF must be a date (YYYY-MM-DD, e.g. 2026-10-08) or a history stamp (YYYYMMDD-HHMMSS, "
        f"e.g. 20261008-141200), got '{as_of}'"
    )


def _baseline_snapshots(client, bucket, prefix):
    """List every stored copy of a model/test/version's baseline: the current one and its history.

    Args:
        client: boto3 S3 client, see _s3_client.
        bucket: Bucket name.
        prefix: The baseline's key prefix, see _baseline_prefix.

    Returns:
        list[dict]: {'stamp', 'published_at'} per copy, oldest first. 'stamp' is the copy's
            history folder name, or None for the current baseline, and 'published_at' is when
            it was published (see _published_at for the current one). A history folder whose
            name isn't a stamp wasn't made by _archive_baseline, so is left out.
    """
    snapshots = []
    current = _current_baseline_keys(client, bucket, prefix)
    if any(obj["Key"].startswith(f"{prefix}/output/") for obj in current):
        snapshots.append({"stamp": None, "published_at": _published_at(client, bucket, prefix, current)})

    history = f"{prefix}/{HISTORY_DIRECTORY}/"
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=history, Delimiter="/"):
        for common_prefix in page.get("CommonPrefixes", []):
            stamp = common_prefix["Prefix"][len(history):].rstrip("/")
            try:
                published_at = datetime.strptime(stamp, HISTORY_TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            snapshots.append({"stamp": stamp, "published_at": published_at})
    return sorted(snapshots, key=lambda snapshot: snapshot["published_at"])


def resolve_baseline_snapshots(config):
    """Pick, for BASELINE_AS_OF, which stored copy of each OASISLMF_BASELINE_VERSION baseline to compare against.

    The copy picked is the one that was current at BASELINE_AS_OF: the latest published before
    its cutoff (see parse_baseline_as_of), whether that's the current baseline or one moved
    into its history since. Every model and test needs one, since the point of BASELINE_AS_OF is
    comparing against that dated run, so a gap is an error before any EC2 spend rather than the
    baseline quietly being run live today.

    Args:
        config: Validated benchmark configuration dictionary, see validate_baseline_as_of.

    Returns:
        dict: (model, test, version) -> {'stamp', 'published_at'} (see _baseline_snapshots), one
            per REPO_LOCATIONS and TESTS entry at OASISLMF_BASELINE_VERSION. Empty when
            BASELINE_AS_OF isn't set.

    Raises:
        OasisAlpacaConfigError: If the bucket can't be read, or a model/test has no baseline
            stored at all or none published by BASELINE_AS_OF (naming its earliest).
    """
    as_of = config.get("BASELINE_AS_OF")
    if not as_of:
        return {}

    cutoff = parse_baseline_as_of(as_of)
    version = config["OASISLMF_BASELINE_VERSION"]
    client = _s3_client(config)
    picked = {}
    for model in (model_name_from_location(location) for location in benchmark_locations(config)):
        for test in benchmark_tests(config):
            bucket, prefix = _baseline_prefix(config["BENCHMARK_BUCKET"], model, test, version)
            name = group_name(model, test)
            try:
                snapshots = _baseline_snapshots(client, bucket, prefix)
            except ClientError as error:
                raise OasisAlpacaConfigError(f"Could not read stored baselines from {config['BENCHMARK_BUCKET']}: {error}")
            if not snapshots:
                raise OasisAlpacaConfigError(
                    f"BASELINE_AS_OF is set, but no {name} {version} baseline is stored at s3://{bucket}/{prefix}"
                )
            eligible = [snapshot for snapshot in snapshots if snapshot["published_at"] < cutoff]
            if not eligible:
                raise OasisAlpacaConfigError(
                    f"No {name} {version} baseline was published by BASELINE_AS_OF {as_of}; the earliest stored was "
                    f"published {snapshots[0]['published_at']:%Y-%m-%d %H:%M:%S} UTC"
                )
            picked[(model, test, version)] = eligible[-1]
            logger.info(
                f"Using the {name} {version} baseline published {eligible[-1]['published_at']:%Y-%m-%d %H:%M:%S} UTC "
                f"(BASELINE_AS_OF {as_of})"
            )
    return picked


def resolve_stored_versions(config):
    """Find which (model, test, version) triples already have a stored baseline to reuse.

    A model/test/version whose baseline is already in BENCHMARK_BUCKET doesn't need an EC2
    run: the stored output and performance metrics stand in for it. Baselines are keyed by
    model, test and version together, so this is checked per REPO_LOCATIONS and TESTS entry
    rather than being limited to a single-model benchmark. PUBLISH_BASELINE opts out entirely, since
    republishing a version means running it rather than reusing what's already there, and
    OASISLMF_TEST_VERSION is never looked up, since it's the version the benchmark is there to
    run.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        set[tuple]: (model, test, version) triples with a stored baseline output in
            BENCHMARK_BUCKET, empty when there's nothing to reuse. test is None when TESTS
            isn't set.
    """
    bucket = config.get("BENCHMARK_BUCKET")
    test_version = config.get("OASISLMF_TEST_VERSION")
    versions = [version for version in benchmark_versions(config) if version != test_version]
    models = [model_name_from_location(location) for location in benchmark_locations(config)]
    if not bucket or not versions or not models:
        return set()

    if config.get("PUBLISH_BASELINE", False):
        logger.info("PUBLISH_BASELINE is set, so every version target runs rather than reusing a stored baseline")
        return set()

    client = _s3_client(config)
    stored = {
        (model, test, version)
        for model in models
        for test in benchmark_tests(config)
        for version in versions
        if _baseline_exists(client, bucket, model, test, version)
    }
    for model, test, version in stored:
        logger.info(f"Reusing the stored {group_name(model, test)} {version} baseline from {bucket} instead of running it")
    return stored


def _baseline_exists(client, bucket_uri, model, test, version):
    """Check whether a model/test/version has stored baseline output in a bucket.

    Args:
        client: boto3 S3 client, see _s3_client.
        bucket_uri: S3 bucket URI the baselines are stored under.
        model: Short model name to look for, see model_name_from_location.
        test: TESTS entry to look for, or None when TESTS isn't set.
        version: OasisLMF version to look for.

    Returns:
        bool: True if any object exists under that model/test/version's 'output/' prefix.

    Raises:
        OasisAlpacaConfigError: If the bucket can't be read, e.g. it doesn't exist or the
            credentials can't list it. This runs before any EC2 spend, so it's worth naming
            the bucket rather than letting a botocore error through.
    """
    bucket, prefix = _baseline_prefix(bucket_uri, model, test, version)
    try:
        listing = client.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/output/", MaxKeys=1)
    except ClientError as error:
        raise OasisAlpacaConfigError(f"Could not read stored baselines from {bucket_uri}: {error}")
    return bool(listing.get("KeyCount"))


def _current_baseline_keys(client, bucket, prefix):
    """List every object of a model/test/version's current baseline, leaving out its history.

    Args:
        client: boto3 S3 client, see _s3_client.
        bucket: Bucket name.
        prefix: The baseline's key prefix, see _baseline_prefix.

    Returns:
        list[dict]: list_objects_v2 'Contents' entries ('Key', 'LastModified', ...).
    """
    history = f"{prefix}/{HISTORY_DIRECTORY}/"
    paginator = client.get_paginator("list_objects_v2")
    return [
        obj
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/")
        for obj in page.get("Contents", [])
        if not obj["Key"].startswith(history)
    ]


def _published_at(client, bucket, prefix, objects):
    """Find when the current baseline was published, to name its folder in the history.

    Args:
        client: boto3 S3 client, see _s3_client.
        bucket: Bucket name.
        prefix: The baseline's key prefix, see _baseline_prefix.
        objects: The baseline's objects, see _current_baseline_keys.

    Returns:
        datetime: The 'published_at' its published.json records, or, for a baseline published
            before those existed (or one whose published.json can't be read), when its newest
            object was last written.
    """
    try:
        body = client.get_object(Bucket=bucket, Key=f"{prefix}/{PUBLISHED_FILENAME}")["Body"].read()
        return datetime.fromisoformat(json.loads(body)["published_at"])
    except (ClientError, ValueError, KeyError, TypeError):
        return max(obj["LastModified"] for obj in objects)


def _archive_baseline(client, bucket, prefix):
    """Move a model/test/version's current baseline into its history, before it's replaced.

    Everything stored for the baseline (its output, performance data, report and
    published.json) is copied, server side, to '<prefix>/history/<published at>/' with the same
    layout, e.g. 'PiWind/test_1/2.5.7/history/20261006-141200/output/...', and only once every
    copy has worked is the original deleted. That leaves nothing of the old run behind for the
    new one to be mixed up with, while keeping it to read or re-download later. Benchmarks only
    ever reuse a baseline's current 'output/', so nothing in the history is reused.

    Args:
        client: boto3 S3 client, see _s3_client.
        bucket: Bucket name.
        prefix: The baseline's key prefix, see _baseline_prefix.

    Returns:
        str or None: The history prefix the baseline was moved to, or None when there was no
            baseline to move.
    """
    objects = _current_baseline_keys(client, bucket, prefix)
    if not objects:
        return None

    stamp = _published_at(client, bucket, prefix, objects).astimezone(timezone.utc).strftime(HISTORY_TIMESTAMP_FORMAT)
    history_prefix = f"{prefix}/{HISTORY_DIRECTORY}/{stamp}"
    for obj in objects:
        relative_key = obj["Key"][len(prefix) + 1:]
        client.copy({"Bucket": bucket, "Key": obj["Key"]}, bucket, f"{history_prefix}/{relative_key}")

    keys = [obj["Key"] for obj in objects]
    for start in range(0, len(keys), DELETE_BATCH_SIZE):
        batch = keys[start:start + DELETE_BATCH_SIZE]
        client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True})
    return history_prefix


def upload_baseline(bucket_uri, model, test, version, result_directory, config, report_path=None):
    """Publish a benchmark target's output and performance data as a model/test/version's baseline.

    Any baseline already stored for that model, test and version is moved into its history
    first (see _archive_baseline), so it's kept rather than overwritten. The performance data is
    the run's result.txt and, when there is one, its manifest.json (see
    alpaca.benchmark.manifest), so a later benchmark reusing the baseline can check it ran
    under the same conditions. The benchmark's report goes alongside, so a baseline, current or archived, can be read without
    re-running anything, and a published.json records when and what was published.

    Args:
        bucket_uri: S3 bucket URI (e.g. 's3://alpaca-benchmark') to publish under.
        model: Short model name this run's results represent, see model_name_from_location.
        test: TESTS entry this run's results represent, or None when TESTS isn't set.
        version: OasisLMF version this run's results represent.
        result_directory: Local directory the target's results were downloaded to (a
            RESULT_DIRECTORY from build_benchmark_targets).
        config: Validated benchmark configuration dictionary, for AWS session settings.
        report_path: The benchmark_report.txt of the benchmark that produced this run, or None
            to publish without one.

    Raises:
        OasisAlpacaError: If result_directory has no 'output' directory under it (see
            find_output_dir). This is checked before the stored baseline is touched.
    """
    bucket, prefix = _baseline_prefix(bucket_uri, model, test, version)
    client = _s3_client(config)
    name = group_name(model, test)
    output_dir = find_output_dir(result_directory)

    history_prefix = _archive_baseline(client, bucket, prefix)
    if history_prefix is not None:
        logger.info(f"Moved the previous {name} {version} baseline to s3://{bucket}/{history_prefix}")

    for file_path in sorted(output_dir.iterdir()):
        if file_path.is_file():
            client.upload_file(str(file_path), bucket, f"{prefix}/output/{file_path.name}")
    logger.info(f"Published {name} {version} baseline output to s3://{bucket}/{prefix}/output")

    result_file = find_result_file(result_directory)
    if result_file is not None:
        client.upload_file(str(result_file), bucket, f"{prefix}/performance/{PERFORMANCE_RESULT_FILENAME}")
        logger.info(f"Published {name} {version} performance metrics to s3://{bucket}/{prefix}/performance")

    manifest_file = Path(result_directory) / MANIFEST_FILENAME
    if manifest_file.is_file():
        client.upload_file(str(manifest_file), bucket, f"{prefix}/performance/{MANIFEST_FILENAME}")
        logger.info(f"Published {name} {version} manifest to s3://{bucket}/{prefix}/performance")

    if report_path is not None and Path(report_path).is_file():
        client.upload_file(str(report_path), bucket, f"{prefix}/{REPORT_FILENAME}")

    published = {
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "test": test,
        "oasislmf_version": version,
    }
    client.put_object(Bucket=bucket, Key=f"{prefix}/{PUBLISHED_FILENAME}", Body=json.dumps(published, indent=4).encode())


def download_baseline(bucket_uri, model, test, version, local_directory, config, stamp=None):
    """Download a model/test/version's stored baseline output and performance data locally.

    Downloads into a shape identical to a normal run's downloaded result directory
    (local_directory/output/*, local_directory/result.txt and, when one was published,
    local_directory/manifest.json), so find_output_dir, find_result_file,
    resolve_model_runtime and read_manifest all work on it unmodified. The current baseline is
    downloaded unless stamp picks one of its history's copies instead (see
    resolve_baseline_snapshots).

    Args:
        bucket_uri: S3 bucket URI the baseline is stored under.
        model: Short model name to fetch the baseline for, see model_name_from_location.
        test: TESTS entry to fetch the baseline for, or None when TESTS isn't set.
        version: OasisLMF version to fetch the baseline for.
        local_directory: Local directory to download into.
        config: Validated benchmark configuration dictionary, for AWS session settings.
        stamp: History folder name of the copy to download, e.g. '20261008-141200', or None for
            the current baseline.

    Returns:
        Path: local_directory, for convenience.

    Raises:
        OasisAlpacaError: If no stored output exists for that model/test/version at that bucket.
    """
    bucket, prefix = _baseline_prefix(bucket_uri, model, test, version)
    if stamp is not None:
        prefix = f"{prefix}/{HISTORY_DIRECTORY}/{stamp}"
    client = _s3_client(config)

    local_directory = Path(local_directory)
    output_dir = local_directory / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    paginator = client.get_paginator("list_objects_v2")
    found_output = False
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/output/"):
        for obj in page.get("Contents", []):
            filename = obj["Key"].rsplit("/", 1)[-1]
            if not filename:
                continue
            found_output = True
            client.download_file(bucket, obj["Key"], str(output_dir / filename))

    if not found_output:
        raise OasisAlpacaError(f"No stored baseline found at s3://{bucket}/{prefix}/output/")

    try:
        client.download_file(
            bucket, f"{prefix}/performance/{PERFORMANCE_RESULT_FILENAME}",
            str(local_directory / PERFORMANCE_RESULT_FILENAME),
        )
    except ClientError:
        logger.warning(f"No stored performance metrics found at s3://{bucket}/{prefix}/performance/")

    try:
        client.download_file(bucket, f"{prefix}/performance/{MANIFEST_FILENAME}", str(local_directory / MANIFEST_FILENAME))
    except ClientError:
        logger.info(f"No stored manifest found at s3://{bucket}/{prefix}/performance/ (published before manifests existed)")

    return local_directory
