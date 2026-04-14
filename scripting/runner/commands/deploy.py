"""Deploy command for CDK infrastructure."""

from runner.commands.base import CommandContext, CommandHandler
from runner.commands.cdk import CdkHelper
from runner.runner_cli import ProvisionSubcommand


class DeployCommand(CommandHandler):
    """Provision AWS infrastructure using CDK."""

    def execute(self, opt: ProvisionSubcommand = ProvisionSubcommand.ALL, **kwargs) -> int:
        """Provision CDK stacks based on the specified option.

        Args:
            opt: ProvisionSubcommand specifying what to provision

        Returns:
            0 on success, 1 on error
        """
        cdk = CdkHelper(self.ctx.cdk_path, self.ctx.rn)
        aws_solvers = self.ctx.aws_solvers

        if opt == ProvisionSubcommand.ALL:
            return cdk.deploy_all()
        elif opt == ProvisionSubcommand.SOLVERS:
            return cdk.deploy_solvers(aws_solvers)
        elif opt == ProvisionSubcommand.LOGS:
            return cdk.deploy_logs(aws_solvers)
        elif opt == ProvisionSubcommand.VPC:
            return cdk.deploy_vpc()
        elif opt == ProvisionSubcommand.ECR:
            return cdk.deploy_ecr_repo()
        elif opt == ProvisionSubcommand.S3:
            return cdk.deploy_s3()
        else:
            self.logger.error("Error: Unknown `provision` option")
            return 1


class BootstrapCommand(CommandHandler):
    """Bootstrap CDK for AWS account."""

    def execute(self, **kwargs) -> int:
        """Run CDK bootstrap.

        Returns:
            0 on success, 1 on error
        """
        cdk = CdkHelper(self.ctx.cdk_path)
        return cdk.bootstrap()
