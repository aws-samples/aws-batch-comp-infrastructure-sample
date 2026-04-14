"""Unit tests for TestReport."""

import pytest
from common.solver_io import SolverResultCode
from testing.test_models import TestCaseDefinition, TestCaseResult, TestReport


def _make_tc(name="test"):
    return TestCaseDefinition(
        name=name,
        benchmark_path=f"/tmp/{name}.cnf",
        expected_results={SolverResultCode.SAT},
        timeout_secs=30,
    )


def _make_result(name="test", code=SolverResultCode.SAT, ms=100, passed=True):
    return TestCaseResult(
        test_case=_make_tc(name),
        solver_result_code=code,
        elapsed_time_ms=ms,
        passed=passed,
    )


class TestReportEdgeCases:
    """Verify report edge cases: all pass, all fail, mixed, empty."""

    def test_all_pass(self):
        report = TestReport(
            solver_name="solver-a",
            results=[
                _make_result("sat", SolverResultCode.SAT, 100, True),
                _make_result("unsat", SolverResultCode.UNSAT, 200, True),
            ],
        )
        assert report.all_passed is True
        assert report.get_exit_code() == 0

    def test_all_fail(self):
        report = TestReport(
            solver_name="solver-b",
            results=[
                _make_result("sat", SolverResultCode.CRASH, 100, False),
                _make_result("unsat", SolverResultCode.TIMEOUT, 200, False),
            ],
        )
        assert report.all_passed is False
        assert report.get_exit_code() == 1

    def test_mixed_results(self):
        report = TestReport(
            solver_name="solver-c",
            results=[
                _make_result("sat", SolverResultCode.SAT, 100, True),
                _make_result("unsat", SolverResultCode.CRASH, 200, False),
            ],
        )
        assert report.all_passed is False
        assert report.get_exit_code() == 1

    def test_empty_results(self):
        report = TestReport(solver_name="solver-d", results=[])
        assert report.all_passed is False
        assert report.get_exit_code() == 1


class TestReportOutput:
    """Verify tabular output contains expected fields."""

    def test_print_report_contains_solver_name(self, capsys):
        report = TestReport(
            solver_name="my-solver",
            results=[_make_result("sat", SolverResultCode.SAT, 142, True)],
        )
        report.print_report()
        output = capsys.readouterr().out
        assert "my-solver" in output

    def test_print_report_contains_result_code(self, capsys):
        report = TestReport(
            solver_name="solver",
            results=[_make_result("sat", SolverResultCode.SAT, 142, True)],
        )
        report.print_report()
        output = capsys.readouterr().out
        assert "SAT" in output

    def test_print_report_contains_time(self, capsys):
        report = TestReport(
            solver_name="solver",
            results=[_make_result("sat", SolverResultCode.SAT, 142, True)],
        )
        report.print_report()
        output = capsys.readouterr().out
        assert "142" in output

    def test_print_report_contains_pass_status(self, capsys):
        report = TestReport(
            solver_name="solver",
            results=[
                _make_result("sat", SolverResultCode.SAT, 100, True),
                _make_result("unsat", SolverResultCode.CRASH, 200, False),
            ],
        )
        report.print_report()
        output = capsys.readouterr().out
        assert "PASS" in output
        assert "FAIL" in output

    def test_print_report_all_passed_message(self, capsys):
        report = TestReport(
            solver_name="solver",
            results=[_make_result("sat", SolverResultCode.SAT, 100, True)],
        )
        report.print_report()
        output = capsys.readouterr().out
        assert "ALL TESTS PASSED" in output

    def test_print_report_some_failed_message(self, capsys):
        report = TestReport(
            solver_name="solver",
            results=[_make_result("sat", SolverResultCode.CRASH, 100, False)],
        )
        report.print_report()
        output = capsys.readouterr().out
        assert "SOME TESTS FAILED" in output

    def test_print_report_contains_test_case_name(self, capsys):
        report = TestReport(
            solver_name="solver",
            results=[_make_result("easy_sat", SolverResultCode.SAT, 100, True)],
        )
        report.print_report()
        output = capsys.readouterr().out
        assert "easy_sat" in output
