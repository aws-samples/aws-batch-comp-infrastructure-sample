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

    cmd = ["/gimsatul/gimsatul", str(s_input.run_dir / "input.json"), "--threads=32", "-r"]
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
