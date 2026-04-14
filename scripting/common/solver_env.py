"""
The management of solver-specific environment options.

These are given to the harness in the Docker containers to modify behavior.
These options help coordinate whether to perform local testing,
what to locally test, where AWS resources are located, and so on.
"""

import os
from enum import Enum

from .misc import intn
from .resource_namer import ResourceNamer


class SolverNodeType(Enum):
    PARALLEL = "parallel"
    DIST_LEADER = "distributed-leader"
    DIST_WORKER = "distributed-worker"

    def __str__(self) -> str:
        return self.value

    def is_parallel(self) -> bool:
        return self == SolverNodeType.PARALLEL

    def is_distributed(self) -> bool:
        return not self.is_parallel()

    def is_leader(self) -> bool:
        return self == SolverNodeType.PARALLEL or self == SolverNodeType.DIST_LEADER

    def is_worker(self) -> bool:
        return not self.is_leader()

    @classmethod
    def from_str(cls, s: str):
        s = s.lower()
        for nt in cls:
            if s == str(nt):
                return nt
        raise ValueError(f"Invalid solver node type: {s}")

    @staticmethod
    def from_bools(is_leader: bool, is_distributed: bool) -> "SolverNodeType":
        if is_leader:
            if is_distributed:
                return SolverNodeType.DIST_LEADER
            else:
                return SolverNodeType.PARALLEL
        else:
            if is_distributed:
                return SolverNodeType.DIST_WORKER
            else:
                raise ValueError("Cannot be parallel worker")


class SolverEnvironment:

    # The ACCOUNT and REGION environment variables have special semantic meaning,
    # i.e., boto3 and the `aws` CLI use them to know which AWS resources to use.
    # See https://docs.aws.amazon.com/cli/v1/userguide/cli-configure-envvars.html
    # The KEY variables should not be changed without first adjusting how
    # boto3 sessions are created in the harness (i.e., the region and account
    # will need to be passed in manually, and X_shim files need to create this
    # boto3 session, rather than using the default session).

    SOLVER_KEY = "SOLVER_NAME"
    PROJECT_KEY = "PROJECT_NAME"
    ACCOUNT_KEY = "AWS_ACCOUNT_ID"
    REGION_KEY = "AWS_DEFAULT_REGION"
    NODE_TYPE_KEY = "SOLVER_NODE_TYPE"
    NUM_WORKERS_KEY = "NUM_WORKERS"
    LOCAL_TESTS_KEY = "LOCAL_TEST_FILES"
    LOCAL_TIMEOUT_KEY = "LOCAL_TIMEOUT"

    def __init__(
        self,
        solver: str,
        project: str,
        account: str | None = None,
        region: str | None = "us-east-1",
        node_type: str | SolverNodeType = SolverNodeType.PARALLEL,
        num_workers: int | str = 0,
        local_test_files: str | None = None,
        local_timeout: int | str | None = None,
    ):

        self.solver = solver
        self.project = project
        self.account = account
        self.region = region
        self.is_aws = self.account is not None and self.region is not None
        self.is_local = not self.is_aws

        self.node_type = node_type
        if isinstance(node_type, str):
            self.node_type = SolverNodeType.from_str(node_type)

        self.is_parallel = self.node_type.is_parallel()
        self.is_distributed = not self.is_parallel
        self.is_leader = self.node_type.is_leader()
        self.is_worker = self.node_type.is_worker()
        self.num_workers = int(num_workers)

        self.local_test_files = local_test_files
        self.local_timeout = intn(local_timeout)
        # TODO add local solver options, since we can't adjust with job args

        self._validate()

    def _validate(self):
        # Helper function for raising errors if a value is missing
        def validate_not_none(key, value):
            if value is None:
                raise ValueError(f"{key} cannot be None")

        validate_not_none(self.SOLVER_KEY, self.solver)
        validate_not_none(self.PROJECT_KEY, self.project)
        if self.is_local:
            validate_not_none(self.LOCAL_TESTS_KEY, self.local_test_files)
            validate_not_none(self.LOCAL_TIMEOUT_KEY, self.local_timeout)
            if self.local_timeout <= 0:
                raise ValueError(f"{self.LOCAL_TIMEOUT_KEY} must be positive, was {self.local_timeout}")
        else:
            validate_not_none(self.ACCOUNT_KEY, self.account)
            validate_not_none(self.REGION_KEY, self.region)

        validate_not_none(self.NUM_WORKERS_KEY, self.num_workers)
        validate_not_none(self.NODE_TYPE_KEY, self.node_type)

        if self.num_workers < 0:
            raise ValueError(f"{self.is_worker} must be non-negative, was {self.num_workers}")

        if self.is_distributed and self.num_workers <= 0:
            raise ValueError(
                f"{self.NUM_WORKERS_KEY} must be positive for" f" distributed solvers, was {self.num_workers}"
            )

    def to_dict(self) -> dict:
        d = {
            self.SOLVER_KEY: self.solver,
            self.PROJECT_KEY: self.project,
            self.NODE_TYPE_KEY: str(self.node_type),
            self.NUM_WORKERS_KEY: self.num_workers,
        }

        if self.is_aws:
            d[self.ACCOUNT_KEY] = self.account
            d[self.REGION_KEY] = self.region
        else:
            d[self.LOCAL_TESTS_KEY] = self.local_test_files
            d[self.LOCAL_TIMEOUT_KEY] = self.local_timeout

        return d

    def to_cdk_dict(self) -> dict:
        """
        Like `to_dict()`, but formatted for CDK task definition.

        This function is called in `solver_stack.py`, but nowhere else.

        The `environment` field for `ecs.TaskDefinition.add_container()`
        requires that the dictionary be a dictionary with only strings
        as keys and values. Since some of the `SolverEnvironment`'s values
        are numerical, we must apply `str()` to every value.

        See also the `environment` field under the `add_container()` function at:
        https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ecs/TaskDefinition.html#aws_cdk.aws_ecs.TaskDefinition
        """
        d = self.to_dict()
        return {k: str(v) for k, v in d.items()}

    @classmethod
    def from_env(cls) -> "SolverEnvironment":
        return SolverEnvironment(
            solver=os.getenv(cls.SOLVER_KEY),
            project=os.getenv(cls.PROJECT_KEY),
            account=os.getenv(cls.ACCOUNT_KEY),
            region=os.getenv(cls.REGION_KEY),
            node_type=os.getenv(cls.NODE_TYPE_KEY, SolverNodeType.PARALLEL),
            num_workers=os.getenv(cls.NUM_WORKERS_KEY, 0),
            local_test_files=os.getenv(cls.LOCAL_TESTS_KEY),
            local_timeout=os.getenv(cls.LOCAL_TIMEOUT_KEY),
        )

    @staticmethod
    def aws_env(rn: ResourceNamer, node_type: SolverNodeType, num_workers: int) -> "SolverEnvironment":
        """Make a new environment for an AWS-based solver. Pulls values from the `ResourceNamer`."""
        return SolverEnvironment(
            solver=rn.solver,
            project=rn.project,
            account=rn.account,
            region=rn.region,
            node_type=node_type,
            num_workers=num_workers,
        )

    def to_resource_namer(self) -> ResourceNamer:
        return ResourceNamer(self.project, self.account, self.region, self.solver)
