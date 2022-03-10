from dataclasses import dataclass


@dataclass
class Solver:
    """Solver interface"""
    def solve(self, problem_loc: str, workers: list, task_uuid: str):
        """Interface for solve command"""
