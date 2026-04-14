"""Tests for SolverJobManager.prepare_jobs().

Tests cover:
  - S3 directory listing with extension filtering (requires AWS credentials)
  - Wrong solver_type filters out all files
  - Limit parameter caps the number of jobs
  - Non-S3 paths are rejected
  - Multiple S3 directories
"""

from pathlib import Path
from typing import List

import pytest
import yaml

from runner.runner_jobs import SolverJobManager
from harness.aws_shim import S3FileSystem
from tests.conftest import requires_aws


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
# Validation tests (no AWS needed)
# ---------------------------------------------------------------------------

class TestFormulaValidation:
    """Test that non-S3 paths are rejected."""

    def test_rejects_local_path(self, tmp_path):
        jobs_path = _write_jobs_yaml(tmp_path, ["/home/user/formulas"])
        jm = SolverJobManager(jobs_path)
        s3 = S3FileSystem.get_local_s3_file_system()
        with pytest.raises(SystemExit):
            jm.prepare_jobs(s3, "sat")

    def test_rejects_relative_path(self, tmp_path):
        jobs_path = _write_jobs_yaml(tmp_path, ["benchmarks/sat/easy"])
        jm = SolverJobManager(jobs_path)
        s3 = S3FileSystem.get_local_s3_file_system()
        with pytest.raises(SystemExit):
            jm.prepare_jobs(s3, "sat")


# ---------------------------------------------------------------------------
# S3 integration tests (require AWS credentials + populated test bucket)
# ---------------------------------------------------------------------------

@requires_aws
class TestS3SatFormulas:
    """Test prepare_jobs with S3 URIs and solver_type=sat."""

    def test_finds_cnf_files_on_s3(self, tmp_path, test_bucket, s3fs):
        uri = f"s3://{test_bucket}/sat/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri])
        jm = SolverJobManager(jobs_path)
        count = jm.prepare_jobs(s3fs, "sat")
        assert count > 0
        assert all(j.endswith(".cnf") for j in jm.jobs)
        assert all(j.startswith("s3://") for j in jm.jobs)

    def test_smt_type_filters_out_cnf_on_s3(self, tmp_path, test_bucket, s3fs):
        uri = f"s3://{test_bucket}/sat/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri])
        jm = SolverJobManager(jobs_path)
        count = jm.prepare_jobs(s3fs, "smt")
        assert count == 0

    def test_limit_caps_results(self, tmp_path, test_bucket, s3fs):
        uri = f"s3://{test_bucket}/sat/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri], limit=1)
        jm = SolverJobManager(jobs_path)
        count = jm.prepare_jobs(s3fs, "sat")
        assert count == 1


@requires_aws
class TestS3SmtFormulas:
    """Test prepare_jobs with S3 URIs and solver_type=smt."""

    def test_finds_smt2_files_on_s3(self, tmp_path, test_bucket, s3fs):
        uri = f"s3://{test_bucket}/smt/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri])
        jm = SolverJobManager(jobs_path)
        count = jm.prepare_jobs(s3fs, "smt")
        assert count > 0
        assert all(j.endswith(".smt2") for j in jm.jobs)

    def test_sat_type_filters_out_smt2_on_s3(self, tmp_path, test_bucket, s3fs):
        uri = f"s3://{test_bucket}/smt/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri])
        jm = SolverJobManager(jobs_path)
        count = jm.prepare_jobs(s3fs, "sat")
        assert count == 0


@requires_aws
class TestS3MultipleDirs:
    """Test prepare_jobs with multiple S3 directories."""

    def test_combines_multiple_s3_dirs(self, tmp_path, test_bucket, s3fs):
        uri = f"s3://{test_bucket}/sat/easy"
        jobs_path = _write_jobs_yaml(tmp_path, [uri, uri])
        jm = SolverJobManager(jobs_path)
        count = jm.prepare_jobs(s3fs, "sat")
        # Same dir listed twice should double the results
        single_dir = tmp_path / "single"
        single_dir.mkdir()
        single_path = _write_jobs_yaml(single_dir, [uri])
        jm2 = SolverJobManager(single_path)
        single_count = jm2.prepare_jobs(s3fs, "sat")
        assert count == single_count * 2


