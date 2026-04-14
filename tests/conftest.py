"""Shared fixtures and configuration for tests."""

import os
import pytest
import boto3

from harness.aws_shim import S3FileSystem


# Test bucket must be configured via environment variable
# External contributors: set TEST_S3_BUCKET to your own bucket
# Run `python tests/setup_test_bucket.py` to populate test data


def _has_aws_credentials() -> bool:
    """Check if valid AWS credentials are available."""
    try:
        boto3.client("sts").get_caller_identity()
        return True
    except Exception:
        return False


requires_aws = pytest.mark.skipif(
    not _has_aws_credentials(),
    reason="AWS credentials not available",
)


@pytest.fixture(scope="session")
def test_bucket() -> str:
    """The S3 bucket used for integration tests.

    Must be configured via TEST_S3_BUCKET environment variable.
    """
    bucket = os.environ.get("TEST_S3_BUCKET")
    if not bucket:
        pytest.skip(
            "TEST_S3_BUCKET environment variable not set. "
            "S3 integration tests require a configured test bucket."
        )
    return bucket


@pytest.fixture(scope="session")
def s3_client():
    """A boto3 S3 client for test setup/teardown."""
    return boto3.client("s3")


@pytest.fixture(scope="session")
def s3fs(s3_client, test_bucket) -> S3FileSystem:
    """An S3FileSystem instance for use in tests.

    Validates that the test bucket exists and has test data.
    Run `python tests/setup_test_bucket.py` to populate the bucket.
    """
    fs = S3FileSystem(s3_client)

    # Check that the test bucket has expected test directories
    try:
        sat_files = fs.ls(test_bucket, "sat/easy", recursive=False)
        smt_files = fs.ls(test_bucket, "smt/easy", recursive=False)
    except Exception as e:
        pytest.skip(
            f"Test bucket '{test_bucket}' not accessible: {e}\n"
            f"Run `python tests/setup_test_bucket.py` to set up test data."
        )

    if not sat_files and not smt_files:
        pytest.skip(
            f"Test bucket '{test_bucket}' exists but is empty.\n"
            f"Run `python tests/setup_test_bucket.py` to populate test data."
        )

    return fs
