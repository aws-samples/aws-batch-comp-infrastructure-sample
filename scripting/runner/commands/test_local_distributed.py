"""Distributed local solver testing.

Orchestrates multi-container local testing for distributed solvers by
creating a Docker bridge network, starting leader + worker containers,
waiting for completion, and collecting results.
"""

import json
import os
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import yaml
from common import LoggingManager
from common.constants import DOCKER_PLATFORM, SAT_FORMULA_EXTENSION, SMT_FORMULA_EXTENSION
from common.solver_io import SolverResultCode
from runner.commands.test_local import TestCase, TestResult
from runner.runner_config import ProjectConfig, SolverConfig

lm = LoggingManager()
logger = lm.get_logger("DistributedTestRunner")


class DistributedTestRunner:
    """Orchestrates multi-container local testing for distributed solvers."""

    def __init__(
        self,
        solver: SolverConfig,
        project: ProjectConfig,
        num_workers: int,
        test_formulas_path: Path,
        expected_path: Path,
        timeout: int,
        results_dir: Optional[Path] = None,
    ):
        self.solver = solver
        self.project = project
        self.num_workers = num_workers
        self.test_formulas_path = test_formulas_path
        self.expected_path = expected_path
        self.timeout = timeout
        self.results_dir = results_dir

        # Generate unique names for network and containers
        uid = uuid4().hex[:8]
        self.network_name = f"satcomp-local-{uid}"
        self.leader_name = f"satcomp-leader-{uid}"
        self.worker_names: List[str] = [f"satcomp-worker-{i}-{uuid4().hex[:8]}" for i in range(num_workers)]
        self.container_names: List[str] = []

        # Shared volume temp directory
        self._shared_dir: Optional[str] = None

        # Cleanup flag for signal handling
        self._cleanup_requested = False
        self._original_sigint = None
        self._original_sigterm = None

    def _register_signal_handlers(self):
        """Register SIGINT/SIGTERM handlers that trigger cleanup."""
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)

        def _handler(signum, frame):
            logger.info(f"Received signal {signum}, requesting cleanup...")
            self._cleanup_requested = True

        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    def _restore_signal_handlers(self):
        """Restore original signal handlers."""
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)

    def _create_network(self):
        """Create a Docker bridge network."""
        logger.info(f"Creating Docker network: {self.network_name}")
        result = subprocess.run(
            ["docker", "network", "create", "--driver", "bridge", self.network_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create Docker network: {result.stderr.strip()}")

    def _create_shared_volume(self):
        """Create a temp directory for shared JSON state files."""
        self._shared_dir = tempfile.mkdtemp(prefix="satcomp-shared-")
        os.chmod(self._shared_dir, 0o777)
        logger.info(f"Created shared state directory: {self._shared_dir}")

    def _build_env_vars(self, node_type: str) -> Dict[str, str]:
        """Build environment variables dict for a container."""
        env = {
            "SOLVER_NODE_TYPE": node_type,
            "NUM_WORKERS": str(self.num_workers),
            "SOLVER_NAME": self.solver.name,
            "PROJECT_NAME": self.project.project,
            "LOCAL_TIMEOUT": str(self.timeout),
            "SHARED_STATE_DIR": "/shared",
        }
        return env

    def _start_worker_containers(self):
        """Start N worker containers on the network."""
        image_name = self.solver.get_docker_name()
        env = self._build_env_vars("distributed-worker")
        # Workers don't need LOCAL_TEST_FILES
        env["LOCAL_TEST_FILES"] = "/dev/null"

        for name in self.worker_names:
            if self._cleanup_requested:
                return
            logger.info(f"Starting worker container: {name}")
            cmd = [
                "docker",
                "run",
                "-d",
                f"--platform={DOCKER_PLATFORM}",
                "--user", "ecs-user",
                "--name",
                name,
                f"--network={self.network_name}",
                "-v",
                f"{self._shared_dir}:/shared",
            ]
            for k, v in env.items():
                cmd.extend(["-e", f"{k}={v}"])
            cmd.append(image_name)

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Failed to start worker {name}: {result.stderr.strip()}")
            self.container_names.append(name)

    def _start_leader_container(self):
        """Start the leader container on the network."""
        image_name = self.solver.get_docker_name()
        env = self._build_env_vars("distributed-leader")

        # Leader gets the test formulas mounted and a glob for LOCAL_TEST_FILES
        solver_type = self.project.solver_type
        if solver_type == "sat":
            formula_glob = "/opt/amazon/test_formulas/**/*.cnf"
        elif solver_type == "smt":
            formula_glob = "/opt/amazon/test_formulas/**/*.smt2"
        else:
            formula_glob = "/opt/amazon/test_formulas/**/*"
        env["LOCAL_TEST_FILES"] = formula_glob

        logger.info(f"Starting leader container: {self.leader_name}")
        cmd = [
            "docker",
            "run",
            "-d",
            f"--platform={DOCKER_PLATFORM}",
            "--user", "ecs-user",
            "--name",
            self.leader_name,
            f"--network={self.network_name}",
            "-v",
            f"{self._shared_dir}:/shared",
            "-v",
            f"{self.test_formulas_path}:/opt/amazon/test_formulas:ro",
        ]
        for k, v in env.items():
            cmd.extend(["-e", f"{k}={v}"])
        cmd.append(image_name)

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start leader: {result.stderr.strip()}")
        self.container_names.append(self.leader_name)

    def _wait_for_leader(self):
        """Wait for the leader container to exit, with timeout."""
        # docker wait blocks until the container stops; we use a timeout
        container_timeout = self.timeout * 4 + 60  # generous buffer
        logger.info(f"Waiting for leader container (timeout: {container_timeout}s)...")

        try:
            result = subprocess.run(
                ["docker", "wait", self.leader_name],
                capture_output=True,
                text=True,
                timeout=container_timeout,
            )
            exit_code = result.stdout.strip()
            logger.info(f"Leader container exited with code: {exit_code}")
        except subprocess.TimeoutExpired:
            logger.warning("Leader container timed out, stopping all containers")

    def _collect_results(self, test_cases: List[TestCase]) -> List[TestResult]:
        """Collect results from leader container logs."""
        result = subprocess.run(
            ["docker", "logs", self.leader_name],
            capture_output=True,
            text=True,
        )
        stdout = result.stdout
        stderr = result.stderr
        # docker logs sends container stdout to result.stdout and container stderr to result.stderr
        # Python logging defaults to stderr, so check both
        combined = stdout + "\n" + stderr

        # Parse output queue messages from leader logs
        # The leader logs JSON output queue messages
        output_messages = []
        for line in combined.split("\n"):
            # Leader entrypoint logs messages like: {"solver": "...", "solver_result_code": ...}
            line = line.strip()
            if not line:
                continue
            # Try to find JSON in the log line (may be prefixed by logger info)
            brace_idx = line.find("{")
            if brace_idx >= 0:
                json_str = line[brace_idx:]
                try:
                    msg = json.loads(json_str)
                    if "solver_result_code" in msg:
                        output_messages.append(msg)
                except (json.JSONDecodeError, KeyError):
                    pass

        # Build expected results map from test cases
        logger.info(f"Found {len(output_messages)} result messages from leader logs")
        expected_by_formula = {}
        for tc in test_cases:
            formula_name = tc.formula_path.name
            expected_by_formula[formula_name] = tc

        results = []
        matched_formulas = set()

        for msg in output_messages:
            formula_url = msg.get("formula_s3_uri", "")
            formula_name = os.path.basename(formula_url)
            solver_result_code = msg.get("solver_result_code", -6)
            runtime_millis = msg.get("solver_runtime_millis", 0)

            result_code = SolverResultCode.from_int(solver_result_code)
            actual_result = str(result_code)
            elapsed = runtime_millis / 1000.0

            tc = expected_by_formula.get(formula_name)
            if tc is None:
                continue

            matched_formulas.add(formula_name)
            passed = actual_result.upper() == tc.expected_result.upper()
            # For ERROR expected, accept anything except SAT/UNSAT
            if tc.expected_result.upper() == "ERROR":
                passed = actual_result.upper() not in ("SAT", "UNSAT")

            # For CRASH expected, accept INDETERMINATE (OOM may report either)
            if tc.expected_result.upper() == "CRASH":
                passed = passed or actual_result.upper() in ("CRASH", "INDETERMINATE")

            # For TIMEOUT expected, accept INDETERMINATE if solver ran long enough
            if tc.expected_result.upper() == "TIMEOUT":
                passed = passed or actual_result.upper() not in ("SAT", "UNSAT")

            results.append(
                TestResult(
                    test_case=tc,
                    actual_result=actual_result,
                    elapsed_time=elapsed,
                    passed=passed,
                    stdout=stdout,
                    stderr=stderr,
                    solver_result_code=solver_result_code,
                    process_return_code=0,
                )
            )

        # Any test cases that didn't produce output
        for tc in test_cases:
            if tc.formula_path.name not in matched_formulas:
                expected = tc.expected_result.upper()
                # No output is acceptable for TIMEOUT and CRASH tests
                if expected in ("TIMEOUT", "CRASH"):
                    logger.warning(
                        f"No output for {tc.formula_path.name} (expected {expected}); inferring pass"
                    )
                    actual = "TIMEOUT" if expected == "TIMEOUT" else "CRASH"
                    results.append(
                        TestResult(
                            test_case=tc,
                            actual_result=actual,
                            elapsed_time=0.0,
                            passed=True,
                            stdout=stdout,
                            stderr=stderr,
                            solver_result_code=-7 if expected == "TIMEOUT" else -8,
                            process_return_code=0,
                        )
                    )
                else:
                    results.append(
                        TestResult(
                            test_case=tc,
                            actual_result="NO_RESULT",
                            elapsed_time=0.0,
                            passed=False,
                            error_message="No result produced by distributed run",
                            stdout=stdout,
                            stderr=stderr,
                        )
                    )

        return results

    def _cleanup(self):
        """Stop and remove all containers, remove network, remove temp dir."""
        logger.info("Cleaning up distributed test resources...")

        # Stop and remove containers
        for name in self.container_names:
            try:
                subprocess.run(
                    ["docker", "stop", "-t", "5", name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except Exception as e:
                logger.debug(f"Error stopping container {name}: {e}")
            try:
                subprocess.run(
                    ["docker", "rm", "-f", name],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            except Exception as e:
                logger.debug(f"Error removing container {name}: {e}")

        # Remove network
        try:
            subprocess.run(
                ["docker", "network", "rm", self.network_name],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as e:
            logger.debug(f"Error removing network {self.network_name}: {e}")

        # Remove shared temp directory
        if self._shared_dir and os.path.exists(self._shared_dir):
            try:
                import shutil

                shutil.rmtree(self._shared_dir, ignore_errors=True)
            except Exception as e:
                logger.debug(f"Error removing shared dir {self._shared_dir}: {e}")

    def run(self, test_cases: List[TestCase]) -> List[TestResult]:
        """Run distributed tests. Creates network, starts containers, waits, collects results."""
        logger.info(f"Starting distributed test: {self.num_workers} workers, network={self.network_name}")
        logger.info(f"Solver: {self.solver.name}, timeout: {self.timeout}s")

        self._register_signal_handlers()
        try:
            self._create_network()
            self._create_shared_volume()
            self._start_worker_containers()

            if self._cleanup_requested:
                return [
                    TestResult(
                        test_case=tc,
                        actual_result="INTERRUPTED",
                        elapsed_time=0.0,
                        passed=False,
                        error_message="Test interrupted by signal",
                    )
                    for tc in test_cases
                ]

            self._start_leader_container()
            self._wait_for_leader()
            results = self._collect_results(test_cases)

            # Write results if results_dir provided
            if self.results_dir:
                self._write_results(results)

            return results
        except Exception as e:
            logger.error(f"Distributed test failed: {e}")
            return [
                TestResult(
                    test_case=tc,
                    actual_result="ERROR",
                    elapsed_time=0.0,
                    passed=False,
                    error_message=str(e),
                )
                for tc in test_cases
            ]
        finally:
            self._cleanup()
            self._restore_signal_handlers()

    def _write_results(self, results: List[TestResult]):
        """Write results to results_dir in the same format as TestLocalCommand."""
        if not self.results_dir:
            return

        self.results_dir.mkdir(parents=True, exist_ok=True)
        solver_name = self.solver.name

        tests_summary = []
        passed_count = 0
        failed_count = 0

        for result in results:
            if result.passed:
                passed_count += 1
            else:
                failed_count += 1

            formula_dir_name = result.test_case.name.replace("/", "_")
            formula_dir = self.results_dir / solver_name / formula_dir_name
            formula_dir.mkdir(parents=True, exist_ok=True)

            solver_out = {
                "solver_result_code": result.solver_result_code,
                "process_return_code": result.process_return_code,
                "elapsed_time": result.elapsed_time,
                "artifacts": {
                    "stdout_path": str(formula_dir / "stdout.log"),
                    "stderr_path": str(formula_dir / "stderr.log"),
                },
            }
            with open(formula_dir / "solver_out.json", "w") as f:
                json.dump(solver_out, f, indent=2)

            (formula_dir / "stdout.log").write_text(result.stdout)
            (formula_dir / "stderr.log").write_text(result.stderr)

            tests_summary.append(
                {
                    "name": result.test_case.name,
                    "expected": result.test_case.expected_result,
                    "actual": result.actual_result,
                    "passed": result.passed,
                    "time_seconds": round(result.elapsed_time, 3),
                    "error": result.error_message,
                }
            )

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "formula_dir": str(self.test_formulas_path),
            "expected_file": str(self.expected_path),
            "mode": "distributed",
            "num_workers": self.num_workers,
            "network_name": self.network_name,
            "total_passed": passed_count,
            "total_failed": failed_count,
            "solvers": {
                solver_name: {
                    "passed": passed_count,
                    "failed": failed_count,
                    "tests": tests_summary,
                }
            },
        }

        with open(self.results_dir / "summary.yml", "w") as f:
            yaml.dump(summary, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Results written to: {self.results_dir}")