# ---------------------------------------------------------------------------
# Test-local specific fields (no AWS needed)
# ---------------------------------------------------------------------------

def _write_jobs_yaml_with_test_local(tmp_path: Path, formulas: List[str],
                                      formula_dir_test_local=None,
                                      expected_file_test_local=None,
                                      results_dir: str = "results") -> str:
    """Write a jobs YAML with test-local fields and return its path."""
    config = {
        "results_dir": results_dir,
        "formulas": formulas,
        "limit": None,
        "job_options": {
            "timeout_secs": 10,
            "solver_options": [],
        },
    }
    if formula_dir_test_local is not None:
        config["formula_dir_test_local"] = formula_dir_test_local
    if expected_file_test_local is not None:
        config["expected_file_test_local"] = expected_file_test_local

    path = tmp_path / "jobs.yml"
    path.write_text(yaml.dump(config))
    return str(path)


class TestFormulaDirTestLocal:
    """Tests for formula_dir_test_local field in jobs.yml."""

    def test_formula_dir_test_local_not_set(self, tmp_path):
        """Test that formula_dir_test_local returns None when not set."""
        jobs_path = _write_jobs_yaml(tmp_path, [])
        jm = SolverJobManager(jobs_path)
        assert jm.formula_dir_test_local is None

    def test_formula_dir_test_local_absolute_path(self, tmp_path):
        """Test formula_dir_test_local with absolute path."""
        custom_dir = tmp_path / "custom_formulas"
        custom_dir.mkdir()

        jobs_path = _write_jobs_yaml_with_test_local(
            tmp_path, [],
            formula_dir_test_local=str(custom_dir)
        )
        jm = SolverJobManager(jobs_path)
        assert jm.formula_dir_test_local == custom_dir

    def test_formula_dir_test_local_relative_path(self, tmp_path):
        """Test formula_dir_test_local with relative path (resolved relative to jobs.yml)."""
        custom_dir = tmp_path / "custom_formulas"
        custom_dir.mkdir()

        jobs_path = _write_jobs_yaml_with_test_local(
            tmp_path, [],
            formula_dir_test_local="custom_formulas"
        )
        jm = SolverJobManager(jobs_path)
        assert jm.formula_dir_test_local == custom_dir


class TestExpectedFileTestLocal:
    """Tests for expected_file_test_local field in jobs.yml."""

    def test_expected_file_test_local_not_set(self, tmp_path):
        """Test that expected_file_test_local returns None when not set."""
        jobs_path = _write_jobs_yaml(tmp_path, [])
        jm = SolverJobManager(jobs_path)
        assert jm.expected_file_test_local is None

    def test_expected_file_test_local_absolute_path(self, tmp_path):
        """Test expected_file_test_local with absolute path."""
        expected_file = tmp_path / "my_expected.yml"
        expected_file.touch()

        jobs_path = _write_jobs_yaml_with_test_local(
            tmp_path, [],
            expected_file_test_local=str(expected_file)
        )
        jm = SolverJobManager(jobs_path)
        assert jm.expected_file_test_local == expected_file

    def test_expected_file_test_local_relative_path(self, tmp_path):
        """Test expected_file_test_local with relative path (resolved relative to jobs.yml)."""
        expected_file = tmp_path / "my_expected.yml"
        expected_file.touch()

        jobs_path = _write_jobs_yaml_with_test_local(
            tmp_path, [],
            expected_file_test_local="my_expected.yml"
        )
        jm = SolverJobManager(jobs_path)
        assert jm.expected_file_test_local == expected_file

    def test_both_fields_set(self, tmp_path):
        """Test that both formula_dir_test_local and expected_file_test_local can be set."""
        custom_dir = tmp_path / "custom_formulas"
        custom_dir.mkdir()
        expected_file = tmp_path / "my_expected.yml"
        expected_file.touch()

        jobs_path = _write_jobs_yaml_with_test_local(
            tmp_path, [],
            formula_dir_test_local=str(custom_dir),
            expected_file_test_local=str(expected_file)
        )
        jm = SolverJobManager(jobs_path)
        assert jm.formula_dir_test_local == custom_dir
        assert jm.expected_file_test_local == expected_file
