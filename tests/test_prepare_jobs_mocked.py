"""Mocked S3 tests for SolverJobManager.prepare_jobs().

These tests use moto to mock AWS S3, allowing them to run without
real AWS credentials or access to internal buckets. They provide
the same coverage as the S3 integration tests in test_prepare_jobs.py.
"""

from pathlib import Path
from typing import List

import boto3
import pytest
from moto import mock_aws
import yaml

from runner.runner_jobs import SolverJobManager
from harness.aws_shim import S3FileSystem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def aws_credentials(monkeypatch):
    """Mock AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def mock_s3(aws_credentials):
    """Create a mocked S3 environment with test data."""
    with mock_aws():
        s3_client = boto3.client("s3", region_name="us-east-1")

        # Create test bucket
        bucket_name = "test-bucket"
        s3_client.create_bucket(Bucket=bucket_name)

        # Add SAT formula files (.cnf)
        for i in range(5):
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f"sat/easy/formula_{i}.cnf",
                Body=f"p cnf 3 1\n1 2 3 0\n"
            )

        # Add SMT formula files (.smt2)
        for i in range(5):
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f"smt/easy/formula_{i}.smt2",
                Body=f"(set-logic QF_LIA)\n(check-sat)\n"
            )

        # Add some non-formula files that should be filtered out
        s3_client.put_object(
            Bucket=bucket_name,
            Key="sat/easy/readme.txt",
            Body="This is not a formula"
        )

        yield {
            "client": s3_client,
            "bucket": bucket_name,
            "s3fs": S3FileSystem(s3_client),
        }


def _write_jobs_yaml(tmp_path: Path, formulas: List[str],
                     limit=None, results_dir: str = "results") -> str:
    """Write a minimal jobs YAML and return its path."""
    config = {
        "results_dir": results_dir,
        "formulas": formulas,
        "limit": limit,
        "job_options": {
            "timeout_secs": 10,
            "solver_options": [],
        },
    }
    path = tmp_path / "jobs.yml"
    path.write_text(yaml.dump(config))
    return str(path)


# ---------------------------------------------------------------------------
# Mocked S3 tests for SAT formulas
# ---------------------------------------------------------------------------

class TestMockedS3SatFormulas:
    """Test prepare_jobs with mocked S3 and solver_type=sat."""

    def test_finds_cnf_files(self, tmp_path, mock_s3):
        uri = f"s3://{mock_s3['bucket']}/sat/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri])
        jm = SolverJobManager(jobs_path)

        count = jm.prepare_jobs(mock_s3["s3fs"], "sat")

        assert count == 5
        assert all(j.endswith(".cnf") for j in jm.jobs)
        assert all(j.startswith("s3://") for j in jm.jobs)

    def test_smt_type_filters_out_cnf(self, tmp_path, mock_s3):
        uri = f"s3://{mock_s3['bucket']}/sat/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri])
        jm = SolverJobManager(jobs_path)

        count = jm.prepare_jobs(mock_s3["s3fs"], "smt")

        assert count == 0

    def test_limit_caps_results(self, tmp_path, mock_s3):
        uri = f"s3://{mock_s3['bucket']}/sat/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri], limit=2)
        jm = SolverJobManager(jobs_path)

        count = jm.prepare_jobs(mock_s3["s3fs"], "sat")

        assert count == 2


# ---------------------------------------------------------------------------
# Mocked S3 tests for SMT formulas
# ---------------------------------------------------------------------------

class TestMockedS3SmtFormulas:
    """Test prepare_jobs with mocked S3 and solver_type=smt."""

    def test_finds_smt2_files(self, tmp_path, mock_s3):
        uri = f"s3://{mock_s3['bucket']}/smt/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri])
        jm = SolverJobManager(jobs_path)

        count = jm.prepare_jobs(mock_s3["s3fs"], "smt")

        assert count == 5
        assert all(j.endswith(".smt2") for j in jm.jobs)

    def test_sat_type_filters_out_smt2(self, tmp_path, mock_s3):
        uri = f"s3://{mock_s3['bucket']}/smt/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri])
        jm = SolverJobManager(jobs_path)

        count = jm.prepare_jobs(mock_s3["s3fs"], "sat")

        assert count == 0


# ---------------------------------------------------------------------------
# Mocked S3 tests for multiple directories
# ---------------------------------------------------------------------------

class TestMockedS3MultipleDirs:
    """Test prepare_jobs with multiple S3 directories."""

    def test_combines_multiple_dirs(self, tmp_path, mock_s3):
        uri = f"s3://{mock_s3['bucket']}/sat/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri, uri])
        jm = SolverJobManager(jobs_path)

        count = jm.prepare_jobs(mock_s3["s3fs"], "sat")

        # Same dir listed twice should double the results
        assert count == 10

    def test_mixed_sat_and_smt_dirs(self, tmp_path, mock_s3):
        sat_uri = f"s3://{mock_s3['bucket']}/sat/easy"
        smt_uri = f"s3://{mock_s3['bucket']}/smt/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [sat_uri, smt_uri])
        jm = SolverJobManager(jobs_path)

        # With solver_type=sat, only .cnf files from sat/easy
        count = jm.prepare_jobs(mock_s3["s3fs"], "sat")
        assert count == 5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestMockedS3EdgeCases:
    """Test edge cases with mocked S3."""

    def test_empty_directory(self, tmp_path, mock_s3):
        # Create an empty prefix
        uri = f"s3://{mock_s3['bucket']}/empty"
        jobs_path = _write_jobs_yaml(tmp_path, [uri])
        jm = SolverJobManager(jobs_path)

        count = jm.prepare_jobs(mock_s3["s3fs"], "sat")

        assert count == 0

    def test_filters_non_formula_files(self, tmp_path, mock_s3):
        """Verify that non-.cnf/.smt2 files are filtered out."""
        uri = f"s3://{mock_s3['bucket']}/sat/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri])
        jm = SolverJobManager(jobs_path)

        count = jm.prepare_jobs(mock_s3["s3fs"], "sat")

        # Should only get .cnf files, not readme.txt
        assert count == 5
        assert not any("readme.txt" in j for j in jm.jobs)
