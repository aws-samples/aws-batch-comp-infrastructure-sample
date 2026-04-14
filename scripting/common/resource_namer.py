"""Consistent naming for AWS solver resources."""


class ResourceNamer:
    """
    A class to manage a consistent naming scheme for AWS resources.

    Call `set_solver()` before getting the names for any solver-specific resources.

    When setting up the CDK architecture, call `set_stack()` to inherit the
    account ID and region information.
    """

    FIELD_SEP = "--"
    PREFIX = "satcomp"

    INPUT_QUEUE = "InputQueue"
    OUTPUT_QUEUE = "OutputQueue"

    # DynamoDB information (for distributed solvers)
    IP_TABLE = "NodeIpTable"
    TIMESTAMP_TABLE = "TimestampTable"
    PARTITION_KEY = "nodeId"

    RESULTS_S3_BUCKET = "ResultsBucket"
    ECR_REPO = "EcrRepo"
    VPC_STACK = "SolverVpcStack"

    # CC: I can't determine a better place for this option
    # The maximum number of EC2 instances thatn can belong to any ECS cluster
    ASG_MAX_CAPACITY = 500

    # The user to run the solver Docker container as.
    # Using a non-root user prevents solvers from e.g. deleting the filesystem.
    LINUX_USER = "ecs-user"

    def __init__(
        self,
        project: str,
        account: str | None = None,
        region: str | None = None,
        solver: str | None = None,
    ):
        self.project = project.lower()
        self.account = account
        self.region = region
        self.solver = solver

    def set_solver(self, solver: str) -> None:
        self.solver = solver

    def set_stack(self, stack) -> None:
        # The type of the `stack` argument is `aws_cdk:Stack`.
        # However, to speed up import time, we do not import `aws_cdk` here,
        # since we only need to access these two parameters
        self.account = stack.account
        self.region = stack.region

    def _solver(self, solver: str | None) -> str:
        return self.solver if solver is None else solver

    def _scoped_name(self, resource_type: str, solver: str | None = None) -> str:
        parts = [self.PREFIX, resource_type, self.project]
        if solver is not None:
            parts.append(solver)
        return self.FIELD_SEP.join(parts)

    def get_results_bucket_stack_name(self) -> str:
        return self._scoped_name("s3")

    def get_ecr_repo_stack_name(self) -> str:
        return self._scoped_name("ecr")

    def get_vpc_stack_name(self) -> str:
        return self._scoped_name("vpc")

    def get_reserved_stack_names(self) -> list[str]:
        return [self.get_results_bucket_stack_name(), self.get_ecr_repo_stack_name(), self.get_vpc_stack_name()]

    def get_bucket_name(self) -> str:
        return f"{self.account}-{self.region}-{self.project}-solver-results"

    def get_ecr_repo_name(self) -> str:
        return f"{self.project}-{self.region}-ecr"

    def get_ecs_cluster_postfix(self) -> str:
        return "ecs-cluster"

    def get_ecs_cluster_name(self, solver: str | None = None) -> str:
        solver = self._solver(solver)
        return f"{self.project}-{self.region}-{solver}-{self.get_ecs_cluster_postfix()}"

    def get_solver_from_ecs_cluster_name(self, s: str, region: str | None = None) -> str:
        """Extract the solver from the ECS cluster name. Best-effort."""
        region = self.region if region is None else region

        if s.startswith("arn:aws:ecs:"):
            s = s.split("/")[1]

        postfix = f"-{self.get_ecs_cluster_postfix()}"
        if not s.endswith(postfix):
            raise ValueError(f"Cannot extract solver name from ECS cluster {s}")

        # Remove the ending
        s = s[: -len(postfix)]

        # Next, skip over the project and region substrings
        start_of_solver = len(self.project) + len(region) + 2
        s = s[start_of_solver:]

        return s

    def get_task_def_name(self, solver: str | None = None, is_leader: bool = True) -> str:
        solver = self._solver(solver)
        tag = "Leader" if is_leader else "Worker"
        return self._scoped_name("taskdef", solver) + tag

    def get_linux_params_name(self, is_leader: bool) -> str:
        tag = "Leader" if is_leader else "Worker"
        return f"{tag}LinuxParams"

    def get_asg_name(self, solver: str | None = None) -> str:
        solver = self._solver(solver)
        return f"{self.project}-{self.region}-{solver}-Asg"

    def get_sqs_queue_prefix(self) -> str:
        return f"{self.account}-{self.region}-{self.project}"

    def get_sqs_queue_name(self, base_queue_name: str) -> str:
        return f"{self.get_sqs_queue_prefix()}-{self.solver}-{base_queue_name}"

    def get_sqs_input_queue_name(self) -> str:
        return self.get_sqs_queue_name(self.INPUT_QUEUE)

    def get_sqs_output_queue_name(self) -> str:
        return self.get_sqs_queue_name(self.OUTPUT_QUEUE)

    def get_log_group_stack_name(self, solver: str | None = None) -> str:
        solver = self._solver(solver)
        return self._scoped_name("loggroup", solver) + "Stack"

    def get_solver_stack_name(self, solver: str | None = None) -> str:
        solver = self._solver(solver)
        return self._scoped_name("solver", solver) + "Stack"

    def get_log_group_name(self, solver: str | None = None) -> str:
        solver = self._solver(solver)
        return f"/ecs/{self.project}-{self.region}-{solver}"

    def get_container_name(self, solver: str | None = None) -> str:
        solver = self._solver(solver)
        return self._scoped_name("container", solver)

    def get_ecr_repo_url(self) -> str:
        return f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/{self.get_ecr_repo_name()}"

    def get_image_url(self, solver: str | None = None) -> str:
        solver = self.solver if solver is None else solver
        return f"{self.get_ecr_repo_name()}:{self.get_ecr_image_tag(solver)}"

    def get_ecr_image_tag(self, solver: str | None = None) -> str:
        """Returns the image tag as it would appear in ECR after being pushed by satcomp.py"""
        solver = self._solver(solver)
        return self._scoped_name("image", solver)

    def get_solver_from_ecr_image_tag(self, s: str) -> str:
        parts = s.split(self.FIELD_SEP)
        if len(parts) < 4 or parts[0] != self.PREFIX or parts[1] != "image":
            raise ValueError(f"Cannot extract solver name from ECR image tag: {s}")
        return parts[-1]

    def get_dynamo_table_name(self, base_name: str) -> str:
        return f"{self.project}-{self.region}-{self.solver}-{base_name}"

    def get_ip_table_name(self) -> str:
        return self.get_dynamo_table_name(self.IP_TABLE)

    def get_timestamp_table_name(self) -> str:
        return self.get_dynamo_table_name(self.TIMESTAMP_TABLE)
