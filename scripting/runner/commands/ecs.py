"""ECS commands for starting, stopping, and managing solver tasks."""

from typing import List, Tuple

from common import LoggingManager, ResourceNamer
from common.solver_env import SolverEnvironment, SolverNodeType
from runner.commands.base import CommandContext, CommandHandler
from runner.runner_docker import SolverConfig

lm = LoggingManager()


class EcsServiceManager:
    """Helper class for managing ECS services and validating configurations.

    Encapsulates the nested functions from start/stop/standby commands
    for better testability.
    """

    def __init__(self, ctx: CommandContext, logger=None):
        """Initialize the service manager.

        Args:
            ctx: CommandContext with AWS clients and config
            logger: Optional logger instance
        """
        self.ctx = ctx
        self.logger = logger or lm.get_logger(self.__class__.__name__)
        self._task_arns: List[str] | None = None

    @property
    def ecs_client(self):
        return self.ctx.get_client("ecs")

    @property
    def ecr_client(self):
        return self.ctx.get_client("ecr")

    @property
    def asg_client(self):
        return self.ctx.get_client("autoscaling")

    @property
    def rn(self) -> ResourceNamer:
        return self.ctx.rn

    def get_task_arns(self) -> List[str]:
        """Get all active task definition ARNs.

        Returns:
            List of task definition ARNs
        """
        if self._task_arns is None:
            task_response = self.ecs_client.list_task_definitions(status="ACTIVE")
            self._task_arns = task_response["taskDefinitionArns"]
        return self._task_arns

    def validate_ecr_images(self, aws_solvers: List[str]) -> bool:
        """Validate that all solvers have Docker images in ECR.

        Args:
            aws_solvers: List of solver names to validate

        Returns:
            True if all images exist, False otherwise
        """
        ecr_repo_name = self.rn.get_ecr_repo_name()
        ecr_response = self.ecr_client.describe_images(repositoryName=ecr_repo_name, filter={"tagStatus": "TAGGED"})
        ecr_images = ecr_response["imageDetails"]
        tagged_images: List[Tuple[List[str], str]] = [
            (i["imageTags"], i["imageDigest"]) for i in ecr_images if i.get("imageTags") is not None
        ]

        for solver in aws_solvers:
            expected_tag = self.rn.get_ecr_image_tag(solver)
            if not any(expected_tag in tags for tags, _ in tagged_images):
                self.logger.error(f"Error: Missing ECR Docker image for solver {solver}")
                self.logger.error(f"Expected tag: {expected_tag}")
                self.logger.error("Perhaps try the `push` command")
                return False

        return True

    def find_task_arn(self, solver: str, is_leader: bool) -> str | None:
        """Find the task ARN for a solver.

        Args:
            solver: Solver name
            is_leader: True for leader task, False for worker task

        Returns:
            Task ARN if found, None otherwise
        """
        task_arns = self.get_task_arns()
        task_def_name = self.rn.get_task_def_name(solver, is_leader)
        # CloudFormation strips all hyphens from construct IDs,
        # so we need to match without them
        task_def_name_normalized = task_def_name.replace("-", "")

        for arn in task_arns:
            self.logger.debug(f"task arn: {arn}")
            if task_def_name_normalized in arn:
                self.logger.debug(f"  matched task def name: {task_def_name_normalized}")
                return arn

        self.logger.error(f"Couldn't find an ECS task definition for solver {solver}.")
        if not is_leader:
            self.logger.error("Specifically, couldn't find a task definition for the worker.")
            self.logger.error(
                f"Perhaps {solver} was deployed as a parallel solver, "
                "but is now a distributed solver in your config file?"
            )
        self.logger.error("Run `deploy solvers` and try again.")
        return None

    def validate_env_vars(self, sc: SolverConfig, is_leader: bool) -> bool:
        """Validate environment variables in task definition match config.

        Args:
            sc: SolverConfig for the solver
            is_leader: True for leader task, False for worker task

        Returns:
            True if valid, False otherwise
        """
        arn = self.find_task_arn(sc.name, is_leader)
        if arn is None:
            return False

        response = self.ecs_client.describe_task_definition(taskDefinition=arn)
        containers = response["taskDefinition"]["containerDefinitions"]
        if len(containers) != 1:
            self.logger.error(f"Error: Task definition for {sc.name} has multiple referenced ECR images.")
            return False

        c_info = containers[0]
        expected_container_name = self.rn.get_container_name(sc.name)
        if c_info["name"] != expected_container_name:
            self.logger.error(
                f"Error: Expected container name ({expected_container_name}) doesn't "
                f"match deployed container name ({c_info['name']})"
            )
            return False

        c_env = {x["name"]: x["value"] for x in c_info["environment"]}
        validation_keys = [SolverEnvironment.NUM_WORKERS_KEY, SolverEnvironment.NODE_TYPE_KEY]
        for key in validation_keys:
            if c_env.get(key) is None:
                self.logger.error(f"AWS environment variable missing the {key} field")
                self.logger.error("Re-deploy with `deploy solvers`")
                return False

        # Validate NUM_WORKERS
        aws_num_workers = int(c_env[SolverEnvironment.NUM_WORKERS_KEY])
        config_num_workers = sc.cdk_solver.num_workers
        if aws_num_workers != config_num_workers:
            self.logger.error(
                f'Error: Solver "{sc.name}" is configured to use {config_num_workers} number of workers per leader (NoWpL),'
                f" but on AWS it uses {aws_num_workers} NoWpL."
            )
            self.logger.error("You must either run `deploy solvers` to update the NoWpL on AWS,")
            self.logger.error("or adjust the NoWpL in your config file to match the one on AWS.")
            return False

        # Validate NODE_TYPE
        aws_node_type = SolverNodeType.from_str(c_env[SolverEnvironment.NODE_TYPE_KEY])
        config_node_type = SolverNodeType.from_bools(is_leader, sc.is_distributed)
        if aws_node_type != config_node_type:
            self.logger.error(f'Error: Solver "{sc.name}" is configured as "{config_node_type}",')
            self.logger.error(f'but on AWS it is "{aws_node_type}".')
            self.logger.error("Either adjust `is_distributed` in your config file, or run `deploy solvers`.")
            return False

        return True

    def adjust_service(
        self, cluster_name: str, service_arns: List[str], cluster_service: str, desired_count: int, solver: str
    ) -> bool:
        """Adjust the desired count for an ECS service.

        Args:
            cluster_name: ECS cluster name
            service_arns: List of service ARNs in the cluster
            cluster_service: Service name substring to match
            desired_count: Desired task count
            solver: Solver name (for error messages)

        Returns:
            True on success, False otherwise
        """
        arn = None
        for service in service_arns:
            if cluster_service in service:
                arn = service
                break

        if arn is None:
            self.logger.error(f"Error: Could not find service for solver {solver}")
            return False

        self.ecs_client.update_service(
            cluster=cluster_name,
            service=arn,
            desiredCount=desired_count,
        )
        return True

    def scale_solver(self, solver: str, num_leaders: int, num_copies: int) -> bool:
        """Scale a solver's ECS service and ASG.

        Args:
            solver: Solver name
            num_leaders: Number of leader tasks to run
            num_copies: Number of EC2 instances per leader

        Returns:
            True on success, False otherwise
        """
        self.rn.set_solver(solver)
        self.logger.info(f"Adjusting the scaling for {solver}...")

        # Calculate the number of desired EC2 instances
        sc = self.ctx.project.get_solver(solver)
        num_workers_per_leader = sc.cdk_solver.num_workers
        desired_asg_capacity = num_copies * (1 + num_workers_per_leader)

        # 1. Update the auto-scaling group
        asg_name = self.rn.get_asg_name()
        self.asg_client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            DesiredCapacity=desired_asg_capacity,
        )

        # 2. Update the ECS cluster to start/stop a task
        cluster_name = self.rn.get_ecs_cluster_name()
        ecs_response = self.ecs_client.list_services(cluster=cluster_name)
        service_arns = ecs_response["serviceArns"]

        leader_service = f"{self.rn.get_solver_stack_name()}-SolverLeaderService"
        worker_service = f"{self.rn.get_solver_stack_name()}-SolverWorkerService"

        if not self.adjust_service(cluster_name, service_arns, leader_service, num_leaders, solver):
            return False

        if sc.is_distributed:
            if not self.adjust_service(
                cluster_name, service_arns, worker_service, num_leaders * num_workers_per_leader, solver
            ):
                return False

        return True


