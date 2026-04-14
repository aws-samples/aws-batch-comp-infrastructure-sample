"""
Simple test solver for validating the test-local command.

This solver doesn't actually solve formulas - it determines the result
based on the formula filename, which allows testing the infrastructure
without requiring a real SAT/SMT solver.

Expected behavior:
- Files containing "sat" in the path (not "unsat"): returns SAT
- Files containing "unsat" in the path: returns UNSAT
- Files in "hard" directory: sleeps to simulate timeout
- Files in "malformed" directory: raises an error
"""

import sys
import time
from pathlib import Path
from typing import List

from common.solver_io import SolverInput, SolverResultCode


def get_run_command(s_input: SolverInput) -> List[str]:
    """Return command to run the test solver."""
    formula_path = str(s_input.formula_file)
    timeout = s_input.timeout_seconds

    # Parse test category from solver arguments
    category = "easy"  # default
    for arg in s_input.solver_argument_list:
        if arg.startswith("--test-category="):
            category = arg.split("=")[1]

    # Use Python to run this module as the solver
    # Pass the formula path, timeout, and category as arguments
    return [
        "python3",
        "-c",
        f"""
import sys
import time
from pathlib import Path

formula_path = "{formula_path}"
timeout = {timeout}
category = "{category}"
path_lower = formula_path.lower()
name = Path(formula_path).stem.lower()

# Detect category from filename prefix if not set via args
if category == "easy":
    if name.startswith("timeout_") or "/hard/" in path_lower:
        category = "hard"
    elif name.startswith("malformed_") or "/malformed/" in path_lower:
        category = "malformed"
    elif name.startswith("oom_"):
        category = "oom"

if category == "malformed":
    print("Error: Malformed formula file detected", file=sys.stderr)
    sys.exit(1)

if category == "oom":
    print("c Simulating out-of-memory", file=sys.stderr)
    sys.exit(1)

if category == "hard":
    print("c Solving hard formula...")
    time.sleep(timeout + 10)
    print("s UNKNOWN")
    sys.exit(0)

if name.startswith("unsat") or "unsat" in path_lower:
    print("c Test solver: detected UNSAT formula")
    print("s UNSATISFIABLE")
else:
    print("c Test solver: detected SAT formula")
    print("s SATISFIABLE")
""",
    ]


def get_solver_result(stdout_path: Path) -> SolverResultCode:
    """Parse solver output to determine result."""
    if not stdout_path.exists():
        return SolverResultCode.INDETERMINATE

    with open(stdout_path, "r") as f:
        content = f.read()

    # Check for standard SAT solver output format
    if "s SATISFIABLE" in content:
        return SolverResultCode.SAT
    elif "s UNSATISFIABLE" in content:
        return SolverResultCode.UNSAT
    elif "s UNKNOWN" in content:
        return SolverResultCode.UNKNOWN

    return SolverResultCode.INDETERMINATE


def get_cleanup_command() -> List[str]:
    """Cleanup command for distributed solvers (not used by this solver)."""
    return ["echo", "cleanup"]
