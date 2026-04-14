"""Parser, validator, and writer of the `input.json` requests for solvers."""

from typing import List

from common import SolverEnvironment, SolverQueueInput

################################################################################


class SolverRequester:
    """Generator of `input.json` strings.

    Since a solver's name, running configurations, timeout, etc.
    do not change between formulas, this class takes those settings
    and applies them to each formula and language
    """

    def __init__(
        self,
        solver_name: str,
        solver_options: List[str] | None = None,
        timeout_secs: int = 5,
        num_workers: int = 0,
    ):
        self.solver_name = solver_name
        self.solver_options = solver_options or []

        if timeout_secs > 0:
            self.timeout_secs = timeout_secs
        else:
            raise ValueError(f"Timeout seconds must be strictly positive (was {timeout_secs})")

        if num_workers >= 0:
            self.num_workers = num_workers
        else:
            raise ValueError(f"Number of workers must be non-negative (was {num_workers})")

    @staticmethod
    def from_env(senv: SolverEnvironment) -> "SolverRequester":
        return SolverRequester(
            solver_name=senv.solver,
            solver_options=[],
            timeout_secs=senv.local_timeout,
            num_workers=senv.num_workers,
        )

    def make_request(self, formula_url: str) -> SolverQueueInput:
        return SolverQueueInput(
            solver_name=self.solver_name,
            formula_url=formula_url,
            solver_options=self.solver_options,
            timeout_secs=self.timeout_secs,
            num_workers=self.num_workers,
        )

    def make_request_dict(self, formula_url: str) -> dict:
        return self.make_request(formula_url).to_dict()

    def make_request_json(self, formula_url: str) -> str:
        return self.make_request(formula_url).to_json()
