"""Docker build and push commands."""

import base64

from runner.commands.base import CommandContext, CommandHandler


class BuildCommand(CommandHandler):
    """Build Docker images from config file."""

    def execute(self, **kwargs) -> int:
        """Build all Docker images defined in the project config.

        Returns:
            0 on success, 1 on error
        """
        self.logger.info("build: Build Docker images from a config file")
        self.sdc.build_images()
        return 0

    @property
    def sdc(self):
        return self.ctx.sdc


class PushCommand(CommandHandler):
    """Push built Docker images to AWS ECR repository."""

    def execute(self, **kwargs) -> int:
        """Push Docker images to ECR.

        Authenticates with ECR, tags images, and pushes them to the repository.

        Returns:
            0 on success, 1 on error
        """
        self.logger.info("push: Push built Docker images to an AWS ECR repository")

        if not self.ctx.project.has_image_to_push:
            self.logger.info('No images to push (all images had "push" set to false)')
            return 0

        ecr_client = self.ctx.get_client("ecr")
        rn = self.ctx.rn

        # Query ECR over boto3 for login credentials
        token = ecr_client.get_authorization_token()

        # Extract the ECR Docker endpoint for the account and provided region
        # It should look something like `<acct#>.dkr.ecr.<region>.amazonaws.com`
        # We strip the "https://" prefix because `docker.login()` doesn't like it
        ecr_endpoint = token["authorizationData"][0]["proxyEndpoint"].replace("https://", "")
        ecr_repo = f"{ecr_endpoint}/{rn.get_ecr_repo_name()}"

        # Get the temporary (~12 hour) authorization token for this AWS profile
        # This is equivalent to running `% aws ecr get-login-password`
        auth_token = token["authorizationData"][0]["authorizationToken"]
        _, password = base64.b64decode(auth_token).decode().split(":")

        # Log in to ECR using the AWS CLI method (more reliable than Python SDK)
        sdc = self.ctx.sdc
        sdc.log_in_to_aws(ecr_endpoint, self.ctx.project.region)
        if not sdc.tag_and_push_images(ecr_repo):
            self.logger.error("Failed to push images to ECR. Check authentication and try again.")
            return 1

        return 0
