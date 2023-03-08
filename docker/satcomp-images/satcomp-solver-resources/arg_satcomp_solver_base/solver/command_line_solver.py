"""
This will contain the Solver implementation that shells out to a a solver
executable and saves the logs
"""
import logging
import os
from json import JSONDecodeError

from arg_satcomp_solver_base.solver.solver import Solver
from arg_satcomp_solver_base.solver.run_command import CommandRunner

from arg_satcomp_solver_base.utils import FileOperations

FAILED_TO_WRITE_PROBLEM_TEXT = "Failed to write problem text to file"


class SolverException(Exception):
    """Solver run failure exception"""


class CommandLineSolver(Solver):
    """Solver implementation that shells out to an executable wrapper for a solver executable and saves the logs"""
    solver_command: str
    command_runner: CommandRunner
    stdout_target_loc: str = "base_container_stdout.log"
    stderr_target_loc: str = "base_container_stderr.log"

    DEFAULT_TIMEOUT_SECONDS: int = 3600

    def __init__(self, solver_command: str):
        self.solver_command = solver_command
        self.command_runner = CommandRunner(self.stdout_target_loc, self.stderr_target_loc)
        self.file_operations = FileOperations()
        self.logger = logging.getLogger("CommandLineSolver")
        self.logger.setLevel(logging.DEBUG)

    def _save_input_json(self, formula_file: str, directory_path: str, workers: list, formula_language: str, solver_argument_list: list, timeout_seconds: str):
        input_json = {
            "formula_file": formula_file,
            "worker_node_ips": list(map(lambda w: w["nodeIp"], workers)),
            "formula_language": formula_language, 
            "solver_argument_list": solver_argument_list,
            "timeout_seconds": timeout_seconds,
        }
        try:
            self.file_operations.write_json_file(os.path.join(directory_path, "input.json"), input_json)
        except OSError as e:
            self.logger.exception(e)
            raise SolverException(FAILED_TO_WRITE_PROBLEM_TEXT)

    def _run_command(self, cmd: str, arguments: list, output_directory: str, timeout: int):
        """Run a command as a subprocess and save logs"""
        cmd_list = [cmd]
        if arguments is not None:
            cmd_list.extend(arguments)
        process_result = self.command_runner.run(cmd_list, output_directory, timeout)
        return process_result

    def _get_solver_result(self, request_directory_path):
        try:
            raw_solver_result = self.file_operations.read_json_file(os.path.join(request_directory_path, "solver_out.json"))
        except FileNotFoundError:
            self.logger.error("Solver did not generate output JSON")
        except JSONDecodeError as e:
            self.logger.error("Solver output not valid json")
            self.logger.exception(e)
        else:
            return raw_solver_result
        # If we cannot read the solver result, that is not an error state
        # since it is user provided and may not work
        return None

    def solve(self, formula_file: str, request_directory_path: str, workers: list, task_uuid: str, timeout: int, formula_language: str, solver_argument_list: list):
        """Solve implementation that shells out to a subprocess"""
   
        self._save_input_json(formula_file, request_directory_path, workers, formula_language, solver_argument_list, timeout)

        if not timeout:
            timeout = CommandLineSolver.DEFAULT_TIMEOUT_SECONDS
        try:
            process_result = self._run_command(self.solver_command, [request_directory_path],
                                               request_directory_path, timeout)
        except FileNotFoundError:
            self.logger.error(f"Failed to execute solver script at path: {self.solver_command}. "
                              f"Solver executable does not exist")
            raise SolverException(f"Failed to execute solver script at path: {self.solver_command}. "
                                  f"Solver executable does not exist")

        solver_result = self._get_solver_result(request_directory_path)
        self.logger.info(solver_result)
        if solver_result is None:
            task_state = {
                "status": "FAILED",
                "message": "Error retrieving solver result"
            }
        else:
            task_state = process_result.get("task_state")

        solver_runtime_millis = None
        run_time_ns = process_result.get("run_time_ns")
        if run_time_ns:
            solver_runtime_millis = round(process_result.get("run_time_ns") / 1000000)
        """
        Our output includes the stdout and stderr logs of the driver (the /satcomp/solver executable),
        as well as whatever JSON output is provided once that solver finishes.
        """
        return {
            "task_id": task_uuid,
            "driver": {
                "stdout": os.path.join(request_directory_path, process_result.get("stdout")),
                "stderr": os.path.join(request_directory_path, process_result.get("stderr")),
                "return_code": process_result.get("return_code"),
                "solver_runtime_millis": solver_runtime_millis
            },
            "solver": {
                "output": solver_result,
                "request_directory_path": request_directory_path
            },
            "task_state": task_state
        }
