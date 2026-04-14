"""Property-based tests for TestCaseRegistry file discovery and classification.

**Validates: Requirements 11.2, 11.3, 11.4**
Feature: solver-acceptance-testing, Property 8: Benchmark file discovery and classification
"""

import os
import tempfile
from pathlib import Path

import pytest
from common.solver_io import SolverResultCode
from hypothesis import given, settings
from hypothesis import strategies as st
from testing.test_registry import TestCaseRegistry

# The naming convention from the registry
NAMING_CONVENTION = {
    "sat_": {SolverResultCode.SAT},
    "unsat_": {SolverResultCode.UNSAT},
    "timeout_": {SolverResultCode.TIMEOUT},
    "oom_": {SolverResultCode.CRASH, SolverResultCode.INDETERMINATE},
    "malformed_": {SolverResultCode.UNKNOWN, SolverResultCode.INDETERMINATE, SolverResultCode.CRASH},
}

PREFIXES = list(NAMING_CONVENTION.keys())
EXTENSIONS = [".cnf", ".smt2"]

# Strategy: generate a valid prefix
prefix_strategy = st.sampled_from(PREFIXES)

# Strategy: generate a valid extension
extension_strategy = st.sampled_from(EXTENSIONS)

# Strategy: generate a suffix (alphanumeric, non-empty)
suffix_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=20,
)

# Strategy: generate a subdirectory (cnf or smtlib)
subdir_strategy = st.sampled_from(["cnf", "smtlib"])


@settings(max_examples=100)
@given(
    prefix=prefix_strategy,
    suffix=suffix_strategy,
    ext=extension_strategy,
    subdir=subdir_strategy,
)
def test_recognized_files_map_to_correct_expected_sets(prefix, suffix, ext, subdir):
    """Property 8: Files with recognized prefixes and valid extensions are
    discovered and mapped to the correct expected result code sets.

    **Validates: Requirements 11.2, 11.3, 11.4**
    """
    filename = f"{prefix}{suffix}{ext}"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create the subdirectory and file
        formula_dir = Path(tmpdir) / subdir
        formula_dir.mkdir(parents=True)
        filepath = formula_dir / filename
        filepath.write_text("p cnf 1 1\n1 0\n")

        registry = TestCaseRegistry(tmpdir, timeout_secs=30)
        test_cases = registry.discover_test_cases()

        # Should find exactly one test case
        assert len(test_cases) == 1, f"Expected 1 test case for {filename} in {subdir}/, got {len(test_cases)}"

        tc = test_cases[0]
        expected_set = NAMING_CONVENTION[prefix]
        assert (
            tc.expected_results == expected_set
        ), f"For prefix '{prefix}', expected {expected_set} but got {tc.expected_results}"
        assert tc.timeout_secs == 30
        assert tc.benchmark_path == str(filepath)


@settings(max_examples=100)
@given(
    name=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Nd")),
        min_size=1,
        max_size=20,
    ).filter(lambda n: not any(n.startswith(p) for p in PREFIXES)),
    ext=extension_strategy,
)
def test_unrecognized_prefix_files_are_ignored(name, ext):
    """Files without recognized prefixes should not be discovered.

    **Validates: Requirements 11.4**
    """
    filename = f"{name}{ext}"

    with tempfile.TemporaryDirectory() as tmpdir:
        formula_dir = Path(tmpdir) / "cnf"
        formula_dir.mkdir(parents=True)
        filepath = formula_dir / filename
        filepath.write_text("p cnf 1 1\n1 0\n")

        registry = TestCaseRegistry(tmpdir, timeout_secs=30)
        test_cases = registry.discover_test_cases()

        assert len(test_cases) == 0, f"Expected 0 test cases for unrecognized file '{filename}', got {len(test_cases)}"
