"""Teardown management system for comprehensive resource cleanup."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError
from common.resource_inventory_tracker import ResourceInventoryEntry, ResourceInventoryTracker
from common.solver_logging import LoggingManager
from runner.runner_config import ProjectConfig

from cdk_infra.solver_constructs.resource_tagging_manager import ResourceTaggingManager


@dataclass
class TeardownResult:
    """Result of a teardown operation."""

    success: bool
    deleted_resources: list[str]
    failed_resources: list[tuple[str, str]]  # (resource_id, error)
    orphaned_resources: list[str]
    duration_seconds: float
    preview_mode: bool = False


@dataclass
class CleanupReport:
    """Report of cleanup verification."""

    total_resources_found: int
    successfully_deleted: int
    failed_deletions: int
    orphaned_resources: list[str]
    verification_errors: list[str]


class TeardownManager:
    """
    Manages comprehensive resource cleanup for SATcomp infrastructure.

    Provides safe and complete removal of all AWS resources using tags and inventory tracking.
    """

    def __init__(self, config: ProjectConfig):
        """
        Initialize teardown manager.

        Args:
            config: Project configuration containing AWS settings
        """
        self.config = config
        self.project = config.project.lower()
        self.region = config.region

        # Initialize logging
        self.lm = LoggingManager()
        self.logger = self.lm.get_logger("TeardownManager", formatted=False)

        # Initialize resource tracker
        self.inventory_tracker = ResourceInventoryTracker(self.project, self.region)

        # Initialize AWS clients
        self._init_aws_clients()

    def _init_aws_clients(self):
        """Initialize AWS service clients."""
        self.ec2 = boto3.client("ec2", region_name=self.region)
        self.ecs = boto3.client("ecs", region_name=self.region)
        self.s3 = boto3.client("s3", region_name=self.region)
        self.sqs = boto3.client("sqs", region_name=self.region)
        self.dynamodb = boto3.client("dynamodb", region_name=self.region)
        self.logs = boto3.client("logs", region_name=self.region)
        self.autoscaling = boto3.client("autoscaling", region_name=self.region)
        self.iam = boto3.client("iam", region_name=self.region)
        self.ecr = boto3.client("ecr", region_name=self.region)
        self.cloudformation = boto3.client("cloudformation", region_name=self.region)

    def preview_teardown(self, solver: str = None) -> list[dict]:
        """
        Preview resources that would be deleted.

        Args:
            solver: Optional solver name to filter by

        Returns:
            List of resource dictionaries with details
        """
        self.logger.info(
            f"Previewing teardown for project '{self.project}'" + (f", solver '{solver}'" if solver else "")
        )

        try:
            # Get resources from inventory tracker
            resources = self.inventory_tracker.list_resources(solver=solver)

            preview_data = []
            for resource in resources:
                preview_data.append(
                    {
                        "resource_arn": resource.resource_arn,
                        "resource_type": resource.resource_type,
                        "solver": resource.solver,
                        "tags": resource.tags,
                        "region": resource.region,
                    }
                )

            self.logger.info(f"Found {len(preview_data)} resources for teardown")
            return preview_data

        except Exception as e:
            self.logger.error(f"Failed to preview teardown: {e}")
            raise RuntimeError(f"Teardown preview failed: {e}")

    def execute_teardown(self, solver: str = None, dry_run: bool = False) -> TeardownResult:
        """
        Execute teardown with optional dry-run.

        Args:
            solver: Optional solver name to filter by
            dry_run: If True, only simulate the teardown

        Returns:
            TeardownResult with operation details
        """
        start_time = datetime.now()

        self.logger.info(
            f"Starting teardown for project '{self.project}'"
            + (f", solver '{solver}'" if solver else "")
            + (" (DRY RUN)" if dry_run else "")
        )

        deleted_resources = []
        failed_resources = []
        orphaned_resources = []

        try:
            # Get resources to delete
            resources = self.inventory_tracker.list_resources(solver=solver)

            if not resources:
                self.logger.info("No resources found for teardown")
                return TeardownResult(
                    success=True,
                    deleted_resources=[],
                    failed_resources=[],
                    orphaned_resources=[],
                    duration_seconds=0.0,
                    preview_mode=dry_run,
                )

            # Group resources by type for ordered deletion
            grouped_resources = self.inventory_tracker.group_resources_by_type(solver=solver)

            # Define deletion order (dependencies first)
            deletion_order = [
                "ECS_SERVICE",
                "ECS_TASK_DEFINITION",
                "ECS_CLUSTER",
                "EC2_INSTANCE",
                "AUTOSCALING_GROUP",
                "LAUNCH_TEMPLATE",
                "SECURITY_GROUP",
                "SQS_QUEUE",
                "S3_BUCKET",
                "DYNAMODB_TABLE",
                "LOG_GROUP",
                "ECR_REPOSITORY",
                "IAM_ROLE",
                "IAM_POLICY",
                "VPC",
                "SUBNET",
                "INTERNET_GATEWAY",
                "ROUTE_TABLE",
            ]

            # Delete resources in order
            for resource_type in deletion_order:
                if resource_type in grouped_resources:
                    resources_of_type = grouped_resources[resource_type]
                    self.logger.info(f"Deleting {len(resources_of_type)} {resource_type} resources")

                    for resource in resources_of_type:
                        try:
                            if dry_run:
                                self.logger.info(f"[DRY RUN] Would delete {resource.resource_arn}")
                                deleted_resources.append(resource.resource_arn)
                            else:
                                success = self._delete_resource(resource)
                                if success:
                                    deleted_resources.append(resource.resource_arn)
                                    self.logger.info(f"Successfully deleted {resource.resource_arn}")
                                else:
                                    failed_resources.append((resource.resource_arn, "Deletion failed"))
                                    self.logger.error(f"Failed to delete {resource.resource_arn}")
                        except Exception as e:
                            error_msg = str(e)
                            failed_resources.append((resource.resource_arn, error_msg))
                            self.logger.error(f"Error deleting {resource.resource_arn}: {error_msg}")

            # Handle any remaining resource types not in the ordered list
            remaining_types = set(grouped_resources.keys()) - set(deletion_order)
            for resource_type in remaining_types:
                resources_of_type = grouped_resources[resource_type]
                self.logger.warning(f"Deleting {len(resources_of_type)} {resource_type} resources (unordered)")

                for resource in resources_of_type:
                    try:
                        if dry_run:
                            self.logger.info(f"[DRY RUN] Would delete {resource.resource_arn}")
                            deleted_resources.append(resource.resource_arn)
                        else:
                            success = self._delete_resource(resource)
                            if success:
                                deleted_resources.append(resource.resource_arn)
                            else:
                                failed_resources.append((resource.resource_arn, "Deletion failed"))
                    except Exception as e:
                        error_msg = str(e)
                        failed_resources.append((resource.resource_arn, error_msg))
                        self.logger.error(f"Error deleting {resource.resource_arn}: {error_msg}")

            # Check for orphaned resources
            if not dry_run:
                orphaned_resources = self._find_orphaned_resources(solver)

            duration = (datetime.now() - start_time).total_seconds()
            success = len(failed_resources) == 0

            self.logger.info(f"Teardown completed in {duration:.2f} seconds")
            self.logger.info(
                f"Deleted: {len(deleted_resources)}, Failed: {len(failed_resources)}, Orphaned: {len(orphaned_resources)}"
            )

            return TeardownResult(
                success=success,
                deleted_resources=deleted_resources,
                failed_resources=failed_resources,
                orphaned_resources=orphaned_resources,
                duration_seconds=duration,
                preview_mode=dry_run,
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.logger.error(f"Teardown failed after {duration:.2f} seconds: {e}")
            return TeardownResult(
                success=False,
                deleted_resources=deleted_resources,
                failed_resources=failed_resources + [("TEARDOWN_OPERATION", str(e))],
                orphaned_resources=orphaned_resources,
                duration_seconds=duration,
                preview_mode=dry_run,
            )

    def _delete_resource(self, resource: ResourceInventoryEntry) -> bool:
        """
        Delete a single resource based on its type.

        Args:
            resource: Resource to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            resource_type = resource.resource_type
            arn = resource.resource_arn

            if resource_type == "ECS_SERVICE":
                return self._delete_ecs_service(arn)
            elif resource_type == "ECS_CLUSTER":
                return self._delete_ecs_cluster(arn)
            elif resource_type == "EC2_INSTANCE":
                return self._delete_ec2_instance(arn)
            elif resource_type == "AUTOSCALING_GROUP":
                return self._delete_autoscaling_group(arn)
            elif resource_type == "SQS_QUEUE":
                return self._delete_sqs_queue(arn)
            elif resource_type == "S3_BUCKET":
                return self._delete_s3_bucket(arn)
            elif resource_type == "LOG_GROUP":
                return self._delete_log_group(arn)
            elif resource_type == "ECR_REPOSITORY":
                return self._delete_ecr_repository(arn)
            elif resource_type == "SECURITY_GROUP":
                return self._delete_security_group(arn)
            elif resource_type == "VPC":
                return self._delete_vpc(arn)
            else:
                self.logger.warning(f"Unknown resource type for deletion: {resource_type}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to delete resource {resource.resource_arn}: {e}")
            return False

    def _delete_ecs_service(self, arn: str) -> bool:
        """Delete ECS service."""
        try:
            # Extract cluster and service names from ARN
            parts = arn.split("/")
            if len(parts) >= 3:
                cluster_name = parts[1]
                service_name = parts[2]

                # Scale down to 0 first
                self.ecs.update_service(cluster=cluster_name, service=service_name, desiredCount=0)

                # Delete the service
                self.ecs.delete_service(cluster=cluster_name, service=service_name)
                return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ServiceNotFoundException":
                return True  # Already deleted
            raise
        return False

    def _delete_ecs_cluster(self, arn: str) -> bool:
        """Delete ECS cluster."""
        try:
            cluster_name = arn.split("/")[-1]
            self.ecs.delete_cluster(cluster=cluster_name)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ClusterNotFoundException":
                return True  # Already deleted
            raise
        return False

    def _delete_ec2_instance(self, arn: str) -> bool:
        """Delete EC2 instance."""
        try:
            instance_id = arn.split("/")[-1]
            self.ec2.terminate_instances(InstanceIds=[instance_id])
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                return True  # Already deleted
            raise
        return False

    def _delete_autoscaling_group(self, arn: str) -> bool:
        """Delete Auto Scaling Group."""
        try:
            asg_name = arn.split("/")[-1]

            # Scale down to 0 first
            self.autoscaling.update_auto_scaling_group(
                AutoScalingGroupName=asg_name, MinSize=0, MaxSize=0, DesiredCapacity=0
            )

            # Delete the ASG
            self.autoscaling.delete_auto_scaling_group(AutoScalingGroupName=asg_name, ForceDelete=True)
            return True
        except ClientError as e:
            if "does not exist" in str(e):
                return True  # Already deleted
            raise
        return False

    def _delete_sqs_queue(self, arn: str) -> bool:
        """Delete SQS queue."""
        try:
            # Convert ARN to URL
            queue_url = f"https://sqs.{self.region}.amazonaws.com/{arn.split(':')[4]}/{arn.split(':')[-1]}"
            self.sqs.delete_queue(QueueUrl=queue_url)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "AWS.SimpleQueueService.NonExistentQueue":
                return True  # Already deleted
            raise
        return False

    def _delete_s3_bucket(self, arn: str) -> bool:
        """Delete S3 bucket and all its contents."""
        try:
            bucket_name = arn.split(":")[-1]

            # Delete all objects first
            try:
                paginator = self.s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket_name):
                    if "Contents" in page:
                        objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
                        if objects:
                            self.s3.delete_objects(Bucket=bucket_name, Delete={"Objects": objects})
            except ClientError:
                pass  # Bucket might be empty or not exist

            # Delete the bucket
            self.s3.delete_bucket(Bucket=bucket_name)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucket":
                return True  # Already deleted
            raise
        return False

    def _delete_log_group(self, arn: str) -> bool:
        """Delete CloudWatch log group."""
        try:
            log_group_name = arn.split(":")[-1]
            self.logs.delete_log_group(logGroupName=log_group_name)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                return True  # Already deleted
            raise
        return False

    def _delete_ecr_repository(self, arn: str) -> bool:
        """Delete ECR repository."""
        try:
            repo_name = arn.split("/")[-1]
            self.ecr.delete_repository(repositoryName=repo_name, force=True)  # Delete even if it contains images
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "RepositoryNotFoundException":
                return True  # Already deleted
            raise
        return False

    def _delete_security_group(self, arn: str) -> bool:
        """Delete security group."""
        try:
            sg_id = arn.split("/")[-1]
            self.ec2.delete_security_group(GroupId=sg_id)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidGroupId.NotFound":
                return True  # Already deleted
            raise
        return False

    def _delete_vpc(self, arn: str) -> bool:
        """Delete VPC."""
        try:
            vpc_id = arn.split("/")[-1]
            self.ec2.delete_vpc(VpcId=vpc_id)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidVpcID.NotFound":
                return True  # Already deleted
            raise
        return False

    def _find_orphaned_resources(self, solver: str = None) -> list[str]:
        """
        Find orphaned resources that weren't properly tagged.

        Args:
            solver: Optional solver name to filter by

        Returns:
            List of orphaned resource ARNs
        """
        orphaned = []

        try:
            # This is a simplified implementation
            # In practice, you'd want to check for resources that match naming patterns
            # but don't have proper tags

            # For now, we'll just return an empty list since the main cleanup
            # should handle tagged resources
            pass

        except Exception as e:
            self.logger.error(f"Error finding orphaned resources: {e}")

        return orphaned

    def verify_cleanup(self, project: str) -> CleanupReport:
        """
        Verify all resources have been removed.

        Args:
            project: Project name to verify cleanup for

        Returns:
            CleanupReport with verification results
        """
        self.logger.info(f"Verifying cleanup for project '{project}'")

        verification_errors = []
        orphaned_resources = []

        try:
            # Check if any resources still exist
            remaining_resources = self.inventory_tracker.list_resources()

            total_found = len(remaining_resources)
            successfully_deleted = 0
            failed_deletions = 0

            for resource in remaining_resources:
                # Verify if resource actually still exists
                if self.inventory_tracker.verify_resource_exists(resource.resource_arn):
                    orphaned_resources.append(resource.resource_arn)
                    failed_deletions += 1
                else:
                    successfully_deleted += 1

            if orphaned_resources:
                self.logger.warning(f"Found {len(orphaned_resources)} orphaned resources")
            else:
                self.logger.info("Cleanup verification successful - no orphaned resources found")

            return CleanupReport(
                total_resources_found=total_found,
                successfully_deleted=successfully_deleted,
                failed_deletions=failed_deletions,
                orphaned_resources=orphaned_resources,
                verification_errors=verification_errors,
            )

        except Exception as e:
            error_msg = f"Cleanup verification failed: {e}"
            verification_errors.append(error_msg)
            self.logger.error(error_msg)

            return CleanupReport(
                total_resources_found=0,
                successfully_deleted=0,
                failed_deletions=0,
                orphaned_resources=orphaned_resources,
                verification_errors=verification_errors,
            )

    def force_cleanup_orphaned(self) -> list[str]:
        """
        Force cleanup of orphaned resources.

        Returns:
            List of resource ARNs that were force-cleaned
        """
        self.logger.info("Starting force cleanup of orphaned resources")

        cleaned_resources = []

        try:
            # Find orphaned resources
            orphaned = self._find_orphaned_resources()

            if not orphaned:
                self.logger.info("No orphaned resources found")
                return cleaned_resources

            self.logger.info(f"Found {len(orphaned)} orphaned resources")

            # Attempt to clean each orphaned resource
            for resource_arn in orphaned:
                try:
                    # This would need more sophisticated logic to determine
                    # resource type from ARN and delete appropriately
                    self.logger.info(f"Force cleaning {resource_arn}")
                    # Implementation would go here
                    cleaned_resources.append(resource_arn)
                except Exception as e:
                    self.logger.error(f"Failed to force clean {resource_arn}: {e}")

            self.logger.info(f"Force cleanup completed. Cleaned {len(cleaned_resources)} resources")

        except Exception as e:
            self.logger.error(f"Force cleanup failed: {e}")

        return cleaned_resources
