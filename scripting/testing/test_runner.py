"""Acceptance test runner for solver Docker images.

Orchestrates building solver images, running them against benchmark formulas,
and producing a pass/fail report.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from common import LoggingManager, SolverEnvironment
from common.constants import DOCKER_PLATFORM
from common.solver_io import CompetitionQueueOutput, SolverResultCode
from runner.runner_config import ProjectConfig, SolverConfig
from runner.runner_docker import SolverDockerClient

from .result_validator import ResultValidator
from .test_models import TestCaseDefinition, TestCaseResult, TestReport
from .test_registry import TestCaseRegistry

lm = LoggingManager()
logger = lm.get_logger("AcceptanceTestRunner")

# Container paths matching the satcomp-infrastructure Dockerfile
CONTAINER_RUN_DIR = "/tmp/solver"


class AcceptanceTestRunner:
    """Top-level orchestrator for solver acceptance tests."""

    def __init__(
        self,
        project: ProjectConfig,
        solver_names: Optional[List[str]] = None,
        timeout_secs: int = 30,
        aws_mode: bool = False,
        boto3_session=None,
        account_id: str = None,
    ):
        self.project = project
        self.solver_names = solver_names
        self.timeout_secs = timeout_secs
        self.aws_mode = aws_mode
        self.sdc = SolverDockerClient(project)
        self._boto3_session = boto3_session
        self._account_id = account_id

        # Resolve test_formulas directory relative to project root
        script_dir = Path(__file__).resolve().parent
        self.project_root = script_dir.parent.parent
        self.formula_dir = self.project_root / "test_formulas"

    def run(self) -> TestReport:
        """Build images, run all test cases, return the report."""
        solvers = self._resolve_solvers()
        if not solvers:
            logger.error("No solvers to test")
            report = TestReport(solver_name="(none)", timeout_secs=self.timeout_secs)
            report.print_report()
            return report

        # For now, test one solver at a time and return the first report
        # (multi-solver support returns the combined report)
        all_results: List[TestCaseResult] = []
        solver_name_label = ", ".join(s.name for s in solvers)

        for solver in solvers:
            # Build images
            if not self._build_images():
                logger.error("Docker build failed. No tests will be run.")
                report = TestReport(
                    solver_name=solver.name,
                    timeout_secs=self.timeout_secs,
                )
                report.print_report()
                return report

            # Discover test cases
            registry = TestCaseRegistry(self.formula_dir, self.timeout_secs)
            try:
                test_cases = registry.get_default_test_cases()
            except FileNotFoundError as e:
                logger.warning(str(e))
                test_cases = registry.discover_test_cases()

            if not test_cases:
                logger.error(f"No test cases found in {self.formula_dir}")
                report = TestReport(
                    solver_name=solver.name,
                    timeout_secs=self.timeout_secs,
                )
                report.print_report()
                return report

            # Filter by solver type (cnf for SAT, smt2 for SMT)
            test_cases = self._filter_by_solver_type(test_cases)

            logger.info(f"Running {len(test_cases)} test cases for solver '{solver.name}'")

            # Execute each test case
            if self.aws_mode:
                results = self._run_all_test_cases_aws(solver.name, test_cases)
                all_results.extend(results)
            else:
                for tc in test_cases:
                    result = self._run_test_case_local(solver.name, tc)
                    all_results.append(result)

        report = TestReport(
            solver_name=solver_name_label,
            results=all_results,
            timeout_secs=self.timeout_secs,
        )
        report.print_report()
        return report

    def _resolve_solvers(self) -> List[SolverConfig]:
        """Resolve which solvers to test."""
        all_solvers = [s for s in self.project.solvers if s.name != "satcomp-infrastructure"]

        if self.solver_names is None:
            return all_solvers

        resolved = []
        for name in self.solver_names:
            found = False
            for s in all_solvers:
                if s.name == name:
                    resolved.append(s)
                    found = True
                    break
            if not found:
                available = [s.name for s in all_solvers]
                logger.error(f"Solver '{name}' not found in config. " f"Available: {available}")
                return []
        return resolved

    def _filter_by_solver_type(self, test_cases: List[TestCaseDefinition]) -> List[TestCaseDefinition]:
        """Filter test cases by the project's solver type (sat → .cnf, smt → .smt2)."""
        solver_type = self.project.solver_type
        if solver_type == "sat":
            return [tc for tc in test_cases if tc.benchmark_path.endswith(".cnf")]
        elif solver_type == "smt":
            return [tc for tc in test_cases if tc.benchmark_path.endswith(".smt2")]
        return test_cases

    def _build_images(self) -> bool:
        """Build Docker images. Returns True on success."""
        try:
            self.sdc.build_images(force_rebuild=True)
            return True
        except SystemExit:
            return False
        except Exception as e:
            logger.error(f"Docker build failed: {e}")
            print(str(e), file=sys.stderr)
            return False

    def _run_test_case_local(self, solver_name: str, test_case: TestCaseDefinition) -> TestCaseResult:
        """Run a single test case locally using Docker."""
        logger.info(
            f"  Running test: {test_case.name} (expected: " f"{', '.join(str(r) for r in test_case.expected_results)})"
        )

        image_name = f"{solver_name}:latest"
        benchmark_path = Path(test_case.benchmark_path)

        if not benchmark_path.exists():
            return TestCaseResult(
                test_case=test_case,
                solver_result_code=SolverResultCode.INDETERMINATE,
                elapsed_time_ms=0,
                passed=False,
                error_message=f"Benchmark file not found: {benchmark_path}",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            tmpdir_path.chmod(0o777)

            # Copy formula to temp dir
            import shutil

            formula_dest = tmpdir_path / benchmark_path.name
            shutil.copy(benchmark_path, formula_dest)
            formula_dest.chmod(0o666)

            # Create input.json
            input_json = {
                "formula_file": f"{CONTAINER_RUN_DIR}/{benchmark_path.name}",
                "run_dir": CONTAINER_RUN_DIR,
                "solver_argument_list": [],
                "timeout_seconds": test_case.timeout_secs,
                "node_ip": "127.0.0.1",
                "worker_node_ips": [],
            }
            input_json_path = tmpdir_path / "input.json"
            with open(input_json_path, "w") as f:
                json.dump(input_json, f)

            # Create empty stdout/stderr files
            for fname in ["stdout.log", "stderr.log"]:
                p = tmpdir_path / fname
                p.touch()
                p.chmod(0o666)
            input_json_path.chmod(0o666)

            # Build the run script
            run_script = self._build_run_script(test_case)
            script_path = tmpdir_path / "run_test.py"
            with open(script_path, "w") as f:
                f.write(run_script)
            script_path.chmod(0o755)

            # Docker run command
            docker_cmd = [
                "docker",
                "run",
                "--rm",
                f"--platform={DOCKER_PLATFORM}",
                "-v",
                f"{tmpdir}:{CONTAINER_RUN_DIR}",
            ]

            # Apply memory limit for OOM tests
            if test_case.memory_limit_mb is not None:
                docker_cmd.extend(["--memory", f"{test_case.memory_limit_mb}m"])
            else:
                # Default: 4GB for normal tests, 128MB for OOM tests
                is_oom = any(Path(test_case.benchmark_path).stem.startswith("oom_") for _ in [1])
                if is_oom:
                    docker_cmd.extend(["--memory", "128m", "--memory-swap", "128m"])
                else:
                    docker_cmd.extend(["--memory", "4g", "--shm-size", "1g"])

            docker_cmd.extend(
                [
                    "--entrypoint",
                    "bash",
                    image_name,
                    "-c",
                    f"source /opt/amazon/scripting/.venv/bin/activate && python3 {CONTAINER_RUN_DIR}/run_test.py",
                ]
            )

            container_timeout = test_case.timeout_secs * 2 + 30
            start_time = time.time()

            try:
                result = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=container_timeout,
                )
                elapsed_time = time.time() - start_time
            except subprocess.TimeoutExpired:
                elapsed_time = time.time() - start_time
                elapsed_ms = round(elapsed_time * 1000)
                # Build a synthetic output for timeout
                output = CompetitionQueueOutput(
                    solver=solver_name,
                    process_return_code=-1,
                    solver_result_code=SolverResultCode.TIMEOUT,
                    solver_runtime_millis=elapsed_ms,
                    job_time_start="",
                    formula_s3_uri=str(benchmark_path),
                    upload_dir_uri="",
                )
                return ResultValidator.validate(test_case, output)
            except Exception as e:
                return TestCaseResult(
                    test_case=test_case,
                    solver_result_code=SolverResultCode.CRASH,
                    elapsed_time_ms=round((time.time() - start_time) * 1000),
                    passed=False,
                    error_message=f"Container execution error: {e}",
                )

            # Read solver output
            solver_out_path = tmpdir_path / "solver_out.json"
            if solver_out_path.exists():
                with open(solver_out_path, "r") as f:
                    solver_out = json.load(f)

                result_code_int = solver_out.get("solver_result_code", -6)
                result_code = SolverResultCode.from_int(result_code_int)
                elapsed_s = solver_out.get("elapsed_time", elapsed_time)
                elapsed_ms = round(elapsed_s * 1000)
            else:
                # No output file — container crashed or OOM
                if result.returncode == 137:
                    # SIGKILL — likely OOM
                    result_code = SolverResultCode.CRASH
                elif result.returncode != 0:
                    result_code = SolverResultCode.CRASH
                else:
                    result_code = SolverResultCode.INDETERMINATE
                elapsed_ms = round(elapsed_time * 1000)

            output = CompetitionQueueOutput(
                solver=solver_name,
                process_return_code=result.returncode,
                solver_result_code=result_code,
                solver_runtime_millis=elapsed_ms,
                job_time_start="",
                formula_s3_uri=str(benchmark_path),
                upload_dir_uri="",
            )
            return ResultValidator.validate(test_case, output)

    def _run_all_test_cases_aws(self, solver_name: str, test_cases: List[TestCaseDefinition]) -> List[TestCaseResult]:
        """Run all test cases on AWS in two phases: safe tests first, then destructive tests."""
        from common import ResourceNamer
        from harness.aws_shim import S3FileSystem, SqsQueue
        from utils.solver_request import SolverRequester

        project = self.project
        session = self._boto3_session
        rn = ResourceNamer(project.project, self._account_id, project.region)
        rn.set_solver(solver_name)

        s3 = S3FileSystem.get_s3_file_system_from_session(session)
        bucket = rn.get_bucket_name()
        q_in = SqsQueue.get_sqs_queue_from_session(session, rn.get_sqs_input_queue_name())
        q_out = SqsQueue.get_sqs_queue_from_session(session, rn.get_sqs_output_queue_name())

        # Split into safe tests (SAT, UNSAT, timeout) and destructive tests (OOM, malformed)
        destructive_prefixes = {"oom_", "malformed_"}
        safe_tests = [tc for tc in test_cases
                      if not any(Path(tc.benchmark_path).stem.startswith(p) for p in destructive_prefixes)]
        destructive_tests = [tc for tc in test_cases
                             if any(Path(tc.benchmark_path).stem.startswith(p) for p in destructive_prefixes)]

        all_results = []
        for batch_label, batch in [("safe", safe_tests), ("destructive", destructive_tests)]:
            if not batch:
                continue

            # Purge output queue before each batch (skip if recently purged)
            logger.info(f"  Clearing output queue before {batch_label} tests...")
            try:
                q_out.purge()
                time.sleep(5)
            except Exception:
                # SQS limits purge to once per 60s — drain instead
                while True:
                    msg = q_out.get_message(wait_time_secs=1)
                    if not msg:
                        break
                    msg.delete()

            # Submit all in batch
            uri_map = {}
            max_timeout = 0
            for tc in batch:
                benchmark_path = Path(tc.benchmark_path)
                if not benchmark_path.exists():
                    continue
                s3_key = f"acceptance-test/{tc.name}/{benchmark_path.name}"
                s3_uri = f"s3://{bucket}/{s3_key}"
                s3.upload_file(str(benchmark_path), bucket, s3_key)
                requester = SolverRequester(solver_name, [], tc.timeout_secs)
                q_in.send_message(requester.make_request_json(s3_uri))
                uri_map[s3_uri] = tc
                max_timeout = max(max_timeout, tc.timeout_secs)
                logger.info(f"  Submitted: {tc.name}")

            # Collect results
            poll_timeout = max_timeout * 2 + 120
            start_time = time.time()
            collected = {}

            while len(collected) < len(uri_map) and time.time() - start_time < poll_timeout:
                msg = q_out.get_message(wait_time_secs=10)
                if msg:
                    body = json.loads(msg.read())
                    msg.delete()
                    uri = body.get("formula_s3_uri", "")
                    if uri in uri_map:
                        collected[uri] = body
                        logger.info(f"  Result: {uri_map[uri].name} -> {body.get('solving_result', '?')}")

            # Validate
            for s3_uri, tc in uri_map.items():
                if s3_uri in collected:
                    output = CompetitionQueueOutput.from_dict(collected[s3_uri])
                else:
                    result_code = SolverResultCode.INDETERMINATE
                    if SolverResultCode.TIMEOUT in tc.expected_results:
                        result_code = SolverResultCode.TIMEOUT
                    output = CompetitionQueueOutput(
                        solver=solver_name, process_return_code=-1,
                        solver_result_code=result_code,
                        solver_runtime_millis=round((time.time() - start_time) * 1000),
                        job_time_start="", formula_s3_uri=s3_uri, upload_dir_uri="",
                    )
                all_results.append(ResultValidator.validate(tc, output))

        return all_results

    @staticmethod
    def _build_run_script(test_case: TestCaseDefinition) -> str:
        """Build the Python script that runs inside the Docker container."""
        return f"""#!/usr/bin/env python3
import sys
import json
import time
sys.path.insert(0, '/opt/amazon/scripting')
from pathlib import Path
from common.solver_io import SolverInput
from harness.entrypoints.solver_cmd import get_run_command, get_solver_result

RUN_DIR = '{CONTAINER_RUN_DIR}'

with open(f'{{RUN_DIR}}/input.json') as f:
    input_data = json.load(f)

s_input = SolverInput.from_dict(input_data)
cmd = get_run_command(s_input)
print(f"Running command: {{cmd}}", file=sys.stderr)

import subprocess
start = time.time()
try:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout={test_case.timeout_secs},
    )
    elapsed = time.time() - start

    with open(f'{{RUN_DIR}}/stdout.log', 'w') as f:
        f.write(result.stdout)
    with open(f'{{RUN_DIR}}/stderr.log', 'w') as f:
        f.write(result.stderr)

    solver_result = get_solver_result(Path(f'{{RUN_DIR}}/stdout.log'))

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
        'solver_result_code': -7,
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
