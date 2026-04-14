"""Property-based tests for ResultValidator.

**Validates: Requirements 2.2, 2.3, 3.2, 3.3, 4.3, 4.4, 5.2, 6.2, 6.3, 6.4**
Feature: solver-acceptance-testing, Property 2: Result validation correctness
"""

import pytest
from common.solver_io import CompetitionQueueOutput, SolverResultCode
from hypothesis import given, settings
from hypothesis import strategies as st
from testing.result_validator import ResultValidator
from testing.test_models import TestCaseDefinition

# All possible SolverResultCode values
ALL_RESULT_CODES = list(SolverResultCode)

# Strategy: generate a non-empty subset of SolverResultCode values
result_code_set_strategy = st.frozensets(st.sampled_from(ALL_RESULT_CODES), min_size=1).map(set)

# Strategy: generate a single SolverResultCode
result_code_strategy = st.sampled_from(ALL_RESULT_CODES)


def make_test_case(expected_results, timeout_secs=30):
    return TestCaseDefinition(
        name="test",
        benchmark_path="/tmp/test.cnf",
        expected_results=expected_results,
        timeout_secs=timeout_secs,
    )


def make_output(result_code, runtime_millis=1000):
    return CompetitionQueueOutput(
        solver="test-solver",
        process_return_code=0,
        solver_result_code=result_code,
        solver_runtime_millis=runtime_millis,
        job_time_start="2025-01-01",
        formula_s3_uri="s3://test/formula.cnf",
        upload_dir_uri="s3://test/output/",
    )


@settings(max_examples=100)
@given(
    expected=result_code_set_strategy,
    actual=result_code_strategy,
    elapsed_ms=st.integers(min_value=0, max_value=300_000),
)
def test_validate_passes_iff_result_in_expected_set(expected, actual, elapsed_ms):
    """Property 2: ResultValidator.validate() returns passed=True iff result code
    is in the expected set, with timeout elapsed-time special case.

    **Validates: Requirements 2.2, 3.2, 4.3, 5.2, 6.2**
    """
    timeout_secs = 30
    tc = make_test_case(expected, timeout_secs=timeout_secs)
    output = make_output(actual, runtime_millis=elapsed_ms)

    result = ResultValidator.validate(tc, output)

    # Determine expected pass/fail
    direct_match = actual in expected
    timeout_special = SolverResultCode.TIMEOUT in expected and elapsed_ms >= timeout_secs * 1000
    should_pass = direct_match or timeout_special

    assert result.passed == should_pass, (
        f"Expected passed={should_pass} but got passed={result.passed}. "
        f"actual={actual}, expected_set={expected}, elapsed_ms={elapsed_ms}"
    )
    assert result.solver_result_code == actual
    assert result.elapsed_time_ms == elapsed_ms
