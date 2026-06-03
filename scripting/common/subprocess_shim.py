"""
A shim to spawn a new sub-process and capture its stdout and stderr.
"""

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from common import pathing
from common.json_to_python import JsonToPythonObject
from common.ps_stats import PsStats

################################################################################


class SubprocessShimOutput(JsonToPythonObject):
    """
    A class to represent the output of a `SubprocessShim` call.

    See the documentation for `SubprocessShim.run()` for more information.
    """

    def __init__(
        self, elapsed_time: float, return_code: int, stdout_path: Path | str, stderr_path: Path | str, timed_out: bool
    ):
        self.elapsed_time = elapsed_time
        self.return_code = return_code
        self.stdout_path = pathing.normalize_path(stdout_path)
        self.stderr_path = pathing.normalize_path(stderr_path)
        self.timed_out = timed_out

    def _validate(self):
        if not os.path.exists(self.stdout_path):
            raise ValueError(f"Stdout file at {self.stdout_path} does not exist")
        if not os.path.exists(self.stderr_path):
            raise ValueError(f"Stderr file at {self.stderr_path} does not exist")

    def to_dict(self) -> dict:
        return {
            "elapsed_time": self.elapsed_time,
            "return_code": self.return_code,
            "stdout": str(self.stderr_path),
            "stderr": str(self.stderr_path),
            "timed_out": self.timed_out,
        }

    @staticmethod
    def from_dict(d: dict) -> "SubprocessShimOutput":
        return SubprocessShimOutput(
            return_code=d["return_code"],
            stdout=d.get("stdout", ""),
            stderr=d.get("stderr", ""),
            timed_out=d.get("timed_out", False),
        )


class SubprocessShim:
    """
    A shim to spawn a new sub-process and capture its stdout and stderr.

    Solver sub-processes can crash or misbehave for a variety of reasons.
    So to robustly capture a sub-process (group)'s output, we call
    `subprocess.Popen()` and then pipe the stdout/stderr to specified files.

    To run the solver, call `.run()`.
    """

    TIMEOUT_RETURN_CODE = -100
    SIGTERM_CLEANUP_TIMEOUT_SECS = 10

    def __init__(
        self,
        logger: logging.Logger,
        stdout_path: Path | str | None,
        stderr_path: Path | str | None,
        ps_stats_path: Path | str | None = None,
    ):
        self.logger = logger
        self.stdout_path = pathing.normalize_path(stdout_path) if stdout_path is not None else Path("/dev/null")
        self.stderr_path = pathing.normalize_path(stderr_path) if stderr_path is not None else Path("/dev/null")
        self.ps_stats_path = pathing.normalize_path(ps_stats_path)
        self.error_return = SubprocessShimOutput(0, -1, self.stdout_path, self.stderr_path, False)

    def validate_cmd(self, cmd: List[str]):
        # Previously checked for spaces and trailing backslashes in tokens,
        # but neither caught real bugs — and the return value was ignored anyway.
        # subprocess.Popen with a list handles spaces in arguments correctly by design.
        pass

    def run(self, cmd: List[str], timeout_secs: Optional[int] = None) -> SubprocessShimOutput:
        """
        Starts a new subprocess (group) with the `cmd` token list provided and `wait()`s until timeout.

        If `timeout_secs = None`, then we `wait()` on the subprocess until it is done.
        By default, `timeout_secs = None`.

        The subprocess's stdout/stderr are logged and written to the file
        paths provided at the constructor.

        Returns a `SubprocessShimOutput` object with the following fields:
        ```
          elapsed_time: float,  # Elapsed time in seconds, as recorded by `time.perf_counter()`
          return_code: int,     # The subprocess's return code, or `TIMEOUT_RETURN_CODE`
          stdout_path: str,     # Path to the captured stdout file
          stderr_path: str,     # Path to the captured stderr file
          timed_out: bool,      # `True` if the subprocess timed out
        ```
        """

        # Verify that `cmd` is a list of atomic tokens (i.e., no spaces in any element)
        self.validate_cmd(cmd)

        # Set the environment variable to unbuffer Python (logging) output
        # When we capture the subprocess's output, we want the echo
        # to the logger (which might go to stdout) to register immediately.
        os.environ["PYTHONUNBUFFERED"] = "1"

        # Use line buffering with the stdout and stderr file handles
        # This ensures that if the shim crashes, we record output up to the most recent line
        LINE_BUFFERED = 1

        timed_out = False
        with (
            open(self.stdout_path, "w", buffering=LINE_BUFFERED) as stdout_handle,
            open(self.stderr_path, "w", buffering=LINE_BUFFERED) as stderr_handle,
        ):
            try:
                if timeout_secs is not None:
                    self.logger.info(f"About to run subprocess, with timeout of {timeout_secs} seconds")
                else:
                    self.logger.info(f"About to run subprocess, with no timeout")
                self.logger.info(f"Command we're going to run: {' '.join(cmd)}")

                start_time = time.perf_counter()

                # Run a new process at the file system's root (i.e., `pwd=/`)
                proc = subprocess.Popen(
                    cmd,  # A list of tokens to run (e.g., ["./solver", "--version"])
                    stdout=stdout_handle,  # Pipe stdout to the stdout file
                    stderr=stderr_handle,  # Pipe stderr to the stderr file
                    start_new_session=True,  # Create a new process group, to propagate SIGTERM and SIGKILL
                    text=True,  # The input and output is text (TODO: what encoding? UTF-8?)
                    bufsize=LINE_BUFFERED,  # Use line buffering for the stdout/stderr writing
                    env=os.environ.copy(),  # Pass environment variables (to disable buffering)
                )

                # Track system statistics, only if requested
                ps_stats = None
                if self.ps_stats_path is not None:
                    ps_stats = PsStats(proc.pid, also_write_to=self.ps_stats_path, should_log=False)
                    ps_stats.start()

                # Wait on the solver until the timeout has passed
                # `threading` will raise an exception if we time out
                # If `timeout_secs = None`, then we block here until done
                return_code = proc.wait(timeout_secs)
                end_time = time.perf_counter()
                if timeout_secs is None:
                    elapsed = end_time - start_time
                else:
                    # Just in case the extra time on either side makes wall clock exceed `timeout_secs`
                    elapsed = min(end_time - start_time, timeout_secs)
            except subprocess.TimeoutExpired:
                timed_out = True
                elapsed = timeout_secs
                self.logger.info("Timeout expired for process. Terminating process group with SIGTERM")

                # Try letting the subprocess clean up its own resources
                # If cleanup takes longer than 10 seconds, kill it
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                try:
                    return_code = proc.wait(SubprocessShim.SIGTERM_CLEANUP_TIMEOUT_SECS)
                except subprocess.TimeoutExpired:
                    self.logger.info("Process unresponsive. Terminating process group with SIGKILL")
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    return_code = SubprocessShim.TIMEOUT_RETURN_CODE

            # Let the consumer threads finish consuming output
            self.logger.info("Sub-process is finished, cleaning up stray resources and helper threads...")
            if ps_stats is not None:
                ps_stats.join()

        output = SubprocessShimOutput(
            elapsed,
            return_code,
            self.stdout_path,
            self.stderr_path,
            timed_out,
        )

        return output
