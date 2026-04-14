"""S3 bucket in which to hold solver results."""

from aws_cdk import (
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_s3 as s3
from common import ResourceNamer
from constructs import Construct

from .resource_tagging_manager import ResourceTaggingManager


class S3ResultsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, rn: ResourceNamer, **kwargs):
        """
        Creates the S3 bucket that solver results are uploaded to.

        By default, destroying this bucket also deletes everything in the bucket.
        """
        kwargs["description"] = "S3 bucket for all solver results to go in."
        super().__init__(scope, construct_id, **kwargs)
        rn.set_stack(self)

        # Initialize resource tagging manager for global resources
        tagging_manager = ResourceTaggingManager(
            project=rn.project, solver="global", environment="production"  # This is a global resource
        )

        bucket_name = rn.get_bucket_name()
        self.bucket = s3.Bucket(
            self,
            "SolverResultsBucket",
            bucket_name=bucket_name,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Apply tags to S3 bucket
        tagging_manager.apply_tags(self.bucket, "S3_BUCKET", {"BucketType": "SolverResults"})
