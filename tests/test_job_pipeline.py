"""End-to-end tests for the job submission and processing pipeline.

Tests cover:
  - SolverJobManager initialization and configuration parsing
  - prepare_jobs with mocked S3
  - submit_jobs with local SQS queues
  - process_jobs with local SQS queues
  - Full submit → process flow with result verification

Uses moto for S3 mocking and built-in LocalSqsQueue for SQS.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import moto
import pytest
import yaml

from harness.aws_shim import SqsQueue, S3FileSystem
from harness.aws_shim.sqs_shim import LocalSqsQueue
from runner.runner_jobs import SolverJobManager
from common import CompetitionQueueOutput, SolverResultCode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def jobs_config_file(tmp_path):
    """Create a minimal jobs.yml config file."""
    config = {
        "results_dir": str(tmp_path / "results"),
        "formulas": ["s3://test-bucket/formulas/"],
        "job_options": {
            "timeout_secs": 60,
            "solver_options": ["--verbose"],
        },
    }
    config_path = tmp_path / "jobs.yml"
    config_path.write_text(yaml.dump(config))
    return config_path


@pytest.fixture
def jobs_config_with_limit(tmp_path):
    """Create a jobs.yml with a limit."""
    config = {
        "results_dir": str(tmp_path / "results"),
        "formulas": ["s3://test-bucket/formulas/"],
        "limit": 5,
        "job_options": {
            "timeout_secs": 30,
            "solver_options": [],
        },
    }
    config_path = tmp_path / "jobs.yml"
    config_path.write_text(yaml.dump(config))
    return config_path


@pytest.fixture
def local_input_queue():
    """Create a local SQS queue for input jobs."""
    return SqsQueue.get_local_sqs_queue("test-input-queue")


@pytest.fixture
def local_output_queue():
    """Create a local SQS queue for output results."""
    return SqsQueue.get_local_sqs_queue("test-output-queue")


@pytest.fixture
def sample_output_message():
    """Create a sample CompetitionQueueOutput message."""
    return CompetitionQueueOutput(
        solver="test-solver",
        process_return_code=0,
        solver_result_code=SolverResultCode.SAT,
        solver_runtime_millis=1234,
        job_time_start="2025-01-01T00:00:00Z",
        formula_s3_uri="s3://test-bucket/formulas/test.cnf",
        upload_dir_uri="s3://test-bucket/results/test/",
    )


# ---------------------------------------------------------------------------
# SolverJobManager initialization tests
# ---------------------------------------------------------------------------

class TestSolverJobManagerInit:
    """Test SolverJobManager initialization."""

    def test_init_success(self, jobs_config_file):
        """Test successful initialization."""
        manager = SolverJobManager(str(jobs_config_file))
        assert manager.results_dir is not None
        assert manager.jobs == []

    def test_init_parses_results_dir(self, jobs_config_file, tmp_path):
        """Test that results_dir is parsed correctly."""
        manager = SolverJobManager(str(jobs_config_file))
        expected_dir = tmp_path / "results"
        assert manager.results_dir == expected_dir

    def test_init_with_limit(self, jobs_config_with_limit):
        """Test initialization with limit field."""
        manager = SolverJobManager(str(jobs_config_with_limit))
        assert manager.limit == 5

    def test_init_without_limit(self, jobs_config_file):
        """Test initialization without limit field."""
        manager = SolverJobManager(str(jobs_config_file))
        assert manager.limit is None

    def test_init_zero_limit_logs_error(self, tmp_path, caplog):
        """Test that zero limit logs an error."""
        config = {
            "results_dir": str(tmp_path / "results"),
            "formulas": [],
            "limit": 0,
            "job_options": {"timeout_secs": 10, "solver_options": []},
        }
        config_path = tmp_path / "jobs.yml"
        config_path.write_text(yaml.dump(config))

        manager = SolverJobManager(str(config_path))
        assert "must be positive" in caplog.text.lower() or manager.limit == 0

    def test_make_results_dir(self, jobs_config_file, tmp_path):
        """Test that make_results_dir creates the directory."""
        manager = SolverJobManager(str(jobs_config_file))
        manager.make_results_dir()
        assert (tmp_path / "results").exists()


# ---------------------------------------------------------------------------
# prepare_jobs tests with mocked S3
# ---------------------------------------------------------------------------

@moto.mock_aws
class TestPrepareJobs:
    """Test prepare_jobs with mocked S3."""

    def _setup_s3_bucket(self, bucket_name, files):
        """Helper to create an S3 bucket with test files."""
        conn = boto3.resource("s3", region_name="us-east-1")
        conn.create_bucket(Bucket=bucket_name)
        for key in files:
            conn.Object(bucket_name, key).put(Body=b"test content")

    def test_prepare_jobs_finds_cnf_files(self, jobs_config_file):
        """Test that prepare_jobs finds .cnf files for SAT."""
        self._setup_s3_bucket("test-bucket", [
            "formulas/test1.cnf",
            "formulas/test2.cnf",
            "formulas/test3.smt2",
        ])

        s3 = S3FileSystem(boto3.client("s3", region_name="us-east-1"))
        manager = SolverJobManager(str(jobs_config_file))
        count = manager.prepare_jobs(s3, "sat")

        assert count == 2
        assert all(j.endswith(".cnf") for j in manager.jobs)

    def test_prepare_jobs_finds_smt2_files(self, jobs_config_file):
        """Test that prepare_jobs finds .smt2 files for SMT."""
        self._setup_s3_bucket("test-bucket", [
            "formulas/test1.cnf",
            "formulas/test2.smt2",
            "formulas/test3.smt2",
        ])

        s3 = S3FileSystem(boto3.client("s3", region_name="us-east-1"))
        manager = SolverJobManager(str(jobs_config_file))
        count = manager.prepare_jobs(s3, "smt")

        assert count == 2
        assert all(j.endswith(".smt2") for j in manager.jobs)

    def test_prepare_jobs_respects_limit(self, jobs_config_with_limit):
        """Test that prepare_jobs respects the limit field."""
        self._setup_s3_bucket("test-bucket", [
            f"formulas/test{i}.cnf" for i in range(20)
        ])

        s3 = S3FileSystem(boto3.client("s3", region_name="us-east-1"))
        manager = SolverJobManager(str(jobs_config_with_limit))
        count = manager.prepare_jobs(s3, "sat")

        assert count == 5
        assert len(manager.jobs) == 5

    def test_prepare_jobs_recursive_search(self, tmp_path):
        """Test that prepare_jobs searches recursively in subdirectories."""
        config = {
            "results_dir": str(tmp_path / "results"),
            "formulas": ["s3://test-bucket/formulas/"],
            "job_options": {"timeout_secs": 10, "solver_options": []},
        }
        config_path = tmp_path / "jobs.yml"
        config_path.write_text(yaml.dump(config))

        # Create files in nested directories under formulas/
        self._setup_s3_bucket("test-bucket", [
            "formulas/level1/test1.cnf",
            "formulas/level1/level2/test2.cnf",
            "formulas/level1/level2/level3/test3.cnf",
        ])

        s3 = S3FileSystem(boto3.client("s3", region_name="us-east-1"))
        manager = SolverJobManager(str(config_path))
        count = manager.prepare_jobs(s3, "sat")

        assert count == 3

    def test_prepare_jobs_empty_bucket(self, jobs_config_file):
        """Test prepare_jobs with empty bucket."""
        self._setup_s3_bucket("test-bucket", [])

        s3 = S3FileSystem(boto3.client("s3", region_name="us-east-1"))
        manager = SolverJobManager(str(jobs_config_file))
        count = manager.prepare_jobs(s3, "sat")

        assert count == 0
        assert manager.jobs == []

    def test_prepare_jobs_returns_full_uris(self, jobs_config_file):
        """Test that prepare_jobs returns full S3 URIs."""
        self._setup_s3_bucket("test-bucket", ["formulas/test.cnf"])

        s3 = S3FileSystem(boto3.client("s3", region_name="us-east-1"))
        manager = SolverJobManager(str(jobs_config_file))
        manager.prepare_jobs(s3, "sat")

        assert len(manager.jobs) == 1
        assert manager.jobs[0].startswith("s3://")


# ---------------------------------------------------------------------------
# submit_jobs tests
# ---------------------------------------------------------------------------

class TestSubmitJobs:
    """Test submit_jobs with local SQS queue."""

    def test_submit_jobs_empty_list(self, jobs_config_file, local_input_queue, caplog):
        """Test submit_jobs with no jobs."""
        manager = SolverJobManager(str(jobs_config_file))
        manager.jobs = []
        manager.submit_jobs("test-solver", local_input_queue)

        assert "no jobs to submit" in caplog.text.lower()

    def test_submit_jobs_single_job(self, jobs_config_file, local_input_queue):
        """Test submit_jobs with a single job."""
        manager = SolverJobManager(str(jobs_config_file))
        manager.jobs = ["s3://bucket/test.cnf"]
        manager.submit_jobs("test-solver", local_input_queue)

        assert local_input_queue.len() == 1

    def test_submit_jobs_multiple_jobs(self, jobs_config_file, local_input_queue):
        """Test submit_jobs with multiple jobs."""
        manager = SolverJobManager(str(jobs_config_file))
        manager.jobs = [f"s3://bucket/test{i}.cnf" for i in range(10)]
        manager.submit_jobs("test-solver", local_input_queue)

        assert local_input_queue.len() == 10

    def test_submit_jobs_message_format(self, jobs_config_file, local_input_queue):
        """Test that submitted messages have correct format."""
        manager = SolverJobManager(str(jobs_config_file))
        manager.jobs = ["s3://bucket/test.cnf"]
        manager.submit_jobs("test-solver", local_input_queue)

        msg = local_input_queue.receive_message(wait_time_secs=0)
        body = json.loads(msg.read())

        # Message format is nested per SolverQueueInput.to_dict()
        assert body["solverConfig"]["solverName"] == "test-solver"
        assert body["formula"]["value"] == "s3://bucket/test.cnf"
        assert body["solverConfig"]["taskTimeoutSeconds"] == 60  # From jobs_config_file
        assert body["solverConfig"]["solverOptions"] == ["--verbose"]

    def test_submit_jobs_uses_timeout_from_config(self, jobs_config_with_limit, local_input_queue):
        """Test that timeout comes from config."""
        manager = SolverJobManager(str(jobs_config_with_limit))
        manager.jobs = ["s3://bucket/test.cnf"]
        manager.submit_jobs("test-solver", local_input_queue)

        msg = local_input_queue.receive_message(wait_time_secs=0)
        body = json.loads(msg.read())

        assert body["solverConfig"]["taskTimeoutSeconds"] == 30  # From jobs_config_with_limit


# ---------------------------------------------------------------------------
# process_jobs tests
# ---------------------------------------------------------------------------

class TestProcessJobs:
    """Test process_jobs with local SQS queue."""

    def test_process_jobs_empty_queue(self, jobs_config_file, local_output_queue, tmp_path):
        """Test process_jobs with empty queue."""
        manager = SolverJobManager(str(jobs_config_file))
        manager.make_results_dir()
        manager.process_jobs(local_output_queue, wait_time_secs=0)

        results_file = tmp_path / "results" / "results.txt"
        assert results_file.exists()
        assert results_file.read_text() == ""

    def test_process_jobs_single_message(
        self, jobs_config_file, local_output_queue, sample_output_message, tmp_path
    ):
        """Test process_jobs with a single message."""
        # Put message on queue
        local_output_queue.put_message(sample_output_message.to_json())

        manager = SolverJobManager(str(jobs_config_file))
        manager.make_results_dir()
        manager.process_jobs(local_output_queue, wait_time_secs=0)

        results_file = tmp_path / "results" / "results.txt"
        content = results_file.read_text()
        assert "test-solver" in content
        assert "s3://test-bucket/formulas/test.cnf" in content

    def test_process_jobs_multiple_messages(
        self, jobs_config_file, local_output_queue, tmp_path
    ):
        """Test process_jobs with multiple messages."""
        for i in range(5):
            msg = CompetitionQueueOutput(
                solver=f"solver-{i}",
                process_return_code=0,
                solver_result_code=SolverResultCode.SAT,
                solver_runtime_millis=1000 + i,
                job_time_start=f"2025-01-0{i+1}T00:00:00Z",
                formula_s3_uri=f"s3://bucket/test{i}.cnf",
                upload_dir_uri=f"s3://bucket/results/{i}/",
            )
            local_output_queue.put_message(msg.to_json())

        manager = SolverJobManager(str(jobs_config_file))
        manager.make_results_dir()
        manager.process_jobs(local_output_queue, wait_time_secs=0)

        results_file = tmp_path / "results" / "results.txt"
        lines = results_file.read_text().strip().split("\n")
        assert len(lines) == 5

    def test_process_jobs_malformed_message_skipped(
        self, jobs_config_file, local_output_queue, sample_output_message, tmp_path, caplog
    ):
        """Test that malformed messages are skipped."""
        # Put a malformed message
        local_output_queue.put_message('{"invalid": "message"}')
        # Put a valid message
        local_output_queue.put_message(sample_output_message.to_json())

        manager = SolverJobManager(str(jobs_config_file))
        manager.make_results_dir()
        manager.process_jobs(local_output_queue, wait_time_secs=0)

        results_file = tmp_path / "results" / "results.txt"
        lines = results_file.read_text().strip().split("\n")
        # Only the valid message should be written
        assert len(lines) == 1
        assert "malformed" in caplog.text.lower()

    def test_process_jobs_deletes_messages(
        self, jobs_config_file, local_output_queue, sample_output_message, tmp_path
    ):
        """Test that processed messages are deleted from queue."""
        local_output_queue.put_message(sample_output_message.to_json())
        assert local_output_queue.len() == 1

        manager = SolverJobManager(str(jobs_config_file))
        manager.make_results_dir()
        manager.process_jobs(local_output_queue, wait_time_secs=0)

        # Queue should be empty after processing
        assert local_output_queue.len() == 0


# ---------------------------------------------------------------------------
# End-to-end pipeline tests
# ---------------------------------------------------------------------------

@moto.mock_aws
class TestEndToEndPipeline:
    """Test the full job submission and processing pipeline."""

    def _setup_s3_with_formulas(self, bucket_name, formula_count):
        """Helper to set up S3 bucket with test formulas."""
        conn = boto3.resource("s3", region_name="us-east-1")
        conn.create_bucket(Bucket=bucket_name)
        for i in range(formula_count):
            conn.Object(bucket_name, f"formulas/test{i}.cnf").put(Body=b"test content")

    def test_full_pipeline_submit_and_process(self, tmp_path):
        """Test full submit → process flow."""
        # Setup config
        config = {
            "results_dir": str(tmp_path / "results"),
            "formulas": ["s3://test-bucket/formulas/"],
            "job_options": {
                "timeout_secs": 60,
                "solver_options": [],
            },
        }
        config_path = tmp_path / "jobs.yml"
        config_path.write_text(yaml.dump(config))

        # Setup S3
        self._setup_s3_with_formulas("test-bucket", 3)

        # Setup queues
        input_queue = SqsQueue.get_local_sqs_queue("input")
        output_queue = SqsQueue.get_local_sqs_queue("output")

        # Phase 1: Prepare and submit jobs
        s3 = S3FileSystem(boto3.client("s3", region_name="us-east-1"))
        manager = SolverJobManager(str(config_path))
        manager.make_results_dir()
        count = manager.prepare_jobs(s3, "sat")
        assert count == 3

        manager.submit_jobs("my-solver", input_queue)
        assert input_queue.len() == 3

        # Phase 2: Simulate solver processing (read from input, write to output)
        for _ in range(3):
            msg = input_queue.receive_message(wait_time_secs=0)
            input_data = json.loads(msg.read())

            # Create output message (input format is nested per SolverQueueInput)
            output = CompetitionQueueOutput(
                solver=input_data["solverConfig"]["solverName"],
                process_return_code=0,
                solver_result_code=SolverResultCode.SAT,
                solver_runtime_millis=500,
                job_time_start="2025-01-01T00:00:00Z",
                formula_s3_uri=input_data["formula"]["value"],
                upload_dir_uri="s3://test-bucket/results/",
            )
            output_queue.put_message(output.to_json())
            msg.delete()

        assert input_queue.len() == 0
        assert output_queue.len() == 3

        # Phase 3: Process results
        manager.process_jobs(output_queue, wait_time_secs=0)

        # Verify results
        results_file = tmp_path / "results" / "results.txt"
        assert results_file.exists()
        lines = results_file.read_text().strip().split("\n")
        assert len(lines) == 3

        # Verify each result has expected format
        for line in lines:
            result = json.loads(line)
            assert result["solver"] == "my-solver"
            assert result["process_return_code"] == 0
            assert "formula_s3_uri" in result

    def test_pipeline_with_limit(self, tmp_path):
        """Test pipeline respects job limit."""
        config = {
            "results_dir": str(tmp_path / "results"),
            "formulas": ["s3://test-bucket/formulas/"],
            "limit": 2,
            "job_options": {
                "timeout_secs": 10,
                "solver_options": [],
            },
        }
        config_path = tmp_path / "jobs.yml"
        config_path.write_text(yaml.dump(config))

        self._setup_s3_with_formulas("test-bucket", 10)

        s3 = S3FileSystem(boto3.client("s3", region_name="us-east-1"))
        input_queue = SqsQueue.get_local_sqs_queue("input")

        manager = SolverJobManager(str(config_path))
        count = manager.prepare_jobs(s3, "sat")
        manager.submit_jobs("solver", input_queue)

        assert count == 2
        assert input_queue.len() == 2

    def test_pipeline_smt_formulas(self, tmp_path):
        """Test pipeline with SMT formulas."""
        config = {
            "results_dir": str(tmp_path / "results"),
            "formulas": ["s3://test-bucket/formulas/"],
            "job_options": {
                "timeout_secs": 10,
                "solver_options": [],
            },
        }
        config_path = tmp_path / "jobs.yml"
        config_path.write_text(yaml.dump(config))

        # Setup S3 with SMT files
        conn = boto3.resource("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")
        for i in range(3):
            conn.Object("test-bucket", f"formulas/test{i}.smt2").put(Body=b"test")
        # Add some CNF files that should be ignored
        conn.Object("test-bucket", "formulas/ignore.cnf").put(Body=b"test")

        s3 = S3FileSystem(boto3.client("s3", region_name="us-east-1"))
        manager = SolverJobManager(str(config_path))
        count = manager.prepare_jobs(s3, "smt")

        assert count == 3
        assert all(j.endswith(".smt2") for j in manager.jobs)


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestPipelineErrorHandling:
    """Test error handling in the job pipeline."""

    def test_submit_jobs_non_list_solver_options_exits(self, tmp_path, local_input_queue):
        """Test that non-list solver_options causes exit."""
        config = {
            "results_dir": str(tmp_path / "results"),
            "formulas": [],
            "job_options": {
                "timeout_secs": 10,
                "solver_options": "--verbose",  # Should be a list
            },
        }
        config_path = tmp_path / "jobs.yml"
        config_path.write_text(yaml.dump(config))

        manager = SolverJobManager(str(config_path))
        manager.jobs = ["s3://bucket/test.cnf"]

        with pytest.raises(SystemExit):
            manager.submit_jobs("solver", local_input_queue)

    def test_prepare_jobs_local_path_exits(self, tmp_path):
        """Test that local paths in formulas cause exit."""
        config = {
            "results_dir": str(tmp_path / "results"),
            "formulas": ["/local/path/to/formulas"],
            "job_options": {
                "timeout_secs": 10,
                "solver_options": [],
            },
        }
        config_path = tmp_path / "jobs.yml"
        config_path.write_text(yaml.dump(config))

        mock_s3 = MagicMock()
        manager = SolverJobManager(str(config_path))

        with pytest.raises(SystemExit):
            manager.prepare_jobs(mock_s3, "sat")

    def test_process_jobs_creates_results_file(self, jobs_config_file, local_output_queue, tmp_path):
        """Test that process_jobs creates results file even with empty queue."""
        manager = SolverJobManager(str(jobs_config_file))
        manager.make_results_dir()

        results_file = tmp_path / "results" / "results.txt"
        assert not results_file.exists()

        manager.process_jobs(local_output_queue, wait_time_secs=0)

        assert results_file.exists()
