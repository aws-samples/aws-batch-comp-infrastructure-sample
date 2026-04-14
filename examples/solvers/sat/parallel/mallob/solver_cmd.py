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
    # Create the hostfile
    all_ips = [s_input.node_ip] + s_input.worker_node_ips
    hostfile_path = s_input.run_dir / "combined_hostfile.txt"
    with open(hostfile_path, "w+") as f:
        for ip in all_ips:
            f.write(f"{ip} slots=1\n")  # distributed default

    cmd = ["/run_solver.sh", str(hostfile_path), str(s_input.formula_file)]
    return cmd


def get_solver_result(stdout_path: Path) -> SolverResultCode:
    if not stdout_path.exists():
        return SolverResultCode.INDETERMINATE

    with open(stdout_path, "r") as f:
        lines = f.readlines()

    # Scan in reverse — last definitive result wins
    for line in reversed(lines):
        stripped = line.strip()

        # ImpCheck trusted results (highest priority)
        if "TRUSTED checker reported UNSAT" in stripped:
            return SolverResultCode.UNSAT
        if "TRUSTED checker reported SAT" in stripped:
            return SolverResultCode.SAT

        # Standard SAT competition output
        if stripped == "s SATISFIABLE":
            return SolverResultCode.SAT
        if stripped == "s UNSATISFIABLE":
            return SolverResultCode.UNSAT
        if stripped in ("s UNKNOWN", "c UNKNOWN"):
            return SolverResultCode.UNKNOWN

        # SATWP (SAT with preprocessing) result codes
        if "SATWP RES ~10~" in stripped:
            return SolverResultCode.SAT
        if "SATWP RES ~20~" in stripped:
            return SolverResultCode.UNSAT

        # Lowercase variants
        if stripped == "sat":
            return SolverResultCode.SAT
        if stripped == "unsat":
            return SolverResultCode.UNSAT
        if stripped == "unknown":
            return SolverResultCode.UNKNOWN

    return SolverResultCode.INDETERMINATE


# For distributed solvers only; ignored by parallel solvers
def get_cleanup_command() -> List[str]:
    script = (
        "pkill -f 'mallob' 2>/dev/null; "
        "pkill -f 'mpirun' 2>/dev/null; "
        "rm -rf /tmp/mallob_* /tmp/*.lrat /tmp/*.proof /rundir/solution.txt* 2>/dev/null; "
        "exit 0"
    )
    return ["bash", "-c", script]
