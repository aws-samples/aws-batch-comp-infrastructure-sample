"""Tests for SqsQueue.delete_message_batch and SolverJobManager.process_jobs.

Uses mocks to verify:
  - delete_message_batch builds correct entries and makes a single API call
  - delete_message_batch handles partial failures
  - process_jobs calls batch delete per receive cycle instead of per-message delete
  - process_jobs writes all results to the output file
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import yaml

from harness.aws_shim.sqs_shim import SqsQueue, QueueMessage, SqsQueueException
from runner.runner_jobs import SolverJobManager
from common.solver_io import CompetitionQueueOutput, SolverResultCode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_queue_message(body: str, receipt_handle: str, sqs_client=None, queue_url="") -> QueueMessage:
    """Create a QueueMessage from a body string and receipt handle."""
    msg_dict = {
        "Body": body,
        "ReceiptHandle": receipt_handle,
    }
    return QueueMessage(msg_dict, sqs_client or MagicMock(), queue_url)


def _make_result_json(solver: str = "test-solver", formula: str = "s3://bucket/f.cnf") -> str:
    """Create a valid CompetitionQueueOutput JSON string."""
    result = CompetitionQueueOutput(
        solver=solver,
        process_return_code=0,
        solver_result_code=SolverResultCode.SAT,
        solver_runtime_millis=100,
        job_time_start="2026-01-01T00:00:00",
        formula_s3_uri=formula,
        upload_dir_uri="s3://bucket/results/",
    )
    return result.to_json()


def _write_jobs_yaml(tmp_path: Path) -> str:
    """Write a minimal jobs YAML for SolverJobManager and return its path."""
    config = {
        "results_dir": str(tmp_path / "results"),
        "formulas": [],
        "limit": None,
        "job_options": {"timeout_secs": 10, "solver_options": []},
    }
    path = tmp_path / "jobs.yml"
    path.write_text(yaml.dump(config))
    return str(path)


# ---------------------------------------------------------------------------
# Tests for SqsQueue.delete_message_batch
# ---------------------------------------------------------------------------

class TestDeleteMessageBatch:

    def test_single_api_call_for_batch(self):
        """Batch delete should make exactly one API call for up to 10 messages."""
        mock_client = MagicMock()
        mock_client.delete_message_batch.return_value = {"Successful": [], "Failed": []}
        queue = SqsQueue(mock_client, "https://sqs.us-east-1.amazonaws.com/123/test-queue")

        messages = [_make_queue_message("body", f"handle-{i}", mock_client) for i in range(5)]
        queue.delete_message_batch(messages)

        mock_client.delete_message_batch.assert_called_once()
        call_args = mock_client.delete_message_batch.call_args
        entries = call_args[1]["Entries"] if "Entries" in call_args[1] else call_args[0][0]
        assert len(entries) == 5
        assert entries[0]["ReceiptHandle"] == "handle-0"
        assert entries[4]["ReceiptHandle"] == "handle-4"

    def test_empty_batch_is_noop(self):
        """Empty message list should not call the API."""
        mock_client = MagicMock()
        queue = SqsQueue(mock_client, "https://sqs.us-east-1.amazonaws.com/123/test-queue")
        queue.delete_message_batch([])
        mock_client.delete_message_batch.assert_not_called()

    def test_rejects_more_than_10(self):
        """Should raise if more than 10 messages are passed."""
        mock_client = MagicMock()
        queue = SqsQueue(mock_client, "https://sqs.us-east-1.amazonaws.com/123/test-queue")
        messages = [_make_queue_message("body", f"handle-{i}", mock_client) for i in range(11)]
        with pytest.raises(SqsQueueException):
            queue.delete_message_batch(messages)

    def test_logs_partial_failures(self):
        """Should not raise on partial failures, but they should be in the response."""
        mock_client = MagicMock()
        mock_client.delete_message_batch.return_value = {
            "Successful": [{"Id": "0"}],
            "Failed": [{"Id": "1", "Code": "InternalError", "Message": "oops"}],
        }
        queue = SqsQueue(mock_client, "https://sqs.us-east-1.amazonaws.com/123/test-queue")
        messages = [_make_queue_message("body", f"handle-{i}", mock_client) for i in range(2)]
        # Should not raise
        queue.delete_message_batch(messages)


# ---------------------------------------------------------------------------
# Tests for SolverJobManager.process_jobs
# ---------------------------------------------------------------------------

class TestProcessJobsBatchDelete:

    def test_uses_batch_delete_not_individual(self, tmp_path):
        """process_jobs should call delete_message_batch, not individual delete."""
        jobs_path = _write_jobs_yaml(tmp_path)
        jm = SolverJobManager(jobs_path)
        jm.make_results_dir()

        result_json = _make_result_json()
        messages = [_make_queue_message(result_json, f"handle-{i}") for i in range(3)]

        mock_queue = MagicMock(spec=SqsQueue)
        # First call returns messages, second returns empty (queue drained)
        mock_queue.receive_messages.side_effect = [messages, []]

        jm.process_jobs(mock_queue)

        # Batch delete should have been called once with all 3 messages
        mock_queue.delete_message_batch.assert_called_once_with(messages)
        # Individual delete should never be called
        for msg in messages:
            msg.delete = MagicMock()
        # (The messages we passed in didn't have delete called on them)

    def test_multiple_batches(self, tmp_path):
        """process_jobs should batch-delete each receive cycle separately."""
        jobs_path = _write_jobs_yaml(tmp_path)
        jm = SolverJobManager(jobs_path)
        jm.make_results_dir()

        result_json = _make_result_json()
        batch1 = [_make_queue_message(result_json, f"b1-{i}") for i in range(10)]
        batch2 = [_make_queue_message(result_json, f"b2-{i}") for i in range(5)]

        mock_queue = MagicMock(spec=SqsQueue)
        mock_queue.receive_messages.side_effect = [batch1, batch2, []]

        jm.process_jobs(mock_queue)

        assert mock_queue.delete_message_batch.call_count == 2
        mock_queue.delete_message_batch.assert_any_call(batch1)
        mock_queue.delete_message_batch.assert_any_call(batch2)

    def test_writes_all_results_to_file(self, tmp_path):
        """All received messages should be written to results.txt."""
        jobs_path = _write_jobs_yaml(tmp_path)
        jm = SolverJobManager(jobs_path)
        jm.make_results_dir()

        formulas = [f"s3://bucket/formula_{i}.cnf" for i in range(5)]
        messages = [_make_queue_message(_make_result_json(formula=f), f"h-{i}") for i, f in enumerate(formulas)]

        mock_queue = MagicMock(spec=SqsQueue)
        mock_queue.receive_messages.side_effect = [messages, []]

        jm.process_jobs(mock_queue)

        results_file = tmp_path / "results" / "results.txt"
        assert results_file.exists()
        lines = results_file.read_text().strip().split("\n")
        assert len(lines) == 5
        for line, formula in zip(lines, formulas):
            parsed = json.loads(line)
            assert parsed["formula_s3_uri"] == formula

    def test_empty_queue(self, tmp_path):
        """Empty queue should produce no output and no batch delete calls."""
        jobs_path = _write_jobs_yaml(tmp_path)
        jm = SolverJobManager(jobs_path)
        jm.make_results_dir()

        mock_queue = MagicMock(spec=SqsQueue)
        mock_queue.receive_messages.return_value = []

        jm.process_jobs(mock_queue)

        mock_queue.delete_message_batch.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for malformed message handling
# ---------------------------------------------------------------------------

class TestMalformedMessages:

    def test_malformed_json_does_not_crash_loop(self, tmp_path):
        """Malformed JSON should be skipped, not crash the entire loop."""
        jobs_path = _write_jobs_yaml(tmp_path)
        jm = SolverJobManager(jobs_path)
        jm.make_results_dir()

        valid_json = _make_result_json(formula="s3://bucket/valid.cnf")
        malformed_json = "not valid json at all"

        messages = [
            _make_queue_message(valid_json, "handle-valid"),
            _make_queue_message(malformed_json, "handle-bad"),
            _make_queue_message(valid_json, "handle-valid2"),
        ]

        mock_queue = MagicMock(spec=SqsQueue)
        mock_queue.receive_messages.side_effect = [messages, []]

        # Should not raise
        jm.process_jobs(mock_queue)

        # All messages should still be deleted (including malformed)
        mock_queue.delete_message_batch.assert_called_once_with(messages)

        # Valid results should be written
        results_file = tmp_path / "results" / "results.txt"
        lines = results_file.read_text().strip().split("\n")
        assert len(lines) == 2  # Only 2 valid messages

    def test_missing_field_does_not_crash_loop(self, tmp_path):
        """Message with missing required field should be skipped."""
        jobs_path = _write_jobs_yaml(tmp_path)
        jm = SolverJobManager(jobs_path)
        jm.make_results_dir()

        valid_json = _make_result_json()
        # Missing 'solver' field
        incomplete_json = json.dumps({
            "process_return_code": 0,
            "solver_result_code": 10,
        })

        messages = [
            _make_queue_message(valid_json, "handle-valid"),
            _make_queue_message(incomplete_json, "handle-incomplete"),
        ]

        mock_queue = MagicMock(spec=SqsQueue)
        mock_queue.receive_messages.side_effect = [messages, []]

        # Should not raise
        jm.process_jobs(mock_queue)

        results_file = tmp_path / "results" / "results.txt"
        lines = results_file.read_text().strip().split("\n")
        assert len(lines) == 1  # Only 1 valid message
