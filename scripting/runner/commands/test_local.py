"""Local solver testing command.

Runs solvers against test formulas in Docker containers to validate
that solvers work correctly before submission.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

import yaml
from common import LoggingManager
from common.constants import (
    DOCKER_PLATFORM,
    SAT_FORMULA_EXTENSION,
    SMT_FORMULA_EXTENSION,
)
from common.solver_io import SolverInput, SolverResultCode
from runner.commands.base import CommandContext, CommandHandler
from runner.runner_config import SolverConfig

if TYPE_CHECKING:
    from runner.runner_jobs import SolverJobManager

lm = LoggingManager()


@dataclass
class TestCase:
    """A single test case with formula path and expected result."""

    name: str
    formula_path: Path
    expected_result: str
    max_time_seconds: int
    description: str
    category: str  # 'easy', 'hard', 'malformed'
    format: str  # 'cnf' or 'smtlib'


@dataclass
class TestResult:
    """Result of running a single test case."""

    test_case: TestCase
    actual_result: str
    elapsed_time: float
    passed: bool
    error_message: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    solver_result_code: int = -6  # INDETERMINATE
    process_return_code: int = -1


class TestLocalCommand(CommandHandler):
    """Run local tests on Docker solver images.

    This command validates that solver Docker images work correctly by running
    them against a suite of test formulas with known expected results.

    The formula directory and expected.yml can be customized via jobs.yml:
    - formula_dir_test_local: Path to custom formula directory
    - expected_file_test_local: Path to custom expected.yml file

    Resolution order for formula directory:
    1. jobs.yml formula_dir_test_local
    2. Default examples/formulas/

    Resolution order for expected.yml:
    1. jobs.yml expected_file_test_local
    2. formula_dir/expected.yml (if custom formula_dir)
    3. Default examples/formulas/expected.yml
    """

    # Path to test formulas relative to project root
    TEST_FORMULAS_DIR = "examples/formulas"
    EXPECTED_RESULTS_FILE = "expected.yml"

    # Container paths (matching Dockerfile)
    CONTAINER_TEST_DIR = "/opt/amazon/test_formulas"
    CONTAINER_RUN_DIR = "/tmp/solver"

    def __init__(
        self,
        ctx: CommandContext,
        job_manager: Optional["SolverJobManager"] = None,
        logger=None,
        num_workers: Optional[int] = None,
    ):
        super().__init__(ctx, logger)
        self.project_root = ctx.cdk_path.parent
        self.job_manager = job_manager
        self.num_workers = num_workers

        # Resolve formula directory and expected.yml path
        self.test_formulas_path = self._resolve_formula_dir()
        self.expected_path = self._resolve_expected_path()

    def _resolve_formula_dir(self) -> Path:
        """Resolve the formula directory path.

        Resolution order:
        1. jobs.yml formula_dir_test_local
        2. Default examples/formulas/
        """
        if self.job_manager and self.job_manager.formula_dir_test_local:
            return self.job_manager.formula_dir_test_local
        return self.project_root / self.TEST_FORMULAS_DIR

    def _resolve_expected_path(self) -> Path:
        """Resolve the expected.yml file path.

        Resolution order:
        1. jobs.yml expected_file_test_local
        2. formula_dir/expected.yml (if custom formula_dir from jobs.yml)
        3. Default examples/formulas/expected.yml
        """
        if self.job_manager:
            # Check explicit expected file first
            if self.job_manager.expected_file_test_local:
                return self.job_manager.expected_file_test_local
            # Check for expected.yml in custom formula dir
            if self.job_manager.formula_dir_test_local:
                custom_expected = self.job_manager.formula_dir_test_local / self.EXPECTED_RESULTS_FILE
                if custom_expected.exists():
                    return custom_expected
        # Default location
        return self.project_root / self.TEST_FORMULAS_DIR / self.EXPECTED_RESULTS_FILE

    def execute(self, solver_name: Optional[str] = None, results_dir: Optional[Path] = None, **kwargs) -> int:
        """Execute local solver tests.

        Args:
            solver_name: Optional specific solver to test. If None, tests all solvers.
            results_dir: Optional directory to write results. If provided, writes:
                - summary.yml with overall results
                - Per-solver/per-formula directories with solver_out.json, stdout.log, stderr.log

        Returns:
            0 if all tests pass, 1 if any test fails
        """
        self.logger.info("test-local: Run local tests on Docker solver images")
        self.logger.info(f"Formula directory: {self.test_formulas_path}")
        self.logger.info(f"Expected results: {self.expected_path}")
        if results_dir:
            self.logger.info(f"Results output: {results_dir}")

        # Load expected results
        if not self.expected_path.exists():
            self.logger.error(f"Expected results file not found: {self.expected_path}")
            return 1

        test_cases = self._load_test_cases()
        if not test_cases:
            self.logger.error("No test cases found")
            return 1

        self.logger.info(f"Loaded {len(test_cases)} test cases")

        # Determine which solvers to test
        solvers_to_test = self._get_solvers_to_test(solver_name)
        if not solvers_to_test:
            self.logger.error("No solvers to test")
            return 1

        # Run tests for each solver and collect all results
        all_passed = True
        all_results: Dict[str, List[TestResult]] = {}

        for solver in solvers_to_test:
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"Testing solver: {solver.name}")
            self.logger.info(f"{'='*60}")

            # Filter test cases by solver type (CNF vs SMT-LIB)
            applicable_tests = self._filter_tests_for_solver(test_cases, solver)

            if not applicable_tests:
                self.logger.warning(f"No applicable tests for solver {solver.name}")
                continue

            results = self._run_tests(solver, applicable_tests)
            all_results[solver.name] = results

            # Print summary
            passed = sum(1 for r in results if r.passed)
            total = len(results)

            self.logger.info(f"\n{solver.name}: {passed}/{total} tests passed")

            for result in results:
                status = "PASS" if result.passed else "FAIL"
                self.logger.info(
                    f"  [{status}] {result.test_case.name}: "
                    f"expected={result.test_case.expected_result}, "
                    f"actual={result.actual_result}, "
                    f"time={result.elapsed_time:.2f}s"
                )
                if result.error_message:
                    self.logger.info(f"         Error: {result.error_message}")

            if passed < total:
                all_passed = False

        # Write results to disk if requested
        if results_dir:
            self._write_results(results_dir, all_results)

        # Final summary
        self.logger.info(f"\n{'='*60}")
        if all_passed:
            self.logger.info("All tests passed!")
            return 0
        else:
            self.logger.error("Some tests failed")
            return 1

    def _load_test_cases(self) -> List[TestCase]:
        """Load test cases from expected.yml."""
        with open(self.expected_path, "r") as f:
            expected = yaml.safe_load(f)

        test_cases = []

        for format_name, categories in expected.items():
            # Map format names to extensions
            if format_name == "cnf":
                ext = SAT_FORMULA_EXTENSION
            elif format_name == "smtlib":
                ext = SMT_FORMULA_EXTENSION
            else:
                continue

            for category, formulas in categories.items():
                for filename, config in formulas.items():
                    formula_path = self.test_formulas_path / format_name / category / filename

                    test_cases.append(
                        TestCase(
                            name=f"{format_name}/{category}/{filename}",
                            formula_path=formula_path,
                            expected_result=config["expected_result"],
                            max_time_seconds=config["max_time_seconds"],
                            description=config.get("description", ""),
                            category=category,
                            format=format_name,
                        )
                    )

        return test_cases

    def _get_solvers_to_test(self, solver_name: Optional[str]) -> List[SolverConfig]:
        """Get list of solvers to test."""
        all_solvers = self.ctx.project.solvers

        if solver_name:
            # Find specific solver
            for solver in all_solvers:
                if solver.name == solver_name:
                    return [solver]
            self.logger.error(f"Solver not found: {solver_name}")
            return []

        # Return all solvers except the infrastructure image
        return [s for s in all_solvers if s.name != "satcomp-infrastructure"]

    def _filter_tests_for_solver(self, test_cases: List[TestCase], solver: SolverConfig) -> List[TestCase]:
        """Filter test cases based on solver type (SAT vs SMT).

        Uses the project-level solver_type to determine which formula format
        to use: 'sat' projects get CNF formulas, 'smt' projects get SMT-LIB formulas.
        """
        solver_type = self.ctx.project.solver_type
        if solver_type == "sat":
            return [tc for tc in test_cases if tc.format == "cnf"]
        elif solver_type == "smt":
            return [tc for tc in test_cases if tc.format == "smtlib"]
        return test_cases

    def _run_tests(self, solver: SolverConfig, test_cases: List[TestCase]) -> List[TestResult]:
        """Run all test cases for a solver. Delegates to DistributedTestRunner for distributed solvers."""
        if solver.is_distributed:
            return self._run_distributed_tests(solver, test_cases)

        results = []
        for test_case in test_cases:
            result = self._run_single_test(solver, test_case)
            results.append(result)
        return results

    def _run_distributed_tests(self, solver: SolverConfig, test_cases: List[TestCase]) -> List[TestResult]:
        """Delegate to DistributedTestRunner for distributed solvers."""
        from runner.commands.test_local_distributed import DistributedTestRunner

        # Determine num_workers: CLI flag > config value > default 2
        num_workers = self.num_workers
        if num_workers is None and solver.cdk_solver is not None:
            num_workers = solver.cdk_solver.num_workers
        if num_workers is None or num_workers <= 0:
            num_workers = 2

        # Use the first test case's timeout, or a default
        timeout = test_cases[0].max_time_seconds if test_cases else 30

        self.logger.info(f"Distributed solver detected: {solver.name}")
        self.logger.info(f"  Workers: {num_workers}")

        runner = DistributedTestRunner(
            solver=solver,
            project=self.ctx.project,
            num_workers=num_workers,
            test_formulas_path=self.test_formulas_path,
            expected_path=self.expected_path,
            timeout=timeout,
            results_dir=None,  # Results writing handled by TestLocalCommand
        )

        self.logger.info(f"  Network: {runner.network_name}")
        return runner.run(test_cases)

    def _run_single_test(self, solver: SolverConfig, test_case: TestCase) -> TestResult:
        """Run a single test case against a solver."""
        self.logger.debug(f"Running test: {test_case.name}")

        image_name = solver.get_docker_name()

        # Check that the Docker image exists
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", image_name],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return TestResult(
                    test_case=test_case,
                    actual_result="ERROR",
                    elapsed_time=0.0,
                    passed=False,
                    error_message=f"Docker image not found: {image_name}. Run 'build' first.",
                )
        except Exception as e:
            return TestResult(
                test_case=test_case,
                actual_result="ERROR",
                elapsed_time=0.0,
                passed=False,
                error_message=f"Failed to check Docker image: {e}",
            )

        # Create a temporary directory for this test run
        # Make it world-writable since the container runs as ecs-user
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            tmpdir_path.chmod(0o777)

            # Copy formula to temp dir (simulating how it works in production)
            import shutil

            formula_dest = tmpdir_path / test_case.formula_path.name
            shutil.copy(test_case.formula_path, formula_dest)
            formula_dest.chmod(0o666)

            # Create input.json
            # Pass the test category via solver_argument_list so the solver knows what to expect
            input_json = {
                "formula_file": f"{self.CONTAINER_RUN_DIR}/{test_case.formula_path.name}",
                "run_dir": self.CONTAINER_RUN_DIR,
                "solver_argument_list": [f"--test-category={test_case.category}"],
                "timeout_seconds": test_case.max_time_seconds,
                "node_ip": "127.0.0.1",
                "worker_node_ips": [],
            }

            input_json_path = tmpdir_path / "input.json"
            with open(input_json_path, "w") as f:
                json.dump(input_json, f)

            # Create empty stdout/stderr files and make them world-writable
            # (the container runs as ecs-user, not root)
            stdout_file = tmpdir_path / "stdout.log"
            stderr_file = tmpdir_path / "stderr.log"
            stdout_file.touch()
            stderr_file.touch()
            stdout_file.chmod(0o666)
            stderr_file.chmod(0o666)
            input_json_path.chmod(0o666)

            # Run the Docker container
            start_time = time.time()

            try:
                # Run container with a custom script that directly invokes solver_cmd.py
                # This bypasses the full harness infrastructure for simpler local testing
                # Write the run script to a file in the temp directory
                run_script = f"""#!/usr/bin/env python3
