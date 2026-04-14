"""Unit tests for TestCaseRegistry."""

import tempfile
from pathlib import Path

import pytest
from common.solver_io import SolverResultCode
from testing.test_registry import TestCaseRegistry


def _create_formula_dir(tmpdir, files):
    """Helper: create formula files in a temp directory structure."""
    base = Path(tmpdir)
    for relpath in files:
        filepath = base / relpath
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text("p cnf 1 1\n1 0\n")
    return base


class TestDefaultTestCases:
    """Verify default test cases include all 5 categories."""

    def test_all_five_categories_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = [
                "cnf/sat_easy.cnf",
                "cnf/unsat_easy.cnf",
                "cnf/timeout_hard.cnf",
                "cnf/oom_big.cnf",
                "cnf/malformed_bad.cnf",
            ]
            base = _create_formula_dir(tmpdir, files)
            registry = TestCaseRegistry(base)
            test_cases = registry.get_default_test_cases()

            assert len(test_cases) == 5
            prefixes_found = set()
            for tc in test_cases:
                stem = Path(tc.benchmark_path).stem
                for prefix in TestCaseRegistry.NAMING_CONVENTION:
                    if stem.startswith(prefix):
                        prefixes_found.add(prefix)
            assert prefixes_found == set(TestCaseRegistry.NAMING_CONVENTION.keys())

    def test_missing_category_raises_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Only 3 of 5 categories
            files = [
                "cnf/sat_easy.cnf",
                "cnf/unsat_easy.cnf",
                "cnf/timeout_hard.cnf",
            ]
            base = _create_formula_dir(tmpdir, files)
            registry = TestCaseRegistry(base)
            with pytest.raises(FileNotFoundError, match="Missing required benchmark categories"):
                registry.get_default_test_cases()


class TestPrefixFiltering:
    """Verify files without recognized prefixes are ignored."""

    def test_unrecognized_prefix_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = [
                "cnf/random_formula.cnf",
                "cnf/my_solver_test.cnf",
                "cnf/formula123.cnf",
            ]
            base = _create_formula_dir(tmpdir, files)
            registry = TestCaseRegistry(base)
            test_cases = registry.discover_test_cases()
            assert len(test_cases) == 0

    def test_recognized_prefix_discovered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = ["cnf/sat_simple.cnf"]
            base = _create_formula_dir(tmpdir, files)
            registry = TestCaseRegistry(base)
            test_cases = registry.discover_test_cases()
            assert len(test_cases) == 1
            assert test_cases[0].expected_results == {SolverResultCode.SAT}

    def test_invalid_extension_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = ["cnf/sat_easy.txt", "cnf/unsat_easy.dimacs"]
            base = _create_formula_dir(tmpdir, files)
            registry = TestCaseRegistry(base)
            test_cases = registry.discover_test_cases()
            assert len(test_cases) == 0


class TestExtensionSupport:
    """Verify both .cnf and .smt2 extensions are supported."""

    def test_cnf_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = ["cnf/sat_test.cnf"]
            base = _create_formula_dir(tmpdir, files)
            registry = TestCaseRegistry(base)
            test_cases = registry.discover_test_cases()
            assert len(test_cases) == 1

    def test_smt2_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = ["smtlib/sat_test.smt2"]
            base = _create_formula_dir(tmpdir, files)
            registry = TestCaseRegistry(base)
            test_cases = registry.discover_test_cases()
            assert len(test_cases) == 1

    def test_both_formats_discovered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = [
                "cnf/sat_cnf.cnf",
                "smtlib/sat_smt.smt2",
            ]
            base = _create_formula_dir(tmpdir, files)
            registry = TestCaseRegistry(base)
            test_cases = registry.discover_test_cases()
            assert len(test_cases) == 2

    def test_timeout_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = ["cnf/sat_test.cnf"]
            base = _create_formula_dir(tmpdir, files)
            registry = TestCaseRegistry(base, timeout_secs=60)
            test_cases = registry.discover_test_cases()
            assert test_cases[0].timeout_secs == 60
