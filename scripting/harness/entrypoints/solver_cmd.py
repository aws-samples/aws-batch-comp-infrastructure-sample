"""
Python logic to map `input.json` input elements to a solver command.

Competitors should add their own logic for how to invoke their solver.
Note that the formula file is a local file on disk,
and the timeout is in seconds. Solvers that do not observe the timeout
will be killed with SIGTERM, and then SIGKILL.
"""

from pathlib import Path
from typing import List

from common.solver_io import SolverInput, SolverResultCode


def get_run_command(s_input: SolverInput) -> List[str]:
    """
    Maps the `SolverInput` from the `input.json` to a list of command tokens in order to invoke the solver.

    NB: `sinput.formula_file` and `.run_dir` are `Path`s. To get a string from them, wrap them in `str()`.

    TODO: Participants should replace this with their solver-specific options.

    Participants should also implement any setup behavior that they want to run
    before their solver is invoked, such as writing down a file of all IP addresses.
    """

    cmd = ["echo", "PLEASE", "IMPLEMENT", "ME", str(s_input.formula_file)]
    return cmd


def get_solver_result(stdout_path: Path) -> SolverResultCode:
    """
    Looks in the solver's `stdout.txt` file for the solving result.

    TODO: Participants should replace with something more robust for their own solver.
    """

    if stdout_path.exists():
        with open(stdout_path, "r") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if line == "s SATISFIABLE" or line == "sat":
                return SolverResultCode.SAT
            elif line == "s UNSATISFIABLE" or line == "unsat":
                return SolverResultCode.UNSAT
            elif line == "c UNKNOWN" or line == "s UNKNOWN" or line == "unknown":
                return SolverResultCode.UNKNOWN

    return SolverResultCode.INDETERMINATE


# For distributed solvers only; ignored by parallel solvers
def get_cleanup_command() -> List[str]:
    cmd = ["echo", "PLEASE", "IMPLEMENT", "ME"]
    return cmd
