from pathlib import Path
from typing import List
from common.solver_io import SolverInput, SolverResultCode

def create_hostfile(worker_ips, leader_ip, request_dir):
    totalWorkerNodes = 0
    hostfile_path = os.path.join(request_dir, 'combined_hostfile')
    with open(hostfile_path, 'w+') as f:
        for ip in worker_ips:
            if ip != leader_ip:
                totalWorkerNodes += 1
                f.write(f'{ip}')
                f.write('\n')

    return hostfile_path, totalWorkerNodes

def get_run_command(s_input: SolverInput) -> List[str]:
    # leader_ip = socket.gethostbyname(socket.gethostname())
    leader_ip = s_input.node_ip

    combined_hostfile, totalWorkerNodes = create_hostfile(s_input.worker_node_ips, leader_ip, s_input.run_dir)

    return [
        "bash", "/SMTS/aws-build/run_solver.sh",
        str(hostfile),
        str(s_input.formula_file),
        str(totalWorkerNodes),
        # "-t", str(s_input.timeout_seconds)
    ]

def get_solver_result(stdout_path: Path) -> SolverResultCode:
    if stdout_path.exists():
        with open(stdout_path, 'r') as f:
            content = f.read()

        if "unsat" in raw_logs or "UNSAT" in raw_logs:
            return SolverResultCode.UNSAT
        if "sat" in raw_logs or "SAT" in raw_logs:
            return SolverResultCode.SAT
        if "error" in raw_logs or ";error" in raw_logs:
            return SolverResultCode.INDETERMINATE

        return SolverResultCode.UNKNOWN

    return SolverResultCode.INDETERMINATE

def get_cleanup_command() -> List[str]:
    return ["pkill", "solver_opensmt"]
