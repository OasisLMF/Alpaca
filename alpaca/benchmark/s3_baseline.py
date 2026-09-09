from alpaca.benchmark.comparison import find_output_dir
from alpaca.benchmark.scripts import benchmark_locations
from alpaca.benchmark.timing import find_result_file
from alpaca.exceptions import OasisAlpacaConfigError, OasisAlpacaError
from botocore.exceptions import ClientError
from pathlib import Path
from urllib.parse import urlparse

import boto3
import logging

logger = logging.getLogger(__name__)

PERFORMANCE_RESULT_FILENAME = "result.txt"


def _parse_bucket_uri(bucket_uri):
    """Split an S3 bucket URI into its bucket name and any prefix.

    Args:
        bucket_uri: e.g. 's3://alpaca-benchmark' or 's3://alpaca-benchmark/some/prefix'.

    Returns:
        tuple[str, str]: (bucket, prefix). prefix is '' when the URI has no extra path.
    """
    parsed = urlparse(bucket_uri)
    return parsed.netloc, parsed.path.strip("/")


def _version_prefix(bucket_uri, version):
    """Build the (bucket, key_prefix) a version's baseline is stored under.

    Args:
        bucket_uri: S3 bucket URI, see _parse_bucket_uri.
        version: OasisLMF version the baseline is stored under.

    Returns:
        tuple[str, str]: (bucket, prefix), with any bucket-level prefix and the version
            joined together.
    """
    bucket, prefix = _parse_bucket_uri(bucket_uri)
    return bucket, "/".join(part for part in (prefix, version) if part)


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
            without any OASISLMF_VERSIONS entry to publish under, since a baseline is stored
            under a version and a branch target hasn't got one.
    """
    if not config.get("PUBLISH_BASELINE", False):
        return

    if not config.get("BENCHMARK_BUCKET"):
        raise OasisAlpacaConfigError("PUBLISH_BASELINE requires BENCHMARK_BUCKET to be set")
    if not config.get("OASISLMF_VERSIONS"):
        raise OasisAlpacaConfigError("PUBLISH_BASELINE requires OASISLMF_VERSIONS entries, as a branch has no version to publish under")


def resolve_stored_versions(config):
    """Find which of a benchmark's versions already have a stored baseline to reuse.

    A version whose baseline is already in BENCHMARK_BUCKET doesn't need an EC2 run: the
    stored output and performance metrics stand in for it. Baselines are keyed by version
    alone, so this only applies when the benchmark runs a single model location - with more
    than one, the same stored output would be reused for every location and the comparison
    would be meaningless. PUBLISH_BASELINE also opts out, since republishing a version means
    running it rather than reusing what's already there.

    Args:
        config: Validated benchmark configuration dictionary.

    Returns:
        set[str]: The OASISLMF_VERSIONS entries with a stored baseline output in
            BENCHMARK_BUCKET, empty when there's nothing to reuse.
    """
    bucket = config.get("BENCHMARK_BUCKET")
    versions = config.get("OASISLMF_VERSIONS") or []
    if not bucket or not versions:
        return set()

    if config.get("PUBLISH_BASELINE", False):
        logger.info("PUBLISH_BASELINE is set, so every version target runs rather than reusing a stored baseline")
        return set()
    if len(benchmark_locations(config)) > 1:
        logger.warning(
            "Stored baselines are keyed by OasisLMF version only, so they can't be told apart per model; "
            "running every version live because REPO_LOCATIONS holds more than one location"
        )
        return set()

    client = _s3_client(config)
    stored = {version for version in versions if _baseline_exists(client, bucket, version)}
    for version in stored:
        logger.info(f"Reusing the stored {version} baseline from {bucket} instead of running it")
    return stored


def _baseline_exists(client, bucket_uri, version):
    """Check whether a version has stored baseline output in a bucket.

    Args:
        client: boto3 S3 client, see _s3_client.
        bucket_uri: S3 bucket URI the baselines are stored under.
        version: OasisLMF version to look for.

    Returns:
        bool: True if any object exists under that version's 'output/' prefix.

    Raises:
        OasisAlpacaConfigError: If the bucket can't be read, e.g. it doesn't exist or the
            credentials can't list it. This runs before any EC2 spend, so it's worth naming
            the bucket rather than letting a botocore error through.
    """
    bucket, version_prefix = _version_prefix(bucket_uri, version)
    try:
        listing = client.list_objects_v2(Bucket=bucket, Prefix=f"{version_prefix}/output/", MaxKeys=1)
    except ClientError as error:
        raise OasisAlpacaConfigError(f"Could not read stored baselines from {bucket_uri}: {error}")
    return bool(listing.get("KeyCount"))


def upload_baseline(bucket_uri, version, result_directory, config):
    """Publish a benchmark target's output and performance data as a version's baseline.

    Args:
        bucket_uri: S3 bucket URI (e.g. 's3://alpaca-benchmark') to publish under.
        version: OasisLMF version this run's results represent.
        result_directory: Local directory the target's results were downloaded to (a
            RESULT_DIRECTORY from build_benchmark_targets).
        config: Validated benchmark configuration dictionary, for AWS session settings.

    Raises:
        OasisAlpacaError: If result_directory has no 'output' directory under it (see
            find_output_dir).
    """
    bucket, version_prefix = _version_prefix(bucket_uri, version)
    client = _s3_client(config)

    existing = client.list_objects_v2(Bucket=bucket, Prefix=f"{version_prefix}/", MaxKeys=1)
    if existing.get("KeyCount"):
        logger.warning(f"Overwriting existing baseline at s3://{bucket}/{version_prefix}")

    output_dir = find_output_dir(result_directory)
    for file_path in sorted(output_dir.iterdir()):
        if file_path.is_file():
            client.upload_file(str(file_path), bucket, f"{version_prefix}/output/{file_path.name}")
    logger.info(f"Published {version} baseline output to s3://{bucket}/{version_prefix}/output")

    result_file = find_result_file(result_directory)
    if result_file is not None:
        client.upload_file(str(result_file), bucket, f"{version_prefix}/performance/{PERFORMANCE_RESULT_FILENAME}")
        logger.info(f"Published {version} performance metrics to s3://{bucket}/{version_prefix}/performance")


def download_baseline(bucket_uri, version, local_directory, config):
    """Download a version's stored baseline output and performance data locally.

    Downloads into a shape identical to a normal run's downloaded result directory
    (local_directory/output/*, local_directory/result.txt), so find_output_dir,
    find_result_file and resolve_model_runtime all work on it unmodified.

    Args:
        bucket_uri: S3 bucket URI the baseline is stored under.
        version: OasisLMF version to fetch the baseline for.
        local_directory: Local directory to download into.
        config: Validated benchmark configuration dictionary, for AWS session settings.

    Returns:
        Path: local_directory, for convenience.

    Raises:
        OasisAlpacaError: If no stored output exists for that version at that bucket.
    """
    bucket, version_prefix = _version_prefix(bucket_uri, version)
    client = _s3_client(config)

    local_directory = Path(local_directory)
    output_dir = local_directory / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    paginator = client.get_paginator("list_objects_v2")
    found_output = False
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{version_prefix}/output/"):
        for obj in page.get("Contents", []):
            filename = obj["Key"].rsplit("/", 1)[-1]
            if not filename:
                continue
            found_output = True
            client.download_file(bucket, obj["Key"], str(output_dir / filename))

    if not found_output:
        raise OasisAlpacaError(f"No stored baseline found at s3://{bucket}/{version_prefix}/output/")

    try:
        client.download_file(
            bucket, f"{version_prefix}/performance/{PERFORMANCE_RESULT_FILENAME}",
            str(local_directory / PERFORMANCE_RESULT_FILENAME),
        )
    except ClientError:
        logger.warning(f"No stored performance metrics found at s3://{bucket}/{version_prefix}/performance/")

    return local_directory