class StartCommand(CommandHandler):
    """Start ECS tasks for solvers."""

    def execute(self, num_copies: int = 1, **kwargs) -> int:
        """Start solver tasks on ECS.

        Args:
            num_copies: Number of instances to start

        Returns:
            0 on success, 1 on error
        """
        self.logger.info("start: Start tasks on ECS")
        return self._execute_ecs_action(num_leaders=num_copies, num_copies=num_copies, action="start")

    def _execute_ecs_action(self, num_leaders: int, num_copies: int, action: str) -> int:
        """Execute an ECS action (start/standby/stop).

        Args:
            num_leaders: Number of leader tasks
            num_copies: Number of EC2 instances
            action: Action name for logging

        Returns:
            0 on success, 1 on error
        """
        manager = EcsServiceManager(self.ctx, self.logger)
        aws_solvers = self.ctx.aws_solvers

        # Validate ECR images exist
        if not manager.validate_ecr_images(aws_solvers):
            return 1

        # Validate task definitions
        self.logger.debug("checking solver task definitions")
        for solver in aws_solvers:
            sc = self.ctx.project.get_solver(solver)
            if not manager.validate_env_vars(sc, is_leader=True):
                return 1
            if sc.is_distributed:
                if not manager.validate_env_vars(sc, is_leader=False):
                    return 1

        # Scale each solver
        for solver in aws_solvers:
            if not manager.scale_solver(solver, num_leaders, num_copies):
                return 1

        if action == "start":
            self.logger.info("start success")
            self.logger.info("Note that it may take up to 15 minutes for a task to start")
        elif action == "standby":
            self.logger.info("standby success")
            self.logger.info("Note that initializing any new EC2 instances can take up to 5 minutes")
        else:
            self.logger.info("stop success")

        return 0


class StandbyCommand(StartCommand):
    """Request/keep EC2 instances but stop running solvers."""

    def execute(self, num_copies: int = 1, **kwargs) -> int:
        """Put solvers in standby mode.

        Args:
            num_copies: Number of EC2 instances to keep

        Returns:
            0 on success, 1 on error
        """
        self.logger.info("standby: Request/keep EC2 instances, but stop any running solvers")
        return self._execute_ecs_action(num_leaders=0, num_copies=num_copies, action="standby")


class StopCommand(StartCommand):
    """Stop running ECS tasks."""

    def execute(self, **kwargs) -> int:
        """Stop all running solver tasks.

        Returns:
            0 on success, 1 on error
        """
        self.logger.info("stop: Stop running tasks on ECS")
        return self._execute_ecs_action(num_leaders=0, num_copies=0, action="stop")
