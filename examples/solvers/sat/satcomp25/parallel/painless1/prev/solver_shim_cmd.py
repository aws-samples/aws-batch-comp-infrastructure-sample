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

    # Create the hostfile
    hostfile_path = run_dir / "combined_hostfile.txt"
    with open(hostfile_path, "w+") as f:
        for ip in sinput.worker_node_ips:
            f.write(f"{ip} slots=1\n")  # distributed default

    cmd = ["/competition/run_solver.sh", str(hostfile_path), str(sinput.formula_file)]
    return cmd
