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
from common.misc import get_curr_year
from common.solver_io import SolverResultCode
from runner.commands.test_local import TestCase, TestResult
from runner.runner_config import ProjectConfig, SolverConfig

lm = LoggingManager()
logger = lm.get_logger("DistributedTestRunner")

# Exit codes signalling that the OS killed the solver (out-of-memory / SIGKILL).
OOM_RETURN_CODES = (137, -9)

# Artifact file names written by the leader harness into each per-run directory.
SOLVER_OUT_FILENAME = "solver_out.json"
INPUT_FILENAME = "input.json"
STDOUT_FILENAME = "stdout.txt"
STDERR_FILENAME = "stderr.txt"


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

        # Host directory bind-mounted onto the leader's work dir so that the
        # per-run artifacts the leader writes (solver_out.json, input.json,
        # stdout.txt, stderr.txt) survive the container and can be read back.
        self._artifacts_dir: Optional[str] = None

        # The leader harness writes its work dir at /tmp/{year}-dist-{solver}
        # (see leader_entrypoint.make_work_dir). We mount a host directory onto
        # exactly that path. The year is computed the same way the leader does.
        self._leader_work_dir_name = f"{get_curr_year()}-dist-{self.solver.name}"
        self._leader_work_dir = f"/tmp/{self._leader_work_dir_name}"

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

    def _create_artifacts_volume(self):
        """Create a host temp directory to capture the leader's per-run artifacts.

        This directory is bind-mounted onto the leader's work dir. Because the
        mount is world-writable and the leader (running as ecs-user) writes its
        solver_out.json/input.json/stdout.txt/stderr.txt there, the runner can
        read structured results back after the container exits, exactly like the
        sequential/parallel local test path reads solver_out.json.
        """
        self._artifacts_dir = tempfile.mkdtemp(prefix="satcomp-artifacts-")
        os.chmod(self._artifacts_dir, 0o777)
        logger.info(f"Created artifacts directory: {self._artifacts_dir}")

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
            "-v",
            f"{self._artifacts_dir}:{self._leader_work_dir}",
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
        """Collect results from the leader's structured per-run artifacts.

        Mirrors the sequential/parallel local test path: instead of scraping the
        leader's stdout logs for JSON, we read the `solver_out.json` files the
        leader harness writes into its (host-mounted) work dir, one per formula.

        For any formula that produced no artifact, we surface the leader log for
        diagnosis rather than silently reporting NO_RESULT.
        """
        leader_log = self._get_leader_logs()
        artifacts_by_formula = self._read_artifacts()
        logger.info(f"Read {len(artifacts_by_formula)} solver_out.json artifact(s) from leader work dir")

        results: List[TestResult] = []
        for tc in test_cases:
            artifact = artifacts_by_formula.get(tc.formula_path.name)
            if artifact is not None:
                results.append(self._result_from_artifact(tc, artifact))
            else:
                results.append(self._result_for_missing_artifact(tc, leader_log))

        return results

    def _get_leader_logs(self) -> str:
        """Fetch the leader container's combined stdout+stderr for diagnostics only."""
        try:
            proc = subprocess.run(
                ["docker", "logs", self.leader_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as e:
            logger.debug(f"Could not read leader logs: {e}")
            return ""
        return (proc.stdout or "") + "\n" + (proc.stderr or "")

    def _read_artifacts(self) -> Dict[str, dict]:
        """Read every `solver_out.json` under the artifacts dir, keyed by formula name.

        Each run directory (written by the leader) contains `input.json` (which
        names the formula), `solver_out.json` (the structured result), and
        `stdout.txt`/`stderr.txt`. We key by the formula's filename so results
        can be matched to test cases exactly, without relying on log formatting.
        """
        artifacts: Dict[str, dict] = {}
        if not self._artifacts_dir:
            return artifacts

        base = Path(self._artifacts_dir)
        for solver_out_path in base.rglob(SOLVER_OUT_FILENAME):
            run_dir = solver_out_path.parent
            formula_name = self._formula_name_from_run_dir(run_dir)
            if formula_name is None:
                logger.debug(f"Skipping run dir with no resolvable formula name: {run_dir}")
                continue

            solver_out = self._read_json(solver_out_path)
            if solver_out is None:
                logger.warning(f"Could not parse {solver_out_path}; skipping")
                continue

            artifacts[formula_name] = {
                "solver_result_code": solver_out.get("solver_result_code", SolverResultCode.INDETERMINATE.value),
                "process_return_code": solver_out.get("process_return_code", -1),
                "elapsed_time": solver_out.get("elapsed_time", 0.0),
                "stdout": self._read_text(run_dir / STDOUT_FILENAME),
                "stderr": self._read_text(run_dir / STDERR_FILENAME),
            }

        return artifacts

    def _formula_name_from_run_dir(self, run_dir: Path) -> Optional[str]:
        """Resolve the formula filename for a run dir by reading its input.json."""
        input_data = self._read_json(run_dir / INPUT_FILENAME)
        if not input_data:
            return None
        formula_file = input_data.get("formula_file", "")
        return os.path.basename(formula_file) if formula_file else None

    def _result_from_artifact(self, tc: TestCase, artifact: dict) -> TestResult:
        """Build a TestResult from a formula's structured solver_out.json artifact."""
        solver_result_code = artifact["solver_result_code"]
        process_return_code = artifact["process_return_code"]
        elapsed = artifact["elapsed_time"]

        actual_result = str(SolverResultCode.from_int(solver_result_code))

        # Mirror the inference the sequential path and harness apply:
        #   - an OS kill (OOM/SIGKILL) is reported as a CRASH
        #   - a solver that produced no SAT/UNSAT answer but ran out its budget
        #     is reported as a TIMEOUT
        if process_return_code in OOM_RETURN_CODES:
            actual_result = "CRASH"
            solver_result_code = SolverResultCode.CRASH.value
        elif actual_result not in ("SAT", "UNSAT") and elapsed >= tc.max_time_seconds:
            actual_result = "TIMEOUT"
            solver_result_code = SolverResultCode.TIMEOUT.value

        return TestResult(
            test_case=tc,
            actual_result=actual_result,
            elapsed_time=elapsed,
            passed=self._matches_expected(actual_result, tc.expected_result),
            stdout=artifact["stdout"],
            stderr=artifact["stderr"],
            solver_result_code=solver_result_code,
            process_return_code=process_return_code,
        )

    def _result_for_missing_artifact(self, tc: TestCase, leader_log: str) -> TestResult:
        """Build a TestResult for a formula that produced no artifact.

        No output is acceptable for TIMEOUT/CRASH tests (the run may not finish
        writing). Otherwise this is a genuine failure, so we surface the leader
        log to explain *why* instead of silently reporting NO_RESULT.
        """
        expected = tc.expected_result.upper()
        if expected in ("TIMEOUT", "CRASH"):
            logger.warning(f"No artifact for {tc.formula_path.name} (expected {expected}); inferring pass")
            actual = "TIMEOUT" if expected == "TIMEOUT" else "CRASH"
            return TestResult(
                test_case=tc,
                actual_result=actual,
                elapsed_time=0.0,
                passed=True,
                stdout="",
                stderr="",
                solver_result_code=SolverResultCode.TIMEOUT.value if expected == "TIMEOUT" else SolverResultCode.CRASH.value,
                process_return_code=0,
            )

        logger.error(
            f"No solver_out.json artifact for {tc.formula_path.name}; the distributed run "
            "likely failed before producing a result. See the leader log for details."
        )
        return TestResult(
            test_case=tc,
            actual_result="NO_RESULT",
            elapsed_time=0.0,
            passed=False,
            error_message=(
                "No solver_out.json artifact was produced for this formula. The distributed "
                "run likely failed before completing (e.g. the solver could not launch across "
                "the worker network). Inspect the leader log (captured as stdout) for the cause."
            ),
            stdout=leader_log,
            stderr="",
            solver_result_code=SolverResultCode.INDETERMINATE.value,
            process_return_code=-1,
        )

    def _matches_expected(self, actual: str, expected: str) -> bool:
        """Whether a distributed run's actual result satisfies the expectation.

        Distributed timeouts/crashes cannot always be distinguished as precisely
        as in the single-container path, so ERROR/CRASH/TIMEOUT expectations are
        matched leniently (a non-SAT/UNSAT outcome satisfies them).
        """
        a = actual.upper()
        e = expected.upper()
        if a == e:
            return True
        if e == "ERROR":
            return a not in ("SAT", "UNSAT")
        if e == "CRASH":
            return a in ("CRASH", "INDETERMINATE")
        if e == "TIMEOUT":
            return a not in ("SAT", "UNSAT")
        return False

    @staticmethod
    def _read_json(path: Path) -> Optional[dict]:
        """Read and parse a JSON file, returning None on any failure."""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _read_text(path: Path) -> str:
        """Read a text file, returning an empty string if it is missing/unreadable."""
        try:
            return path.read_text()
        except OSError:
            return ""

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

        # Remove artifacts temp directory
        if self._artifacts_dir and os.path.exists(self._artifacts_dir):
            try:
                import shutil

                shutil.rmtree(self._artifacts_dir, ignore_errors=True)
            except Exception as e:
                logger.debug(f"Error removing artifacts dir {self._artifacts_dir}: {e}")

    def run(self, test_cases: List[TestCase]) -> List[TestResult]:
        """Run distributed tests. Creates network, starts containers, waits, collects results."""
        logger.info(f"Starting distributed test: {self.num_workers} workers, network={self.network_name}")
        logger.info(f"Solver: {self.solver.name}, timeout: {self.timeout}s")

        self._register_signal_handlers()
        try:
            self._create_network()
            self._create_shared_volume()
            self._create_artifacts_volume()
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
