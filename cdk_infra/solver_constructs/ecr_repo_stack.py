from aws_cdk import (
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_ecr as ecr
from common import ResourceNamer

from .resource_tagging_manager import ResourceTaggingManager


class EcrRepoStack(Stack):
    def __init__(self, scope, construct_id, rn: ResourceNamer, **kwargs):
        """
        Creates the ECR repository to upload solver Docker images to.

        When the ECR repository is destroyed, the corresponding uploaded
        images are also deleted.
        """
        kwargs["description"] = "ECR repository that solver images get uploaded to"
        super().__init__(scope, construct_id, **kwargs)
        rn.set_stack(self)

        # Initialize resource tagging manager for global resources
        tagging_manager = ResourceTaggingManager(
            project=rn.project, solver="global", environment="production"  # This is a global resource
        )

        ecr_name = rn.get_ecr_repo_name()
        self.ecr_repo = ecr.Repository(
            self,
            "SolverEcrRepo",
            repository_name=ecr_name,
            empty_on_delete=True,  # Delete all uploaded images when deleting the repo
            image_scan_on_push=True,  # Scan for vulnerabilities when uploading images
            lifecycle_rules=[
                ecr.LifecycleRule(
                    description="Remove untagged images except the latest one",
                    max_image_count=1,
                    tag_status=ecr.TagStatus.UNTAGGED,
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Apply tags to ECR repository
        tagging_manager.apply_tags(self.ecr_repo, "ECR_REPOSITORY", {"RepositoryType": "SolverImages"})
