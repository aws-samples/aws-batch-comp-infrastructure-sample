"""Tests for the test-local command in runner.commands.test_local.

Tests cover:
  - Loading test cases from expected.yml
  - Filtering test cases for specific solvers
  - Result matching logic (_result_matches_expected)
  - Docker container execution (mocked)
  - Full test workflow with pass/fail scenarios
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, Mock, patch, mock_open, call

import pytest
import yaml

from common.solver_io import SolverResultCode
from runner.commands.base import CommandContext
from runner.commands.test_local import TestCase, TestLocalCommand, TestResult
from runner.runner_config import SolverConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_project():
    """Create a mock ProjectConfig."""
    project = MagicMock()
    project.project = "test-project"
    project.region = "us-west-2"
    project.profile = "default"
    project.solver_type = "SAT"

    # Create mock solvers
    solver1 = MagicMock(spec=SolverConfig)
    solver1.name = "solver1"
    solver1.get_docker_name.return_value = "test-project--solver1"
    solver1.is_distributed = False

    solver2 = MagicMock(spec=SolverConfig)
    solver2.name = "solver2"
    solver2.get_docker_name.return_value = "test-project--solver2"
    solver2.is_distributed = False

    infra = MagicMock(spec=SolverConfig)
    infra.name = "satcomp-infrastructure"
    infra.get_docker_name.return_value = "satcomp-infrastructure"
    infra.is_distributed = False

    project.solvers = [solver1, solver2, infra]
    return project


@pytest.fixture
def mock_sdc():
    """Create a mock SolverDockerClient."""
    sdc = MagicMock()
    sdc.get_solvers.return_value = ["solver1", "solver2", "satcomp-infrastructure"]
    sdc.get_aws_solvers.return_value = ["solver1", "solver2"]
    return sdc


@pytest.fixture
def ctx(mock_project, mock_sdc):
    """Create a CommandContext with mocks."""
    ctx = CommandContext(
        project=mock_project,
        sdc=mock_sdc,
        cdk_path=Path("/tmp/cdk"),
        boto3_session=None,
        account=None,
        rn=None,
    )
    return ctx


@pytest.fixture
def expected_yml_content():
    """Sample expected.yml content."""
    return {
        "cnf": {
            "easy": {
                "test1.cnf": {
                    "expected_result": "SAT",
                    "max_time_seconds": 10,
                    "description": "Easy SAT formula"
                },
                "test2.cnf": {
                    "expected_result": "UNSAT",
                    "max_time_seconds": 10,
                    "description": "Easy UNSAT formula"
                }
            },
            "hard": {
                "test3.cnf": {
                    "expected_result": "TIMEOUT",
                    "max_time_seconds": 5,
                    "description": "Hard formula that times out"
                }
            },
            "malformed": {
                "test4.cnf": {
                    "expected_result": "ERROR",
                    "max_time_seconds": 5,
                    "description": "Malformed formula"
                }
            }
        },
        "smtlib": {
            "easy": {
                "test1.smt2": {
                    "expected_result": "SAT",
                    "max_time_seconds": 10,
                    "description": "Easy SMT-LIB formula"
                }
            }
        }
    }


@pytest.fixture
def test_local_cmd(ctx, tmp_path):
    """Create a TestLocalCommand instance with mocked paths."""
    cmd = TestLocalCommand(ctx)
    # Override paths to use tmp_path
    cmd.project_root = tmp_path
    cmd.test_formulas_path = tmp_path / "test_formulas"
    cmd.expected_path = cmd.test_formulas_path / "expected.yml"

    # Create directory structure
    cmd.test_formulas_path.mkdir(parents=True, exist_ok=True)

    return cmd


# ---------------------------------------------------------------------------
# Test Case Loading Tests
# ---------------------------------------------------------------------------

class TestLoadTestCases:
    """Tests for _load_test_cases method."""

    def test_load_test_cases_valid(self, test_local_cmd, expected_yml_content):
        """Test loading valid test cases from expected.yml."""
        # Write expected.yml
        with open(test_local_cmd.expected_path, 'w') as f:
            yaml.dump(expected_yml_content, f)

        # Create formula files
        for format_name in ["cnf", "smtlib"]:
            for category in expected_yml_content.get(format_name, {}).keys():
                category_path = test_local_cmd.test_formulas_path / format_name / category
                category_path.mkdir(parents=True, exist_ok=True)
                for filename in expected_yml_content.get(format_name, {}).get(category, {}).keys():
                    (category_path / filename).touch()

        # Load test cases
        test_cases = test_local_cmd._load_test_cases()

        # Assertions
        assert len(test_cases) == 5  # 4 CNF + 1 SMT-LIB

        # Check first CNF test case
        cnf_test = next(tc for tc in test_cases if tc.name == "cnf/easy/test1.cnf")
        assert cnf_test.expected_result == "SAT"
        assert cnf_test.max_time_seconds == 10
        assert cnf_test.description == "Easy SAT formula"
        assert cnf_test.category == "easy"
        assert cnf_test.format == "cnf"

        # Check SMT-LIB test case
        smt_test = next(tc for tc in test_cases if tc.name == "smtlib/easy/test1.smt2")
        assert smt_test.expected_result == "SAT"
        assert smt_test.format == "smtlib"

    def test_load_test_cases_missing_file(self, test_local_cmd):
        """Test behavior when expected.yml is missing."""
        # Don't create the file
        assert not test_local_cmd.expected_path.exists()

        # Should raise an error when opening
        with pytest.raises(FileNotFoundError):
            test_local_cmd._load_test_cases()

    def test_load_test_cases_invalid_format(self, test_local_cmd):
        """Test loading with unknown format in expected.yml."""
        content = {
            "unknown_format": {
                "category": {
                    "test.xyz": {
                        "expected_result": "SAT",
                        "max_time_seconds": 10
                    }
                }
            }
        }

        with open(test_local_cmd.expected_path, 'w') as f:
            yaml.dump(content, f)

        test_cases = test_local_cmd._load_test_cases()
        assert len(test_cases) == 0  # Unknown format should be skipped


# ---------------------------------------------------------------------------
# Solver Selection Tests
# ---------------------------------------------------------------------------

class TestGetSolversToTest:
    """Tests for _get_solvers_to_test method."""

    def test_get_solvers_to_test_specific(self, test_local_cmd):
        """Test getting a specific solver by name."""
        solvers = test_local_cmd._get_solvers_to_test("solver1")

        assert len(solvers) == 1
        assert solvers[0].name == "solver1"

    def test_get_solvers_to_test_all(self, test_local_cmd):
        """Test getting all solvers (excluding infrastructure)."""
        solvers = test_local_cmd._get_solvers_to_test(None)

        assert len(solvers) == 2  # solver1 and solver2, not infrastructure
        solver_names = [s.name for s in solvers]
        assert "solver1" in solver_names
        assert "solver2" in solver_names
        assert "satcomp-infrastructure" not in solver_names

    def test_get_solvers_to_test_invalid_name(self, test_local_cmd):
        """Test requesting a non-existent solver."""
        solvers = test_local_cmd._get_solvers_to_test("nonexistent")

        assert len(solvers) == 0


# ---------------------------------------------------------------------------
# Test Filtering Tests
# ---------------------------------------------------------------------------

class TestFilterTestsForSolver:
    """Tests for _filter_tests_for_solver method."""

    def test_filter_tests_for_solver_returns_all(self, test_local_cmd):
        """Test that currently all tests are returned (no filtering)."""
        # Create test cases
        test_cases = [
            TestCase(
                name="cnf/easy/test1.cnf",
                formula_path=Path("test1.cnf"),
                expected_result="SAT",
                max_time_seconds=10,
                description="CNF test",
                category="easy",
                format="cnf"
            ),
            TestCase(
                name="smtlib/easy/test1.smt2",
                formula_path=Path("test1.smt2"),
                expected_result="SAT",
                max_time_seconds=10,
                description="SMT test",
                category="easy",
                format="smtlib"
            )
        ]

        solver = test_local_cmd.ctx.project.solvers[0]
        filtered = test_local_cmd._filter_tests_for_solver(test_cases, solver)

        # Currently returns all tests (no filtering implemented)
        assert len(filtered) == 2
        assert filtered == test_cases


# ---------------------------------------------------------------------------
# Result Matching Tests
# ---------------------------------------------------------------------------

class TestResultMatching:
    """Tests for _result_matches_expected method."""

    def test_result_matches_expected_exact(self, test_local_cmd):
        """Test exact match of results."""
        assert test_local_cmd._result_matches_expected("SAT", "SAT")
        assert test_local_cmd._result_matches_expected("UNSAT", "UNSAT")
        assert test_local_cmd._result_matches_expected("TIMEOUT", "TIMEOUT")

    def test_result_matches_expected_case_insensitive(self, test_local_cmd):
        """Test case-insensitive matching."""
        assert test_local_cmd._result_matches_expected("sat", "SAT")
        assert test_local_cmd._result_matches_expected("UnSaT", "UNSAT")
        assert test_local_cmd._result_matches_expected("timeout", "TIMEOUT")

    def test_result_matches_expected_error_variants(self, test_local_cmd):
        """Test ERROR accepts CRASH and INDETERMINATE."""
        assert test_local_cmd._result_matches_expected("CRASH", "ERROR")
        assert test_local_cmd._result_matches_expected("INDETERMINATE", "ERROR")
        assert test_local_cmd._result_matches_expected("ERROR", "ERROR")

    def test_result_matches_expected_no_match(self, test_local_cmd):
        """Test non-matching results."""
        assert not test_local_cmd._result_matches_expected("SAT", "UNSAT")
        assert not test_local_cmd._result_matches_expected("TIMEOUT", "SAT")
        assert not test_local_cmd._result_matches_expected("CRASH", "SAT")


# ---------------------------------------------------------------------------
# Docker Execution Tests
# ---------------------------------------------------------------------------

class TestRunSingleTest:
    """Tests for _run_single_test method."""

    @patch('subprocess.run')
    @patch('tempfile.TemporaryDirectory')
    @patch('shutil.copy')
    def test_run_single_test_sat(self, mock_copy, mock_tempdir, mock_run, test_local_cmd):
        """Test running a single test that returns SAT."""
        # Setup mocks
        tmpdir = MagicMock()
        tmpdir_path = MagicMock(spec=Path)
        tmpdir.__enter__.return_value = "/tmp/test"
        mock_tempdir.return_value = tmpdir

        # Mock Path operations
        with patch('runner.commands.test_local.Path') as mock_path_cls:
            mock_path = MagicMock()
            mock_path_cls.return_value = mock_path
            mock_path.__truediv__ = MagicMock(return_value=mock_path)
            mock_path.chmod = MagicMock()
            mock_path.touch = MagicMock()
            mock_path.exists.return_value = True

            # Mock subprocess for Docker image check
            mock_run.return_value.returncode = 0

            # Create solver output file
            solver_out = {
                'solver_result_code': SolverResultCode.SAT.value,
                'process_return_code': 0,
                'elapsed_time': 1.5,
                'artifacts': {
                    'stdout_path': '/tmp/test/stdout.log',
                    'stderr_path': '/tmp/test/stderr.log'
                }
            }

            # Mock file operations
            mock_file_content = json.dumps(solver_out)
            with patch('builtins.open', mock_open(read_data=mock_file_content)):
                # Create test case
                test_case = TestCase(
                    name="test1.cnf",
                    formula_path=Path("test1.cnf"),
                    expected_result="SAT",
                    max_time_seconds=10,
                    description="Test",
                    category="easy",
                    format="cnf"
                )

                solver = test_local_cmd.ctx.project.solvers[0]

                # Run test
                result = test_local_cmd._run_single_test(solver, test_case)

        # Assertions
        assert result.actual_result == "SAT"
        assert result.passed is True
        assert result.elapsed_time > 0
        assert result.error_message is None

    @patch('subprocess.run')
    def test_run_single_test_docker_image_missing(self, mock_run, test_local_cmd):
        """Test handling missing Docker image."""
        # Mock Docker image check to fail
        mock_run.return_value.returncode = 1

        test_case = TestCase(
            name="test1.cnf",
            formula_path=Path("test1.cnf"),
            expected_result="SAT",
            max_time_seconds=10,
            description="Test",
            category="easy",
            format="cnf"
        )

        solver = test_local_cmd.ctx.project.solvers[0]

        # Run test
        result = test_local_cmd._run_single_test(solver, test_case)

        # Assertions
        assert result.actual_result == "ERROR"
        assert result.passed is False
        assert "Docker image not found" in result.error_message

    @patch('subprocess.run')
    def test_run_single_test_timeout(self, mock_run, test_local_cmd):
        """Test handling timeout during Docker execution.

        Uses a real temp directory to avoid complex Path mocking issues.
        Only mocks subprocess.run to simulate Docker behavior.
        """
        import tempfile
        import shutil

        # Create a real temp directory with test files
        with tempfile.TemporaryDirectory() as real_tmpdir:
            # Create a real formula file for the test
            formula_file = Path(real_tmpdir) / "test1.cnf"
            formula_file.write_text("p cnf 1 1\n1 0\n")

            # First call succeeds (Docker image check)
            # Second call times out (Docker run)
            # Third call is docker kill (cleanup)
            mock_run.side_effect = [
                MagicMock(returncode=0),  # Image check
                subprocess.TimeoutExpired(cmd="docker", timeout=10),  # Container run
                MagicMock(returncode=0),  # Docker kill (cleanup)
            ]

            test_case = TestCase(
                name="test1.cnf",
                formula_path=formula_file,
                expected_result="TIMEOUT",
                max_time_seconds=5,
                description="Test",
                category="hard",
                format="cnf"
            )

            solver = test_local_cmd.ctx.project.solvers[0]

            # Run test
            result = test_local_cmd._run_single_test(solver, test_case)

            # Assertions
            assert result.actual_result == "TIMEOUT"
            assert result.passed is True  # Expected TIMEOUT
            assert result.elapsed_time > 0


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestExecute:
    """Tests for the main execute method."""

    @patch.object(TestLocalCommand, '_load_test_cases')
    @patch.object(TestLocalCommand, '_get_solvers_to_test')
    @patch.object(TestLocalCommand, '_filter_tests_for_solver')
    @patch.object(TestLocalCommand, '_run_single_test')
    def test_execute_all_pass(self, mock_run, mock_filter, mock_get_solvers,
                             mock_load, test_local_cmd):
        """Test execute when all tests pass."""
        # Setup mocks
        test_cases = [
            TestCase(
                name="test1.cnf",
                formula_path=Path("test1.cnf"),
                expected_result="SAT",
                max_time_seconds=10,
                description="Test 1",
                category="easy",
                format="cnf"
            ),
            TestCase(
                name="test2.cnf",
                formula_path=Path("test2.cnf"),
                expected_result="UNSAT",
                max_time_seconds=10,
                description="Test 2",
                category="easy",
                format="cnf"
            )
        ]

        mock_load.return_value = test_cases
        mock_get_solvers.return_value = [test_local_cmd.ctx.project.solvers[0]]
        mock_filter.return_value = test_cases

        # All tests pass
        mock_run.side_effect = [
            TestResult(
                test_case=test_cases[0],
                actual_result="SAT",
                elapsed_time=1.0,
                passed=True
            ),
            TestResult(
                test_case=test_cases[1],
                actual_result="UNSAT",
                elapsed_time=1.5,
                passed=True
            )
        ]

        # Make expected.yml exist
        test_local_cmd.expected_path.touch()

        # Execute
        result = test_local_cmd.execute()

        # Assertions
        assert result == 0  # All tests passed
        mock_load.assert_called_once()
        mock_get_solvers.assert_called_once_with(None)
        mock_filter.assert_called_once()
        assert mock_run.call_count == 2

    @patch.object(TestLocalCommand, '_load_test_cases')
    @patch.object(TestLocalCommand, '_get_solvers_to_test')
    @patch.object(TestLocalCommand, '_filter_tests_for_solver')
    @patch.object(TestLocalCommand, '_run_single_test')
    def test_execute_some_fail(self, mock_run, mock_filter, mock_get_solvers,
                              mock_load, test_local_cmd):
        """Test execute when some tests fail."""
        # Setup mocks
        test_cases = [
            TestCase(
                name="test1.cnf",
                formula_path=Path("test1.cnf"),
                expected_result="SAT",
                max_time_seconds=10,
                description="Test 1",
                category="easy",
                format="cnf"
            ),
            TestCase(
                name="test2.cnf",
                formula_path=Path("test2.cnf"),
                expected_result="UNSAT",
                max_time_seconds=10,
                description="Test 2",
                category="easy",
                format="cnf"
            )
        ]

        mock_load.return_value = test_cases
        mock_get_solvers.return_value = [test_local_cmd.ctx.project.solvers[0]]
        mock_filter.return_value = test_cases

        # First test passes, second fails
        mock_run.side_effect = [
            TestResult(
                test_case=test_cases[0],
                actual_result="SAT",
                elapsed_time=1.0,
                passed=True
            ),
            TestResult(
                test_case=test_cases[1],
                actual_result="SAT",  # Wrong result
                elapsed_time=1.5,
                passed=False
            )
        ]

        # Make expected.yml exist
        test_local_cmd.expected_path.touch()

        # Execute
        result = test_local_cmd.execute()

        # Assertions
        assert result == 1  # Some tests failed

    def test_execute_missing_expected_file(self, test_local_cmd):
        """Test execute when expected.yml is missing."""
        # Don't create expected.yml
        assert not test_local_cmd.expected_path.exists()

        # Execute
        result = test_local_cmd.execute()

        # Assertions
        assert result == 1  # Error due to missing file

    @patch.object(TestLocalCommand, '_load_test_cases')
    def test_execute_no_test_cases(self, mock_load, test_local_cmd):
        """Test execute when no test cases are found."""
        mock_load.return_value = []

        # Make expected.yml exist
        test_local_cmd.expected_path.touch()

        # Execute
        result = test_local_cmd.execute()

        # Assertions
        assert result == 1  # Error due to no test cases

    @patch.object(TestLocalCommand, '_load_test_cases')
    @patch.object(TestLocalCommand, '_get_solvers_to_test')
    def test_execute_no_solvers(self, mock_get_solvers, mock_load, test_local_cmd):
        """Test execute when no solvers are found."""
        mock_load.return_value = [MagicMock()]  # Some test cases
        mock_get_solvers.return_value = []  # No solvers

        # Make expected.yml exist
        test_local_cmd.expected_path.touch()

        # Execute
        result = test_local_cmd.execute()

        # Assertions
        assert result == 1  # Error due to no solvers

    @patch.object(TestLocalCommand, '_load_test_cases')
    @patch.object(TestLocalCommand, '_get_solvers_to_test')
    @patch.object(TestLocalCommand, '_filter_tests_for_solver')
    @patch.object(TestLocalCommand, '_run_single_test')
    def test_execute_with_specific_solver(self, mock_run, mock_filter,
                                         mock_get_solvers, mock_load, test_local_cmd):
        """Test execute with a specific solver name."""
        # Setup mocks
        test_cases = [MagicMock()]
        mock_load.return_value = test_cases
        mock_get_solvers.return_value = [test_local_cmd.ctx.project.solvers[0]]
        mock_filter.return_value = test_cases

        mock_run.return_value = TestResult(
            test_case=test_cases[0],
            actual_result="SAT",
            elapsed_time=1.0,
            passed=True
        )

        # Make expected.yml exist
        test_local_cmd.expected_path.touch()

        # Execute with specific solver
        result = test_local_cmd.execute(solver_name="solver1")

        # Assertions
        assert result == 0
        mock_get_solvers.assert_called_once_with("solver1")


# ---------------------------------------------------------------------------
# TestCase and TestResult Dataclass Tests
# ---------------------------------------------------------------------------

class TestDataclasses:
    """Tests for TestCase and TestResult dataclasses."""

    def test_test_case_creation(self):
        """Test creating a TestCase instance."""
        tc = TestCase(
            name="test.cnf",
            formula_path=Path("/path/to/test.cnf"),
            expected_result="SAT",
            max_time_seconds=10,
            description="Test description",
            category="easy",
            format="cnf"
        )

        assert tc.name == "test.cnf"
        assert tc.expected_result == "SAT"
        assert tc.max_time_seconds == 10
        assert tc.category == "easy"
        assert tc.format == "cnf"

    def test_test_result_creation(self):
        """Test creating a TestResult instance."""
        tc = TestCase(
            name="test.cnf",
            formula_path=Path("/path/to/test.cnf"),
            expected_result="SAT",
            max_time_seconds=10,
            description="Test",
            category="easy",
            format="cnf"
        )

        result = TestResult(
            test_case=tc,
            actual_result="SAT",
            elapsed_time=1.5,
            passed=True,
            error_message=None
        )

        assert result.test_case == tc
        assert result.actual_result == "SAT"
        assert result.elapsed_time == 1.5
        assert result.passed is True
        assert result.error_message is None

    def test_test_result_with_error(self):
        """Test creating a TestResult with an error message."""
        tc = MagicMock()

        result = TestResult(
            test_case=tc,
            actual_result="ERROR",
            elapsed_time=0.0,
            passed=False,
            error_message="Docker image not found"
        )

        assert result.actual_result == "ERROR"
        assert result.passed is False
        assert result.error_message == "Docker image not found"

    def test_test_result_with_output_fields(self):
        """Test creating a TestResult with stdout/stderr and result codes."""
        tc = MagicMock()

        result = TestResult(
            test_case=tc,
            actual_result="SAT",
            elapsed_time=1.5,
            passed=True,
            stdout="s SATISFIABLE\n",
            stderr="Running solver...\n",
            solver_result_code=10,
            process_return_code=0,
        )

        assert result.stdout == "s SATISFIABLE\n"
        assert result.stderr == "Running solver...\n"
        assert result.solver_result_code == 10
        assert result.process_return_code == 0


# ---------------------------------------------------------------------------
# Path Resolution Tests
# ---------------------------------------------------------------------------

class TestPathResolution:
    """Tests for formula directory and expected.yml path resolution."""

    def test_default_paths_without_job_manager(self, ctx, tmp_path):
        """Test default paths when no job manager is provided."""
        cmd = TestLocalCommand(ctx)
        cmd.project_root = tmp_path

        # Re-resolve paths with new project_root
        cmd.test_formulas_path = cmd._resolve_formula_dir()
        cmd.expected_path = cmd._resolve_expected_path()

        assert cmd.test_formulas_path == tmp_path / "examples/formulas"
        assert cmd.expected_path == tmp_path / "examples/formulas" / "expected.yml"

    def test_custom_formula_dir_from_job_manager(self, ctx, tmp_path):
        """Test formula directory from job manager."""
        # Create custom formula directory
        custom_formulas = tmp_path / "custom_formulas"
        custom_formulas.mkdir()
        (custom_formulas / "expected.yml").touch()

        # Create a mock job manager
        job_manager = MagicMock()
        job_manager.formula_dir_test_local = custom_formulas
        job_manager.expected_file_test_local = None

        cmd = TestLocalCommand(ctx, job_manager=job_manager)
        cmd.project_root = tmp_path

        assert cmd.test_formulas_path == custom_formulas
        # expected.yml should be found in custom formula dir
        assert cmd.expected_path == custom_formulas / "expected.yml"

    def test_explicit_expected_file_from_job_manager(self, ctx, tmp_path):
        """Test explicit expected.yml path from job manager."""
        custom_expected = tmp_path / "my_expected.yml"
        custom_expected.touch()

        job_manager = MagicMock()
        job_manager.formula_dir_test_local = None
        job_manager.expected_file_test_local = custom_expected

        cmd = TestLocalCommand(ctx, job_manager=job_manager)
        cmd.project_root = tmp_path

        assert cmd.expected_path == custom_expected

    def test_explicit_expected_overrides_formula_dir(self, ctx, tmp_path):
        """Test that explicit expected.yml overrides formula dir's expected.yml."""
        custom_formulas = tmp_path / "custom_formulas"
        custom_formulas.mkdir()
        (custom_formulas / "expected.yml").touch()

        explicit_expected = tmp_path / "explicit_expected.yml"
        explicit_expected.touch()

        job_manager = MagicMock()
        job_manager.formula_dir_test_local = custom_formulas
        job_manager.expected_file_test_local = explicit_expected

        cmd = TestLocalCommand(ctx, job_manager=job_manager)
        cmd.project_root = tmp_path

        assert cmd.test_formulas_path == custom_formulas
        assert cmd.expected_path == explicit_expected