import sys
import json
import time
sys.path.insert(0, '/opt/amazon/scripting')
from pathlib import Path
from common.solver_io import SolverInput
from harness.entrypoints.solver_cmd import get_run_command, get_solver_result

RUN_DIR = '{self.CONTAINER_RUN_DIR}'

# Create SolverInput from input.json
with open(f'{{RUN_DIR}}/input.json') as f:
    input_data = json.load(f)

s_input = SolverInput.from_dict(input_data)

# Get the run command
cmd = get_run_command(s_input)
print(f"Running command: {{cmd}}", file=sys.stderr)

# Execute the solver command
import subprocess
start = time.time()
try:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout={test_case.max_time_seconds},
    )
    elapsed = time.time() - start

    # Write stdout/stderr
    with open(f'{{RUN_DIR}}/stdout.log', 'w') as f:
        f.write(result.stdout)
    with open(f'{{RUN_DIR}}/stderr.log', 'w') as f:
        f.write(result.stderr)

    # Parse result
    solver_result = get_solver_result(Path(f'{{RUN_DIR}}/stdout.log'))

    # Write solver_out.json
    solver_out = {{
        'solver_result_code': solver_result.value,
        'process_return_code': result.returncode,
        'elapsed_time': elapsed,
        'artifacts': {{
            'stdout_path': f'{{RUN_DIR}}/stdout.log',
            'stderr_path': f'{{RUN_DIR}}/stderr.log',
        }}
    }}
    with open(f'{{RUN_DIR}}/solver_out.json', 'w') as f:
        json.dump(solver_out, f)

