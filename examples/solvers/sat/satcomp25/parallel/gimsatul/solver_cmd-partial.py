"""
Python logic to map `input.json` input elements to a solver command.

Competitors should add their own logic for how to invoke their solver.
Note that the formula file is a local file on disk,
and the timeout is in seconds. Solvers that do not observe the timeout
will be killed with SIGTERM, and then SIGKILL.
"""

from pathlib import Path
from typing import List

from common.solver_io import SolverInput


def get_run_command(sinput: SolverInput, run_dir: Path) -> List[str]:
    """
    Maps the `SolverInput` from the `input.json` to a list of command tokens in order to invoke the solver.

    TODO: Participants should replace this with their solver-specific options.
    """

    cmd = ["/gimsatul/gimsatul", str(run_dir / "input.json"), "--threads=32", "-r"]
    return cmd
