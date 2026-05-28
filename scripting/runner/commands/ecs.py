"""ECS commands for starting, stopping, and managing solver tasks."""

import time
from typing import List, Tuple

from common import LoggingManager, ResourceNamer
from common.solver_env import SolverEnvironment, SolverNodeType
from harness.aws_shim import SqsQueue
from runner.commands.base import CommandContext, CommandHandler
from runner.runner_docker import SolverConfig

lm = LoggingManager()


def prompt_purge_queues(ctx: "CommandContext", logger) -> None:
    """Check input queues for pending messages and offer to purge them.

    If any solver's input queue has messages, prompts the operator
    to purge all input queues before proceeding.
    """
    if ctx.boto3_session is None:
        return

    aws_solvers = ctx.aws_solvers
    rn = ctx.rn

    try:
        total_messages = 0
        for solver in aws_solvers:
            rn.set_solver(solver)
            q_in_name = rn.get_sqs_input_queue_name()
            q_in = SqsQueue.get_sqs_queue_from_session(ctx.boto3_session, q_in_name)
            total_messages += q_in.len()
    except Exception:
        return

    if total_messages == 0:
        return

    logger.warning(f"Input queues contain ~{total_messages} pending message(s).")
    response = input("Purge input queues before stopping? [y/N] ").strip().lower()
    if response == "y":
        for solver in aws_solvers:
            rn.set_solver(solver)
            q_in_name = rn.get_sqs_input_queue_name()
            q_in = SqsQueue.get_sqs_queue_from_session(ctx.boto3_session, q_in_name)
            q_in.purge()
        logger.info("Input queues purged.")


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

    def get_running_task_count(self, solver: str) -> int:
        """Get the number of running tasks for a solver's cluster.

        Args:
            solver: Solver name

        Returns:
            Number of running tasks
        """
        self.rn.set_solver(solver)
        cluster_name = self.rn.get_ecs_cluster_name()
        response = self.ecs_client.list_tasks(cluster=cluster_name, desiredStatus="RUNNING")
        return len(response.get("taskArns", []))

    def has_stale_images(self, aws_solvers: List[str]) -> bool:
        """Check if any running tasks are using images that differ from ECR.

        Compares the image digest in running task containers against the
        current digest for each solver's tag in ECR.

        Returns:
            True if any running task uses a stale image, False otherwise
        """
        ecr_repo_name = self.rn.get_ecr_repo_name()
        ecr_response = self.ecr_client.describe_images(
            repositoryName=ecr_repo_name, filter={"tagStatus": "TAGGED"}
        )
        ecr_images = ecr_response["imageDetails"]
        tag_to_digest = {}
        for img in ecr_images:
            for tag in img.get("imageTags", []):
                tag_to_digest[tag] = img["imageDigest"]

        for solver in aws_solvers:
            self.rn.set_solver(solver)
            cluster_name = self.rn.get_ecs_cluster_name()
            task_arns = self.ecs_client.list_tasks(
                cluster=cluster_name, desiredStatus="RUNNING"
            ).get("taskArns", [])
            if not task_arns:
                continue

            tasks = self.ecs_client.describe_tasks(cluster=cluster_name, tasks=task_arns)
            ecr_tag = self.rn.get_ecr_image_tag(solver)
            expected_digest = tag_to_digest.get(ecr_tag)
            if expected_digest is None:
                continue

            for task in tasks.get("tasks", []):
                for container in task.get("containers", []):
                    image_digest = container.get("imageDigest")
                    if image_digest and image_digest != expected_digest:
                        return True

        return False

    def get_current_desired_count(self, solver: str) -> int:
        """Get the current desired task count for a solver's leader service.

        Args:
            solver: Solver name

        Returns:
            Current desired count, or 0 if the service is not found
        """
        self.rn.set_solver(solver)
        cluster_name = self.rn.get_ecs_cluster_name()
        ecs_response = self.ecs_client.list_services(cluster=cluster_name)
        service_arns = ecs_response.get("serviceArns", [])
        leader_service = f"{self.rn.get_solver_stack_name()}-SolverLeaderService"

        for arn in service_arns:
            if leader_service in arn:
                desc = self.ecs_client.describe_services(cluster=cluster_name, services=[arn])
                services = desc.get("services", [])
                if services:
                    return services[0].get("desiredCount", 0)
        return 0

    def wait_for_tasks_stopped(self, aws_solvers: List[str], timeout_secs: int = 300) -> bool:
        """Poll until all running tasks have stopped.

        Args:
            aws_solvers: List of solver names to check
            timeout_secs: Maximum time to wait

        Returns:
            True if all tasks stopped, False if timed out
        """
        start = time.time()
        while time.time() - start < timeout_secs:
            total_running = sum(self.get_running_task_count(s) for s in aws_solvers)
            if total_running == 0:
                return True
            self.logger.info(f"Waiting for {total_running} task(s) to stop...")
            time.sleep(10)
        return False

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

        manager = EcsServiceManager(self.ctx, self.logger)
        aws_solvers = self.ctx.aws_solvers
        if manager.has_stale_images(aws_solvers):
            self.logger.warning(
                "Running tasks are using stale images that differ from ECR. "
                "Use `refresh-instances` to cycle tasks with the new images."
            )
            response = input("Would you like to refresh instead? [y/N] ").strip().lower()
            if response == "y":
                return RefreshCommand(self.ctx).execute()

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
        prompt_purge_queues(self.ctx, self.logger)
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


class RefreshCommand(CommandHandler):
    """Cycle ECS tasks to pick up new images from ECR."""

    def execute(self, **kwargs) -> int:
        """Stop running tasks, wait for drain, then restart with fresh images.

        Reads the current desired count per solver from ECS before stopping,
        and restores those same counts on restart.

        Returns:
            0 on success, 1 on error
        """
        self.logger.info("refresh: Cycling tasks to pick up new ECR images")
        aws_solvers = self.ctx.aws_solvers
        manager = EcsServiceManager(self.ctx, self.logger)

        # Read current desired count per solver before stopping
        solver_counts = {s: manager.get_current_desired_count(s) for s in aws_solvers}
        max_count = max(solver_counts.values())
        if max_count == 0:
            self.logger.error("No running tasks to refresh. Use `start-instances` instead.")
            return 1
        for solver, count in solver_counts.items():
            self.logger.info(f"  {solver}: {count} instance(s)")

        # Check queues and offer to purge
        prompt_purge_queues(self.ctx, self.logger)

        # Standby: keep EC2 instances but stop tasks
        self.logger.info("Putting solvers in standby...")
        result = self._execute_ecs_action_direct(manager, num_leaders=0, num_copies=max_count)
        if result != 0:
            return result

        # Wait for all tasks to stop
        self.logger.info("Waiting for running tasks to stop...")
        if not manager.wait_for_tasks_stopped(aws_solvers):
            self.logger.error("Timed out waiting for tasks to stop. Try again or use terminate-instances.")
            return 1

        self.logger.info("All tasks stopped. Starting with fresh images...")
        return StartCommand(self.ctx).execute(num_copies=max_count)

    def _execute_ecs_action_direct(self, manager: EcsServiceManager, num_leaders: int, num_copies: int) -> int:
        """Scale solvers without validation (used during refresh cycle)."""
        aws_solvers = self.ctx.aws_solvers
        for solver in aws_solvers:
            if not manager.scale_solver(solver, num_leaders, num_copies):
                return 1
        return 0
