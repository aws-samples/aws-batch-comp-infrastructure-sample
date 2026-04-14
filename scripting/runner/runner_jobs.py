"""Manages the creation and processing of solver jobs."""

import logging
import os
from pathlib import Path
from typing import List, Optional

import common.pathing as pathing
import yaml
from common import CompetitionQueueOutput, LoggingManager
from common.constants import SAT_FORMULA_EXTENSION, SMT_FORMULA_EXTENSION
from harness.aws_shim import S3FileSystem, SqsQueue
from utils import SolverRequester

################################################################################

lm = LoggingManager()
logger = lm.get_logger("runner_jobs", formatted=False)


class SolverJobManager:
    def __init__(self, config_file_path: str):
        with open(config_file_path, "r") as f:
            self.config: dict = yaml.safe_load(f)

        self.config_file_path = pathing.normalize_path(config_file_path)
        self.config_dir = self.config_file_path.parent
        self.results_dir = pathing.normalize_path(self.config["results_dir"])
        self.jobs: List[str] = []
        self.limit = self.config.get("limit")
        if self.limit is not None and self.limit <= 0:
            logger.error(f"Error: The `limit` field must be positive (was {self.limit})")

    @property
    def formula_dir_test_local(self) -> Optional[Path]:
        """Get the local formula directory for test-local command.

        Returns the formula_dir_test_local value from jobs.yml, resolved
        relative to the jobs.yml file location.
        """
        formula_dir = self.config.get("formula_dir_test_local")
        if formula_dir is None:
            return None
        return pathing.normalize_path(formula_dir, relative_to=self.config_dir)

    @property
    def expected_file_test_local(self) -> Optional[Path]:
        """Get the explicit expected.yml path for test-local command.

        Returns the expected_file_test_local value from jobs.yml, resolved
        relative to the jobs.yml file location. Returns None if not set.
        """
        expected_file = self.config.get("expected_file_test_local")
        if expected_file is None:
            return None
        return pathing.normalize_path(expected_file, relative_to=self.config_dir)

    def make_results_dir(self) -> None:
        self.results_dir.mkdir(mode=0o755, exist_ok=True)

    def prepare_jobs(self, s3: S3FileSystem, solver_type: str) -> int:
        """
        Builds the list of formula S3 URIs to submit as jobs. Stores them in `self.jobs`.

        Each entry in `formulas` must be an S3 URI (starting with "s3://").
        Directories are listed recursively and only files matching the solver
        type extension are kept: '.cnf' for SAT, '.smt2' for SMT.

        Returns the number of files found.
        """
        ext = SAT_FORMULA_EXTENSION if solver_type == "sat" else SMT_FORMULA_EXTENSION
        self.jobs = []
        for location in self.config["formulas"]:
            if not location.startswith("s3://"):
                logger.error(f'Error: Formula path "{location}" must be an S3 URI (s3://...)')
                logger.error("Upload local files to S3 first, e.g. with `aws s3 sync`.")
                exit(1)
            bucket, prefix = pathing.split_s3_uri(location)
            found = s3.ls(bucket, prefix, recursive=True, style=S3FileSystem.UriStyle.FULL_URI)
            self.jobs += [f for f in found if f.endswith(ext)]

        if self.limit is not None:
            self.jobs = self.jobs[: self.limit]

        return len(self.jobs)

    def submit_jobs(self, solver: str, queue: SqsQueue):
        logger.info(f"Submitting jobs for solver {solver}")

        # Return early if there are no jobs to submit
        if len(self.jobs) == 0:
            logger.info("There are no jobs to submit.")
            logger.info("Check that your formula directories contain matching files.")
            return

        # Parse solver and runtime options for this round of jobs
        job_opts = self.config["job_options"]
        self.timeout_secs = int(job_opts["timeout_secs"])
        self.solver_options = job_opts["solver_options"]
        if not isinstance(self.solver_options, list):
            logger.error("The solver options must be a list of individual string tokens.")
            logger.error("If you passed a string, please wrap in `[]` and try again.")
            exit(1)

        # Create a requester with these base options
        requester = SolverRequester(solver, self.solver_options, self.timeout_secs, num_workers=0)

        # Send the messages!
        lvl = queue.logger.getEffectiveLevel()
        queue.logger.setLevel(logging.WARNING)
        messages = [requester.make_request(j).to_json() for j in self.jobs]
        queue.send_messages(messages, display_progress_bar=True)
        queue.logger.setLevel(lvl)

    def process_jobs(self, queue: SqsQueue, wait_time_secs: int = 1) -> None:
        """
        Pull results from the output queue and store them in the `results` directory.

        Once the queue is empty, reports the number of messages read, and returns.

        Note: If SQS message deletion fails (see delete_message_batch), messages may be
        redelivered and processed again, causing duplicate entries in results.txt.
        TODO: Implement deduplication by tracking processed message IDs or formula URIs.
        """

        results_file_path = os.path.join(self.results_dir, "results.txt")
        with open(results_file_path, "a") as f:
            total_messages_read = 0
            malformed_count = 0
            messages = queue.receive_messages(10, wait_time_secs)
            while len(messages) > 0:
                total_messages_read += len(messages)
                logger.info(
                    f"Read {len(messages)} messages from the output queue (total so far: {total_messages_read})"
                )
                for message in messages:
                    body_str = message.read()
                    try:
                        result = CompetitionQueueOutput.from_json(body_str)
                        f.write(result.to_json() + "\n")
                    except (KeyError, ValueError, TypeError) as e:
                        malformed_count += 1
                        logger.warning(f"Skipping malformed message: {e}")
                        logger.debug(f"Malformed message body: {body_str[:200]}")
                queue.delete_message_batch(messages)
                messages = queue.receive_messages(10, wait_time_secs)

        logger.info(f"Output queue was empty, read {total_messages_read} total messages")
        if malformed_count > 0:
            logger.warning(f"Skipped {malformed_count} malformed messages")
