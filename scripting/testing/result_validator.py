"""Validates solver results against expected outcomes."""

from common.solver_io import CompetitionQueueOutput, SolverResultCode

from .test_models import TestCaseDefinition, TestCaseResult


class ResultValidator:
    """Validates a CompetitionQueueOutput against a TestCaseDefinition."""

    @staticmethod
    def validate(test_case: TestCaseDefinition, output: CompetitionQueueOutput) -> TestCaseResult:
        """Check if the solver result matches the expected outcome.

        A test passes if:
        - The solver_result_code is in the expected_results set, OR
        - For timeout-type test cases, the elapsed time >= configured timeout
        """
        result_code = output.solver_result_code
        elapsed_ms = output.solver_runtime_millis

        # Check if result code is directly in the expected set
        passed = result_code in test_case.expected_results

        # Timeout special case: if the test expects TIMEOUT and elapsed time
        # meets or exceeds the configured timeout, it passes regardless of result code
        if not passed and SolverResultCode.TIMEOUT in test_case.expected_results:
            timeout_ms = test_case.timeout_secs * 1000
            if elapsed_ms >= timeout_ms:
                passed = True

        error_message = None
        if not passed:
            expected_str = ", ".join(str(r) for r in test_case.expected_results)
            error_message = f"Expected one of [{expected_str}] but got {result_code} " f"(elapsed: {elapsed_ms}ms)"

        return TestCaseResult(
            test_case=test_case,
            solver_result_code=result_code,
            elapsed_time_ms=elapsed_ms,
            passed=passed,
            error_message=error_message,
        )
