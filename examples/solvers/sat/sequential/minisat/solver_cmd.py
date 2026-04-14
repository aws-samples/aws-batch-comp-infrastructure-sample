"""
Solver command interface for MiniSat 2.2.0 SAT solver.

MiniSat is a classic minimal SAT solver. It reads DIMACS CNF formulas
and outputs standard SAT competition format.
"""

from pathlib import Path
from typing import List

from common.solver_io import SolverInput, SolverResultCode


def get_run_command(s_input: SolverInput) -> List[str]:
    # minisat_static reads from file, outputs result to stdout
    cmd = ["/minisat/simp/minisat_static", str(s_input.formula_file)]
    return cmd


def get_solver_result(stdout_path: Path) -> SolverResultCode:
    if stdout_path.exists():
        with open(stdout_path, "r") as f:
            for line in f:
                line = line.strip()
                if line == "SATISFIABLE" or line == "s SATISFIABLE":
                    return SolverResultCode.SAT
                elif line == "UNSATISFIABLE" or line == "s UNSATISFIABLE":
                    return SolverResultCode.UNSAT
                elif line in ("INDETERMINATE", "c UNKNOWN", "s UNKNOWN"):
                    return SolverResultCode.UNKNOWN

    return SolverResultCode.INDETERMINATE


def get_cleanup_command() -> List[str]:
    cmd = ["echo", "cleanup not needed"]
    return cmd