except subprocess.TimeoutExpired:
    elapsed = time.time() - start
    solver_out = {{
        'solver_result_code': -7,  # TIMEOUT
        'process_return_code': -1,
        'elapsed_time': elapsed,
        'artifacts': {{
            'stdout_path': f'{{RUN_DIR}}/stdout.log',
            'stderr_path': f'{{RUN_DIR}}/stderr.log',
        }}
    }}
    with open(f'{{RUN_DIR}}/solver_out.json', 'w') as f:
        json.dump(solver_out, f)
"""
                # Write the script to the temp directory
                script_path = tmpdir_path / "run_test.py"
                with open(script_path, "w") as f:
                    f.write(run_script)
                script_path.chmod(0o755)

                docker_cmd = [
                    "docker",
                    "run",
                    "--rm",
                    f"--platform={DOCKER_PLATFORM}",
                    "-v",
                    f"{tmpdir}:{self.CONTAINER_RUN_DIR}",
                    "--memory=4g",
                    "--shm-size=1g",
                    "--entrypoint",
                    "bash",
                    image_name,
                    "-c",
                    f"source /opt/amazon/scripting/.venv/bin/activate && python3 {self.CONTAINER_RUN_DIR}/run_test.py",
                ]

                # Add extra timeout buffer (2x the test timeout + 10 seconds)
                container_timeout = test_case.max_time_seconds * 2 + 10

                result = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=container_timeout,
                )

                elapsed_time = time.time() - start_time

                # Read stdout/stderr from temp dir
                stdout_content = ""
                stderr_content = ""
                stdout_file = tmpdir_path / "stdout.log"
                stderr_file = tmpdir_path / "stderr.log"
                if stdout_file.exists():
                    stdout_content = stdout_file.read_text()
                if stderr_file.exists():
                    stderr_content = stderr_file.read_text()

                # Read solver output
                solver_out_path = tmpdir_path / "solver_out.json"
                solver_result_code = -6  # INDETERMINATE
                process_return_code = -1
                if solver_out_path.exists():
                    with open(solver_out_path, "r") as f:
                        solver_out = json.load(f)

                    solver_result_code = solver_out.get("solver_result_code", -6)
                    process_return_code = solver_out.get("process_return_code", -1)
                    result_code = SolverResultCode.from_int(solver_result_code)
                    actual_result = str(result_code)
                else:
                    # No output file - check if it's a crash or timeout
                    if result.returncode != 0:
                        actual_result = "CRASH"
                        solver_result_code = -8  # CRASH
                        self.logger.debug(f"Container stderr: {result.stderr}")
                    else:
                        actual_result = "INDETERMINATE"

            except subprocess.TimeoutExpired:
                elapsed_time = time.time() - start_time
                actual_result = "TIMEOUT"
                solver_result_code = -7  # TIMEOUT
                process_return_code = -1
                stdout_content = ""
                stderr_content = ""
                # Kill the container if still running
                subprocess.run(
                    ["docker", "kill", image_name],
                    capture_output=True,
                )
            except Exception as e:
                elapsed_time = time.time() - start_time
                return TestResult(
                    test_case=test_case,
                    actual_result="ERROR",
                    elapsed_time=elapsed_time,
                    passed=False,
                    error_message=str(e),
                    solver_result_code=-6,
                    process_return_code=-1,
                )

        # Determine if test passed
        passed = self._result_matches_expected(actual_result, test_case.expected_result)

        return TestResult(
            test_case=test_case,
            actual_result=actual_result,
            elapsed_time=elapsed_time,
            passed=passed,
            stdout=stdout_content,
            stderr=stderr_content,
            solver_result_code=solver_result_code,
            process_return_code=process_return_code,
        )

    def _write_results(self, results_dir: Path, all_results: Dict[str, List[TestResult]]) -> None:
        """Write test results to disk in AWS-compatible format.

        Creates:
            {results_dir}/
            ├── summary.yml           # Overall summary with pass/fail counts
            └── {solver-name}/
                └── {formula-name}/
                    ├── solver_out.json   # AWS-compatible solver output
                    ├── stdout.log
                    └── stderr.log

        Args:
            results_dir: Directory to write results to
            all_results: Dict mapping solver name to list of TestResult
        """
        results_dir = Path(results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)

        # Calculate totals
        total_passed = 0
        total_failed = 0
        solvers_summary = {}

        for solver_name, results in all_results.items():
            solver_passed = sum(1 for r in results if r.passed)
            solver_failed = len(results) - solver_passed
            total_passed += solver_passed
            total_failed += solver_failed

            # Write per-formula results
            tests_summary = []
            for result in results:
                # Create formula directory - sanitize name for filesystem
                formula_dir_name = result.test_case.name.replace("/", "_")
                formula_dir = results_dir / solver_name / formula_dir_name
                formula_dir.mkdir(parents=True, exist_ok=True)

                # Write solver_out.json (AWS-compatible format)
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

                # Write stdout.log and stderr.log
                (formula_dir / "stdout.log").write_text(result.stdout)
                (formula_dir / "stderr.log").write_text(result.stderr)

                # Add to summary
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

            solvers_summary[solver_name] = {
                "passed": solver_passed,
                "failed": solver_failed,
                "tests": tests_summary,
            }

        # Write summary.yml
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "formula_dir": str(self.test_formulas_path),
            "expected_file": str(self.expected_path),
            "total_passed": total_passed,
            "total_failed": total_failed,
            "solvers": solvers_summary,
        }

        with open(results_dir / "summary.yml", "w") as f:
            yaml.dump(summary, f, default_flow_style=False, sort_keys=False)

        self.logger.info(f"Results written to: {results_dir}")
        self.logger.info(f"  summary.yml: {total_passed} passed, {total_failed} failed")

    def _result_matches_expected(self, actual: str, expected: str) -> bool:
        """Check if actual result matches expected result."""
        # Normalize result names
        actual_normalized = actual.upper()
        expected_normalized = expected.upper()

        # Direct match
        if actual_normalized == expected_normalized:
            return True

        # For ERROR expected, accept CRASH or INDETERMINATE
        if expected_normalized == "ERROR":
            return actual_normalized in ("CRASH", "INDETERMINATE", "ERROR")

        return False
