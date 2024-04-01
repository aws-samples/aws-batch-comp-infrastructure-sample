from dataclasses import dataclass


@dataclass
class Solver:
    """Solver interface"""
    def solve(self, formula_file: str, request_directory_path: str, workers: list, task_uuid: str, timeout: int, formula_language: str, solver_argument_list: list):
        """Interface for solve command"""
