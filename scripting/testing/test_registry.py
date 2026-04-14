"""Registry for discovering and classifying test cases from benchmark files."""

import os
from pathlib import Path
from typing import Dict, List, Set

from common.solver_io import SolverResultCode

from .test_models import TestCaseDefinition


class TestCaseRegistry:
    """Discovers test cases by scanning formula directories for files with recognized prefixes."""

    NAMING_CONVENTION: Dict[str, Set[SolverResultCode]] = {
        "sat_": {SolverResultCode.SAT},
        "unsat_": {SolverResultCode.UNSAT},
        "timeout_": {SolverResultCode.TIMEOUT},
        "oom_": {SolverResultCode.CRASH, SolverResultCode.INDETERMINATE},
        "malformed_": {SolverResultCode.UNKNOWN, SolverResultCode.INDETERMINATE, SolverResultCode.CRASH},
    }

    VALID_EXTENSIONS = {".cnf", ".smt2"}

    def __init__(self, formula_base_dir: str | Path, timeout_secs: int = 30):
        self.formula_base_dir = Path(formula_base_dir)
        self.timeout_secs = timeout_secs

    def _classify_file(self, filename: str) -> Set[SolverResultCode] | None:
        """Return the expected result set for a filename, or None if unrecognized."""
        stem = Path(filename).stem
        ext = Path(filename).suffix
        if ext not in self.VALID_EXTENSIONS:
            return None
        for prefix, expected in self.NAMING_CONVENTION.items():
            if stem.startswith(prefix) or filename.startswith(prefix):
                return expected
        return None

    def discover_test_cases(self) -> List[TestCaseDefinition]:
        """Scan formula directories and return test case definitions for recognized files."""
        test_cases: List[TestCaseDefinition] = []
        subdirs = ["cnf", "smtlib"]

        for subdir in subdirs:
            scan_dir = self.formula_base_dir / subdir
            if not scan_dir.exists():
                continue
            for root, _, files in os.walk(scan_dir):
                for filename in sorted(files):
                    expected = self._classify_file(filename)
                    if expected is None:
                        continue
                    filepath = Path(root) / filename
                    rel_path = filepath.relative_to(self.formula_base_dir)
                    name = Path(filename).stem
                    test_cases.append(
                        TestCaseDefinition(
                            name=name,
                            benchmark_path=str(filepath),
                            expected_results=expected,
                            timeout_secs=self.timeout_secs,
                        )
                    )

        return test_cases

    def get_default_test_cases(self) -> List[TestCaseDefinition]:
        """Return discovered test cases, raising an error if minimum coverage is missing."""
        test_cases = self.discover_test_cases()
        found_prefixes = set()
        for tc in test_cases:
            for prefix in self.NAMING_CONVENTION:
                if Path(tc.benchmark_path).stem.startswith(prefix):
                    found_prefixes.add(prefix)
                    break

        missing = set(self.NAMING_CONVENTION.keys()) - found_prefixes
        if missing:
            raise FileNotFoundError(
                f"Missing required benchmark categories: {', '.join(sorted(missing))}. "
                f"Ensure test_formulas/ contains files with these prefixes."
            )
        return test_cases
