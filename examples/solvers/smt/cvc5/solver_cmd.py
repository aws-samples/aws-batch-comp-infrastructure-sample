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

    TODO: Participants should replace this with their solver-specific options.
    """

    cmd = ["/cvc5/build/bin/cvc5", str(s_input.formula_file)]
    return cmd


def get_solver_result(stdout_path: Path) -> SolverResultCode:
    ### Optionally, implement your own logic. ###
    # with open(output_file) as f:
    #     raw_logs = f.read()
    #     if "TRUSTED checker reported UNSAT - sig" in raw_logs:
    #         return 20 # checked, trusted
    #     if "TRUSTED checker reported SAT - sig" in raw_logs:
    #         return 10 # checked, trusted
    #     if "SATWP RES ~20~" in raw_logs:
    #         return 20 # normal UNSAT via SAT+prepro
    #     if "SATWP RES ~10~" in raw_logs:
    #         return 10 # normal SAT via SAT+prepro
    #     if "[ERROR]" in raw_logs:
    #         return -1 # some error occurred
    #     return 0

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
