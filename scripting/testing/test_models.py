"""Data models for the solver acceptance testing framework."""

from dataclasses import dataclass, field
from typing import List, Optional, Set

from common.solver_io import SolverResultCode
from utils.tabular import Tabular


@dataclass
class TestCaseDefinition:
    """Defines a single test case with its expected outcomes."""

    name: str
    benchmark_path: str
    expected_results: Set[SolverResultCode]
    timeout_secs: int
    memory_limit_mb: Optional[int] = None


@dataclass
class TestCaseResult:
    """Result of running a single test case."""

    test_case: TestCaseDefinition
    solver_result_code: SolverResultCode
    elapsed_time_ms: int
    passed: bool
    error_message: Optional[str] = None


@dataclass
class TestReport:
    """Aggregated report of all test case results for a solver."""

    solver_name: str
    results: List[TestCaseResult] = field(default_factory=list)
    timeout_secs: int = 30

    @property
    def all_passed(self) -> bool:
        return len(self.results) > 0 and all(r.passed for r in self.results)

    def print_report(self) -> None:
        """Print a human-readable tabular report to stdout."""
        print(f"\nSolver Acceptance Test Report: {self.solver_name}")
        print("=" * 60)

        table = Tabular(4, max_column_length=None)
        table.add_headers(["Test Case", "Result", "Time (ms)", "Status"])

        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            table.add_row(
                [
                    r.test_case.name,
                    str(r.solver_result_code),
                    str(r.elapsed_time_ms),
                    status,
                ]
            )

        table.print()

        passed_count = sum(1 for r in self.results if r.passed)
        total_count = len(self.results)
        print("-" * 60)
        if self.all_passed:
            print(f"Result: ALL TESTS PASSED ({passed_count}/{total_count})")
        else:
            print(f"Result: SOME TESTS FAILED ({passed_count}/{total_count} passed)")

    def get_exit_code(self) -> int:
        """Return 0 if all tests passed, 1 otherwise."""
        return 0 if self.all_passed else 1
