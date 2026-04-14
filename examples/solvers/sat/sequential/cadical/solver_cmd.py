"""
Solver competition interface for CaDiCaL SAT solver.

CaDiCaL is a state-of-the-art sequential SAT solver by Armin Biere.
It reads DIMACS CNF formulas and outputs standard SAT competition format.
"""

from pathlib import Path
from typing import List

from common.solver_io import SolverInput, SolverResultCode


def get_run_command(s_input: SolverInput) -> List[str]:
    """
    Maps the `SolverInput` from the `input.json` to a list of command tokens in order to invoke the solver.
    """
    cmd = ["/cadical/build/cadical", str(s_input.formula_file)]
    return cmd


def get_solver_result(stdout_path: Path) -> SolverResultCode:
    """
    Parses solver stdout to determine result to report.
    """
    if stdout_path.exists():
        with open(stdout_path, "r") as f:
            for line in f:
                line = line.strip()
                if line == "s SATISFIABLE":
                    return SolverResultCode.SAT
                elif line == "s UNSATISFIABLE":
                    return SolverResultCode.UNSAT
                elif line in ("c UNKNOWN", "s UNKNOWN"):
                    return SolverResultCode.UNKNOWN
    return SolverResultCode.INDETERMINATE


def get_cleanup_command() -> List[str]:
    """
    Used for distributed solvers only; ignored by sequential and parallel solvers
    
    This command is run in every leader and worker node.
    """
    cmd = ["echo", "cleanup not needed"]
    return cmd
