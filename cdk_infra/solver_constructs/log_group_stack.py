from aws_cdk import (
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_logs as logs
from common import ResourceNamer
from constructs import Construct

from .resource_tagging_manager import ResourceTaggingManager


class LogGroupStack(Stack):
    def __init__(self, scope: Construct, construct_id, rn: ResourceNamer, **kwargs):
        """
        Creates the log group(s) for the solver stored in `rn`.

        Each solver gets a log group, which can be found in CloudWatch.
        Use the `ResourceNamer` to assign a consistent `log_group_name`.

        Callers must call `rn.set_solver()` before creating a new instance
        of this class.

        By default, logs are automatically deleted by AWS after two years.
        To change this value, edit `__init__()`.
        """
        kwargs["description"] = f"Log group(s) for solver {rn.solver}. Harness stdout gets logged here."
        super().__init__(scope, construct_id, **kwargs)
        rn.set_stack(self)

        # Initialize resource tagging manager
        tagging_manager = ResourceTaggingManager(project=rn.project, solver=rn.solver, environment="production")

        log_group_name = rn.get_log_group_name()
        self.log_group = logs.LogGroup(
            self,
            "SolverLogGroup",
            log_group_name=log_group_name,
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.TWO_YEARS,
        )

        # Apply tags to log group
        tagging_manager.apply_tags(self.log_group, "CLOUDWATCH_LOG_GROUP", {"LogGroupType": "SolverLogs"})
