"""Resource inventory tracking system using AWS tags and Resource Groups API."""

from dataclasses import dataclass
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError


@dataclass
class ResourceInventoryEntry:
    """Represents a resource discovered via tags."""

    resource_arn: str
    resource_type: str
    solver: str
    project: str
    tags: dict[str, str]
    region: str


class ResourceInventoryTracker:
    """
    Tracks AWS resources using tags and AWS Resource Groups API.

    This is a simpler approach than DynamoDB - uses existing AWS infrastructure
    to track resources via consistent tagging.
    """

    def __init__(self, project: str, region: str):
        """
        Initialize tracker with project context.

        Args:
            project: Project name (e.g., "satcomp25")
            region: AWS region
        """
        self.project = project.lower()
        self.region = region

        # Initialize AWS clients
        self.resource_groups = boto3.client("resource-groups", region_name=region)
        self.ec2 = boto3.client("ec2", region_name=region)
        self.ecs = boto3.client("ecs", region_name=region)
        self.s3 = boto3.client("s3", region_name=region)
        self.sqs = boto3.client("sqs", region_name=region)
        self.dynamodb = boto3.client("dynamodb", region_name=region)
        self.logs = boto3.client("logs", region_name=region)

    def list_resources(self, solver: str = None, resource_type: str = None) -> list[ResourceInventoryEntry]:
        """
        List resources using AWS Resource Groups API with tag filters.

        Args:
            solver: Optional solver name filter
            resource_type: Optional resource type filter

        Returns:
            List of ResourceInventoryEntry objects
        """
        try:
            # Build tag filters
            tag_filters = [{"Key": "Project", "Values": [self.project]}]

            if solver:
                tag_filters.append({"Key": "Solver", "Values": [solver.lower()]})

            if resource_type:
                tag_filters.append({"Key": "ResourceType", "Values": [resource_type]})

            # Query using Resource Groups API
            import json

            query = {
                "Type": "TAG_FILTERS_1_0",
                "Query": json.dumps({"ResourceTypeFilters": ["AWS::AllSupported"], "TagFilters": tag_filters}),
            }

            response = self.resource_groups.search_resources(
                ResourceQuery=query, MaxResults=50  # Can be paginated if needed
            )

            entries = []
            for resource in response.get("ResourceIdentifiers", []):
                arn = resource["ResourceArn"]

                # Extract basic info from ARN since get_tags doesn't work reliably
                # ARN format: arn:aws:service:region:account:resource-type/resource-name
                try:
                    arn_parts = arn.split(":")
                    if len(arn_parts) >= 6:
                        service = arn_parts[2]
                        resource_part = arn_parts[5]

                        # Create a basic entry - tags will be empty but we have the resource
                        entry = ResourceInventoryEntry(
                            resource_arn=arn,
                            resource_type=service.upper(),
                            solver=solver or "unknown",
                            project=self.project,
                            tags={},  # Empty for now due to API limitations
                            region=self.region,
                        )
                        entries.append(entry)

                except Exception as e:
                    print(f"Warning: Could not parse ARN {arn}: {e}")
                    continue

            return entries

        except ClientError as e:
            raise RuntimeError(f"Failed to list resources: {e}")

    def get_resource_count(self) -> dict[str, int]:
        """
        Get count of resources by type.

        Returns:
            Dictionary mapping resource types to counts
        """
        resources = self.list_resources()
        counts = {}

        for resource in resources:
            resource_type = resource.resource_type
            counts[resource_type] = counts.get(resource_type, 0) + 1

        return counts

    def verify_resource_exists(self, resource_arn: str) -> bool:
        """
        Check if a resource still exists in AWS.

        Args:
            resource_arn: AWS resource ARN

        Returns:
            True if resource exists, False otherwise
        """
        try:
            # Try to get tags - if this succeeds, resource exists
            self.resource_groups.get_tags(Arn=resource_arn)
            return True
        except ClientError:
            return False

    def list_resources_by_solver(self, solver: str) -> list[ResourceInventoryEntry]:
        """
        List all resources for a specific solver.

        Args:
            solver: Solver name

        Returns:
            List of ResourceInventoryEntry objects for the solver
        """
        return self.list_resources(solver=solver)

    def list_all_project_resources(self) -> list[ResourceInventoryEntry]:
        """
        List all resources for the project.

        Returns:
            List of all ResourceInventoryEntry objects for the project
        """
        return self.list_resources()

    def get_resources_for_cleanup(self, solver: str = None) -> list[str]:
        """
        Get list of resource ARNs that should be cleaned up.

        Args:
            solver: Optional solver name to filter by

        Returns:
            List of resource ARNs to delete
        """
        resources = self.list_resources(solver=solver)
        return [resource.resource_arn for resource in resources]

    def group_resources_by_type(self, solver: str = None) -> dict[str, list[ResourceInventoryEntry]]:
        """
        Group resources by their type.

        Args:
            solver: Optional solver name to filter by

        Returns:
            Dictionary mapping resource types to lists of resources
        """
        resources = self.list_resources(solver=solver)
        grouped = {}

        for resource in resources:
            resource_type = resource.resource_type
            if resource_type not in grouped:
                grouped[resource_type] = []
            grouped[resource_type].append(resource)

        return grouped
