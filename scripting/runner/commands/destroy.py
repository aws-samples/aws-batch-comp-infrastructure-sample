"""Destroy command for CDK infrastructure."""

from runner.commands.base import CommandContext, CommandHandler
from runner.commands.cdk import CdkHelper
from runner.runner_cli import TeardownSubcommand
from runner.runner_teardown import TeardownManager


class DestroyCommand(CommandHandler):
    """Tear down AWS infrastructure using CDK."""

    def execute(self, opt: TeardownSubcommand = TeardownSubcommand.ALL, **kwargs) -> int:
        """Tear down CDK stacks based on the specified option.

        For destroy all, includes verification and cleanup of orphaned resources.

        Args:
            opt: TeardownSubcommand specifying what to destroy

        Returns:
            0 on success, 1 on error
        """
        opt.print_header_message()

        cdk = CdkHelper(self.ctx.cdk_path, self.ctx.rn)
        aws_solvers = self.ctx.aws_solvers
        project = self.ctx.project

        # Initialize teardown manager for enhanced cleanup verification
        teardown_manager = TeardownManager(project)

        if opt == TeardownSubcommand.ALL:
            return self._destroy_all(cdk, teardown_manager, project)
        elif opt == TeardownSubcommand.SOLVERS:
            return self._destroy_solvers(cdk, teardown_manager, aws_solvers)
        elif opt == TeardownSubcommand.LOGS:
            return cdk.destroy_logs(aws_solvers)
        elif opt == TeardownSubcommand.VPC:
            return cdk.destroy_vpc()
        elif opt == TeardownSubcommand.ECR:
            return cdk.destroy_ecr_repo()
        elif opt == TeardownSubcommand.S3:
            return cdk.destroy_s3()
        else:
            self.logger.error("Error: Unknown `teardown` option")
            return 1

    def _destroy_all(self, cdk: CdkHelper, teardown_manager: TeardownManager, project) -> int:
        """Destroy all resources with verification.

        Args:
            cdk: CdkHelper instance
            teardown_manager: TeardownManager for cleanup verification
            project: ProjectConfig

        Returns:
            0 on success, 1 on error
        """
        # First show what resources exist before CDK destroy
        self.logger.info("Checking existing resources before CDK destroy...")
        preview_resources = teardown_manager.preview_teardown()
        if preview_resources:
            self.logger.info(f"Found {len(preview_resources)} tagged resources that will be tracked during destroy")

        # Execute CDK destroy
        result = cdk.destroy_all()
        if result != 0:
            return result

        # Verify cleanup and handle any orphaned resources
        self.logger.info("Verifying cleanup and checking for orphaned resources...")
        cleanup_report = teardown_manager.verify_cleanup(project.project)
        if cleanup_report.orphaned_resources:
            self.logger.warning(f"Found {len(cleanup_report.orphaned_resources)} orphaned resources after CDK destroy")
            self.logger.info("Attempting to clean up orphaned resources...")
            cleaned = teardown_manager.force_cleanup_orphaned()
            self.logger.info(f"Force cleaned {len(cleaned)} orphaned resources")
        else:
            self.logger.info("CDK destroy completed successfully with no orphaned resources")

        return 0

    def _destroy_solvers(self, cdk: CdkHelper, teardown_manager: TeardownManager, aws_solvers) -> int:
        """Destroy solver stacks with verification.

        Args:
            cdk: CdkHelper instance
            teardown_manager: TeardownManager for cleanup verification
            aws_solvers: List of solver names

        Returns:
            0 on success, 1 on error
        """
        result = cdk.destroy_solvers(aws_solvers)
        if result != 0:
            return result

        # Verify solver-specific cleanup
        self.logger.info("Verifying solver resource cleanup...")
        for solver in aws_solvers:
            remaining = teardown_manager.preview_teardown(solver=solver)
            if remaining:
                self.logger.warning(f"Found {len(remaining)} remaining resources for solver {solver}")
                for resource in remaining:
                    self.logger.warning(f"  {resource['resource_type']}: {resource['resource_arn']}")

        return 0