# ---------------------------------------------------------------------------
# Results Writing Tests
# ---------------------------------------------------------------------------

class TestWriteResults:
    """Tests for _write_results method."""

    def test_write_results_creates_directory_structure(self, test_local_cmd, tmp_path):
        """Test that _write_results creates expected directory structure."""
        results_dir = tmp_path / "results"

        # Create test results
        tc1 = TestCase(
            name="cnf/easy/test1.cnf",
            formula_path=Path("test1.cnf"),
            expected_result="SAT",
            max_time_seconds=10,
            description="Test 1",
            category="easy",
            format="cnf"
        )

        result1 = TestResult(
            test_case=tc1,
            actual_result="SAT",
            elapsed_time=1.5,
            passed=True,
            stdout="s SATISFIABLE\n",
            stderr="Running...\n",
            solver_result_code=10,
            process_return_code=0,
        )

        all_results = {"solver1": [result1]}

        # Write results
        test_local_cmd._write_results(results_dir, all_results)

        # Verify directory structure
        assert results_dir.exists()
        assert (results_dir / "summary.yml").exists()
        assert (results_dir / "solver1").is_dir()

        # Check formula directory (name sanitized)
        formula_dir = results_dir / "solver1" / "cnf_easy_test1.cnf"
        assert formula_dir.is_dir()
        assert (formula_dir / "solver_out.json").exists()
        assert (formula_dir / "stdout.log").exists()
        assert (formula_dir / "stderr.log").exists()

    def test_write_results_summary_format(self, test_local_cmd, tmp_path):
        """Test that summary.yml has correct format."""
        results_dir = tmp_path / "results"

        tc1 = TestCase(
            name="cnf/easy/test1.cnf",
            formula_path=Path("test1.cnf"),
            expected_result="SAT",
            max_time_seconds=10,
            description="Test 1",
            category="easy",
            format="cnf"
        )

        tc2 = TestCase(
            name="cnf/easy/test2.cnf",
            formula_path=Path("test2.cnf"),
            expected_result="UNSAT",
            max_time_seconds=10,
            description="Test 2",
            category="easy",
            format="cnf"
        )

        result1 = TestResult(
            test_case=tc1, actual_result="SAT", elapsed_time=1.0,
            passed=True, solver_result_code=10, process_return_code=0,
        )
        result2 = TestResult(
            test_case=tc2, actual_result="SAT", elapsed_time=2.0,
            passed=False, solver_result_code=10, process_return_code=0,
        )

        all_results = {"solver1": [result1, result2]}

        test_local_cmd._write_results(results_dir, all_results)

        # Read and verify summary
        summary = yaml.safe_load((results_dir / "summary.yml").read_text())

        assert "timestamp" in summary
        assert summary["total_passed"] == 1
        assert summary["total_failed"] == 1
        assert "solver1" in summary["solvers"]
        assert summary["solvers"]["solver1"]["passed"] == 1
        assert summary["solvers"]["solver1"]["failed"] == 1
        assert len(summary["solvers"]["solver1"]["tests"]) == 2

    def test_write_results_solver_out_json_format(self, test_local_cmd, tmp_path):
        """Test that solver_out.json has AWS-compatible format."""
        import json
        results_dir = tmp_path / "results"

        tc = TestCase(
            name="cnf/easy/test1.cnf",
            formula_path=Path("test1.cnf"),
            expected_result="SAT",
            max_time_seconds=10,
            description="Test",
            category="easy",
            format="cnf"
        )

        result = TestResult(
            test_case=tc,
            actual_result="SAT",
            elapsed_time=1.5,
            passed=True,
            stdout="s SATISFIABLE\n",
            stderr="",
            solver_result_code=10,
            process_return_code=0,
        )

        test_local_cmd._write_results(results_dir, {"solver1": [result]})

        # Read solver_out.json
        solver_out_path = results_dir / "solver1" / "cnf_easy_test1.cnf" / "solver_out.json"
        solver_out = json.loads(solver_out_path.read_text())

        assert solver_out["solver_result_code"] == 10
        assert solver_out["process_return_code"] == 0
        assert solver_out["elapsed_time"] == 1.5
        assert "artifacts" in solver_out
        assert "stdout_path" in solver_out["artifacts"]
        assert "stderr_path" in solver_out["artifacts"]

    def test_write_results_stdout_stderr_content(self, test_local_cmd, tmp_path):
        """Test that stdout.log and stderr.log contain correct content."""
        results_dir = tmp_path / "results"

        tc = TestCase(
            name="test.cnf",
            formula_path=Path("test.cnf"),
            expected_result="SAT",
            max_time_seconds=10,
            description="Test",
            category="easy",
            format="cnf"
        )

        result = TestResult(
            test_case=tc,
            actual_result="SAT",
            elapsed_time=1.0,
            passed=True,
            stdout="s SATISFIABLE\nv 1 2 -3 0\n",
            stderr="Solver started\nSolver finished\n",
            solver_result_code=10,
            process_return_code=0,
        )

        test_local_cmd._write_results(results_dir, {"solver1": [result]})

        formula_dir = results_dir / "solver1" / "test.cnf"
        assert (formula_dir / "stdout.log").read_text() == "s SATISFIABLE\nv 1 2 -3 0\n"
        assert (formula_dir / "stderr.log").read_text() == "Solver started\nSolver finished\n"

    def test_write_results_multiple_solvers(self, test_local_cmd, tmp_path):
        """Test writing results for multiple solvers."""
        results_dir = tmp_path / "results"

        tc = TestCase(
            name="test.cnf",
            formula_path=Path("test.cnf"),
            expected_result="SAT",
            max_time_seconds=10,
            description="Test",
            category="easy",
            format="cnf"
        )

        result1 = TestResult(
            test_case=tc, actual_result="SAT", elapsed_time=1.0,
            passed=True, solver_result_code=10, process_return_code=0,
        )
        result2 = TestResult(
            test_case=tc, actual_result="UNSAT", elapsed_time=2.0,
            passed=False, solver_result_code=20, process_return_code=0,
        )

        all_results = {"solver1": [result1], "solver2": [result2]}

        test_local_cmd._write_results(results_dir, all_results)

        # Verify both solver directories exist
        assert (results_dir / "solver1").is_dir()
        assert (results_dir / "solver2").is_dir()

        # Verify summary has both solvers
        summary = yaml.safe_load((results_dir / "summary.yml").read_text())
        assert summary["total_passed"] == 1
        assert summary["total_failed"] == 1
        assert "solver1" in summary["solvers"]
        assert "solver2" in summary["solvers"]