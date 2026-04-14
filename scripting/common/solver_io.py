"""
A class representing the `input.json` and `output.json` dictionaries,
for both queue and solver I/O.

Note: Due to circular dependencies, we cannot split SolverIO
from SolverQueueIO, so we include them here in the same file.
"""

from enum import Enum
from pathlib import Path
from typing import List

from . import pathing
from .json_to_python import JsonToPythonObject
from .misc import get_local_ip_address

################################################################################


class SolverQueueInput(JsonToPythonObject):
    """
    A class representation of the object pulled from the SQS queue.

    It has the following form:
    ```
    {
      "formula": {
        "value": str,  # (S3) path to the formula
      },
      "solverConfig": {
        "solverName": str,
        "solverOptions": list[str],
        "taskTimeoutSeconds": int,
      },
      "num_workers": int,   # The number of worker containers; 0 if parallel solver
    }
    ```
    """

    def __init__(
        self,
        solver_name: str,
        formula_url: str,
        solver_options: list[str] | None = None,
        timeout_secs: int = 5,
        num_workers: int = 0,
    ):
        self.solver_name = solver_name
        self.formula_url = formula_url
        self.solver_options = solver_options or []
        self.timeout_secs = timeout_secs
        self.num_workers = num_workers

        if timeout_secs <= 0:
            raise Exception(f"Timeout seconds must be strictly positive (was {timeout_secs})")

        if num_workers < 0:
            raise Exception(f"Number of workers must be non-negative (was {num_workers})")

    def to_dict(self) -> dict:
        return {
            "formula": {
                "value": self.formula_url,
            },
            "solverConfig": {
                "solverName": self.solver_name,
                "solverOptions": self.solver_options,
                "taskTimeoutSeconds": self.timeout_secs,
            },
            "num_workers": self.num_workers,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SolverQueueInput":
        return SolverQueueInput(
            solver_name=d["solverConfig"]["solverName"],
            formula_url=d["formula"]["value"],
            solver_options=d["solverConfig"]["solverOptions"],
            timeout_secs=int(d["solverConfig"]["taskTimeoutSeconds"]),
            num_workers=int(d["num_workers"]),
        )


class SolverInput(JsonToPythonObject):
    """
    A Python class representing the `input.json` object given (indirectly) to the solver.

    Note that the solver receives as its only argument the path to the *directory*
    containing the `input.json`. This directory is also the place where the
    `stdout.log`, `stderr.log`, and `solver_output.json` files are created.
    (For `solver_output.json`, see the `SolverOutput` class in this file.)

    The `SolverInput` object has the following fields:
    ```
    self.formula_file: Path
    self.run_dir: Path
    self.solver_argument_list: list[str]      (default = [])
    self.timeout_seconds: int                 (default = 1000)
    self.node_ip: str                         (default = get_ip())
    self.worker_node_ips: list[str]           (default = [])
    ```
    These fields correspond to the fields of the actual JSON:
    ```
    { "formula_file": Path("/path/to/formula"),
      "run_dir": Path("/path/to/rundir/containing/formula"),
      "solver_argument_list": [list of argument tokens],
      "timeout_seconds": int,
      "node_ip": str,
      "worker_node_ips": [list of IP address strings], }
    ```
    An example input is:
    ```
    { "formula_file": Path("/tmp/solver/formula/php10.cnf"),
      "run_dir": Path("/tmp/solver/formula"),
      "solver_argument_list": ["--verbose", "--num_restarts", "5"],
      "timeout_seconds": 1000,
      "node_ip": "192.0.0.0",
      "worker_node_ips": ["192.0.0.1"], }
    ```
    """

    def __init__(
        self,
        formula_file: Path | str,
        run_dir: Path | str,
        solver_argument_list: List[str] | None = None,
        timeout_seconds: int = 1000,
        node_ip: str = get_local_ip_address(),
        worker_node_ips: List[str] | None = None,
    ):
        self.formula_file = pathing.normalize_path(formula_file)
        self.run_dir = pathing.normalize_path(run_dir)
        self.solver_argument_list = solver_argument_list or []
        self.timeout_seconds = timeout_seconds
        self.node_ip = node_ip
        self.worker_node_ips = worker_node_ips or []
        self._validate()

    @classmethod
    def from_queue_input(
        cls,
        formula_file: Path | str,
        run_dir: Path | str,
        q_input: SolverQueueInput,
        node_ip: str = get_local_ip_address(),
        worker_node_ips: List[str] | None = None,
    ) -> "SolverInput":
        return cls(
            formula_file=formula_file,
            run_dir=run_dir,
            solver_argument_list=q_input.solver_options,
            timeout_seconds=q_input.timeout_secs,
            node_ip=node_ip,
            worker_node_ips=worker_node_ips,
        )

    def _validate(self):
        if self.timeout_seconds <= 0:
            raise ValueError(f"Timeout seconds must be strictly positive (was {self.timeout_seconds})")

        if not self.run_dir.exists():
            raise ValueError(f"Run directory at {self.run_dir} does not exist")

        if not self.formula_file.exists():
            raise ValueError(f"Formula file at {self.formula_file} does not exist")

    @classmethod
    def from_dict(_, d: dict) -> "SolverInput":
        """
        Given a dictionary, produce a SolverInput object
        """
        return SolverInput(
            formula_file=d["formula_file"],
            run_dir=d["run_dir"],
            solver_argument_list=d["solver_argument_list"],
            timeout_seconds=d["timeout_seconds"],
            node_ip=d["node_ip"],
            worker_node_ips=d["worker_node_ips"],
        )

    def to_dict(self) -> dict:
        return {
            "formula_file": str(self.formula_file),
            "run_dir": str(self.run_dir),
            "solver_argument_list": self.solver_argument_list,
            "timeout_seconds": self.timeout_seconds,
            "node_ip": self.node_ip,
            "worker_node_ips": self.worker_node_ips,
        }


################################################################################


class SolverResultCode(Enum):
    UNKNOWN = 0  # For SMT solvers, that the result is unknown
    SAT = 10  # Satisfiable formula
    UNSAT = 20  # Unsatisfiable formula
    INDETERMINATE = -6  # The solver exited, but its result couldn't be determined
    TIMEOUT = -7  # The solver timed out, no official result reported
    CRASH = -8  # The solver crashed (its return code is recorded separately)

    def __str__(self):
        if self == SolverResultCode.UNKNOWN:
            return "UNKNOWN"
        elif self == SolverResultCode.SAT:
            return "SAT"
        elif self == SolverResultCode.UNSAT:
            return "UNSAT"
        elif self == SolverResultCode.INDETERMINATE:
            return "INDETERMINATE"
        elif self == SolverResultCode.TIMEOUT:
            return "TIMEOUT"
        elif self == SolverResultCode.CRASH:
            return "CRASH"
        else:
            raise ValueError(f"Unknown SolverResultCode: {self}")

    @staticmethod
    def from_int(i: int):
        for code in SolverResultCode:
            if code.value == i:
                return code
        return SolverResultCode.INDETERMINATE


class SolverOutput(JsonToPythonObject):
    """
    The contents of the `solver_out.json` file.
    """

    def __init__(
        self,
        solver_result_code: int | SolverResultCode,
        process_return_code: int,
        elapsed_time: float,
        stdout_path: Path | str,
        stderr_path: Path | str,
    ):
        if isinstance(solver_result_code, int):
            self.solver_result_code = SolverResultCode.from_int(solver_result_code)
        else:
            self.solver_result_code = solver_result_code
        self.process_return_code = process_return_code
        self.elapsed_time = elapsed_time
        self.stdout_path = pathing.normalize_path(stdout_path)
        self.stderr_path = pathing.normalize_path(stderr_path)
        self._validate()

    def _validate(self):
        if not self.stdout_path.exists():
            raise ValueError(f"Stdout path does not exist: {self.stdout_path}")
        if not self.stderr_path.exists():
            raise ValueError(f"Stderr path does not exist: {self.stderr_path}")

    @classmethod
    def from_dict(_, d: dict) -> "SolverOutput":
        """
        Given a dictionary, produce a SolverOutput object
        """
        return SolverOutput(
            solver_result_code=d["solver_result_code"],
            process_return_code=d["process_return_code"],
            elapsed_time=d["elapsed_time"],
            stdout_path=d["artifacts"]["stdout_path"],
            stderr_path=d["artifacts"]["stderr_path"],
        )

    def to_dict(self) -> dict:
        return {
            "solver_result_code": self.solver_result_code.value,
            "process_return_code": self.process_return_code,
            "elapsed_time": self.elapsed_time,
            "artifacts": {
                "stdout_path": str(self.stdout_path),
                "stderr_path": str(self.stderr_path),
            },
        }


class CompetitionQueueOutput(JsonToPythonObject):
    def __init__(
        self,
        solver: str,
        process_return_code: int,
        solver_result_code: int | SolverResultCode,
        solver_runtime_millis: int,
        job_time_start: str,
        formula_s3_uri: str,
        upload_dir_uri: str,
    ):
        self.solver = solver
        self.process_return_code = process_return_code
        if isinstance(solver_result_code, int):
            self.solver_result_code = SolverResultCode.from_int(solver_result_code)
        else:
            self.solver_result_code = solver_result_code
        self.solver_runtime_millis = solver_runtime_millis
        self.job_time_start = job_time_start
        self.formula_s3_uri = formula_s3_uri
        self.upload_dir_uri = upload_dir_uri

    @classmethod
    def from_dict(cls, d: dict) -> "CompetitionQueueOutput":
        return CompetitionQueueOutput(
            solver=d["solver"],
            process_return_code=d["process_return_code"],
            solver_result_code=d["solver_result_code"],
            solver_runtime_millis=d["solver_runtime_millis"],
            job_time_start=d["job_time_start"],
            formula_s3_uri=d["formula_s3_uri"],
            upload_dir_uri=d["upload_dir_uri"],
        )

    def to_dict(self) -> dict:
        return {
            "solver": self.solver,
            "process_return_code": self.process_return_code,
            "solver_result_code": self.solver_result_code.value,
            "solving_result": str(self.solver_result_code),
            "solver_runtime_millis": self.solver_runtime_millis,
            "job_time_start": self.job_time_start,
            "formula_s3_uri": self.formula_s3_uri,
            "upload_dir_uri": self.upload_dir_uri,
        }
