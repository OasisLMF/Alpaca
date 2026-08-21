from alpaca.benchmark.comparison import find_output_dir
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

    Single-run mode (no REPO_LOCATION_COMPARISON) is the only mode these keys affect;
    if they're set alongside a dual-target run they're logged and ignored rather than
    raising, since a dual run's own live comparison target makes them redundant, not
    invalid.

    Args:
        config: Validated benchmark configuration dictionary.

    Raises:
        OasisAlpacaConfigError: If PUBLISH_BASELINE is set without BENCHMARK_BUCKET or a
            concrete OASISLMF_VERSION, or if OASISLMF_VERSION_COMPARISON is set in
            single-run mode without BENCHMARK_BUCKET.
    """
    single_run_mode = not config.get("REPO_LOCATION_COMPARISON")
    publish_baseline = str(config.get("PUBLISH_BASELINE", "False")).lower() == "true"
    bucket = config.get("BENCHMARK_BUCKET")

    if not single_run_mode:
        if bucket or publish_baseline:
            logger.warning(
                "BENCHMARK_BUCKET/PUBLISH_BASELINE only apply in single-run mode (no "
                "REPO_LOCATION_COMPARISON); ignoring them for this dual-target run"
            )
        return

    if publish_baseline:
        if not bucket:
            raise OasisAlpacaConfigError("PUBLISH_BASELINE requires BENCHMARK_BUCKET to be set")
        if not config.get("OASISLMF_VERSION"):
            raise OasisAlpacaConfigError("PUBLISH_BASELINE requires a specific OASISLMF_VERSION, not 'latest'")

    if config.get("OASISLMF_VERSION_COMPARISON") and not bucket:
        raise OasisAlpacaConfigError(
            "OASISLMF_VERSION_COMPARISON requires BENCHMARK_BUCKET when REPO_LOCATION_COMPARISON is omitted"
        )


def upload_baseline(bucket_uri, version, result_directory, config):
    """Publish a benchmark target's output and performance data as a version's baseline.

    Args:
        bucket_uri: S3 bucket URI (e.g. 's3://alpaca-benchmark') to publish under.
        version: OasisLMF version this run's results represent.
        result_directory: Local directory the target's results were downloaded to (a
            RESULT_DIRECTORY from build_model_run_configs).
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
