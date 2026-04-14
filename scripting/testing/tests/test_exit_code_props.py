"""Property-based tests for TestReport exit code.

**Validates: Requirements 7.2, 7.3**
Feature: solver-acceptance-testing, Property 4: Exit code reflects overall pass/fail
"""

import pytest
from common.solver_io import SolverResultCode
from hypothesis import given, settings
from hypothesis import strategies as st
from testing.test_models import TestCaseDefinition, TestCaseResult, TestReport

ALL_RESULT_CODES = list(SolverResultCode)

# Strategy: generate a TestCaseResult with a random passed flag
test_case_result_strategy = st.builds(
    TestCaseResult,
    test_case=st.just(
        TestCaseDefinition(
            name="test",
            benchmark_path="/tmp/test.cnf",
            expected_results={SolverResultCode.SAT},
            timeout_secs=30,
        )
    ),
    solver_result_code=st.sampled_from(ALL_RESULT_CODES),
    elapsed_time_ms=st.integers(min_value=0, max_value=300_000),
    passed=st.booleans(),
    error_message=st.none(),
)


@settings(max_examples=100)
@given(results=st.lists(test_case_result_strategy, min_size=0, max_size=20))
def test_exit_code_zero_iff_all_passed(results):
    """Property 4: Exit code is 0 iff all tests passed.

    **Validates: Requirements 7.2, 7.3**
    """
    report = TestReport(
        solver_name="test-solver",
        results=results,
        timeout_secs=30,
    )

    all_passed = len(results) > 0 and all(r.passed for r in results)
    expected_exit_code = 0 if all_passed else 1

    assert report.get_exit_code() == expected_exit_code, (
        f"Expected exit code {expected_exit_code} but got {report.get_exit_code()}. "
        f"all_passed={all_passed}, num_results={len(results)}"
    )
    assert report.all_passed == all_passed
