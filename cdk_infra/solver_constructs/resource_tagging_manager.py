"""Resource tagging management for consistent AWS resource tagging."""

from datetime import datetime
from typing import Optional

from aws_cdk import Tags
from constructs import Construct


class ResourceTaggingManager:
    """
    Manages consistent tagging for all AWS resources in the SATcomp infrastructure.

    Provides standardized tag schema and methods to apply tags to CDK constructs.
    """

    # Standard tag keys
    PROJECT_TAG = "Project"
    SOLVER_TAG = "Solver"
    RESOURCE_TYPE_TAG = "ResourceType"
    CREATED_BY_TAG = "CreatedBy"
    CREATED_AT_TAG = "CreatedAt"
    ENVIRONMENT_TAG = "Environment"
    MANAGED_BY_TAG = "ManagedBy"
    COST_CENTER_TAG = "CostCenter"

    def __init__(self, project: str, solver: str, environment: str = "production"):
        """
        Initialize tagging manager with project context.

        Args:
            project: Project name (e.g., "satcomp25")
            solver: Solver name (e.g., "mallob")
            environment: Environment name (default: "production")
        """
        self.project = project.lower()
        self.solver = solver.lower()
        self.environment = environment.lower()
        self.created_at = datetime.utcnow().isoformat()

    def get_standard_tags(self, resource_type: str) -> dict[str, str]:
        """
        Get standard tags for a resource type.

        Args:
            resource_type: Type of resource (e.g., "ECS", "EC2", "VPC")

        Returns:
            Dictionary of standard tags
        """
        return {
            self.PROJECT_TAG: self.project,
            self.SOLVER_TAG: self.solver,
            self.RESOURCE_TYPE_TAG: resource_type,
            self.CREATED_BY_TAG: "satcomp-infrastructure",
            self.CREATED_AT_TAG: self.created_at,
            self.ENVIRONMENT_TAG: self.environment,
            self.MANAGED_BY_TAG: "CDK",
            self.COST_CENTER_TAG: f"{self.project}-{self.solver}",
        }

    def apply_tags(
        self, construct: Construct, resource_type: str, additional_tags: Optional[dict[str, str]] = None
    ) -> None:
        """
        Apply tags to a CDK construct.

        Args:
            construct: CDK construct to tag
            resource_type: Type of resource being tagged
            additional_tags: Optional additional tags to apply
        """
        # Get standard tags
        tags = self.get_standard_tags(resource_type)

        # Add any additional tags
        if additional_tags:
            tags.update(additional_tags)

        # Apply tags to the construct
        for key, value in tags.items():
            Tags.of(construct).add(key, value)

    def validate_tags(self, tags: dict[str, str]) -> list[str]:
        """
        Validate that required tags are present and properly formatted.

        Args:
            tags: Dictionary of tags to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        required_tags = [
            self.PROJECT_TAG,
            self.SOLVER_TAG,
            self.RESOURCE_TYPE_TAG,
            self.CREATED_BY_TAG,
            self.CREATED_AT_TAG,
            self.ENVIRONMENT_TAG,
            self.MANAGED_BY_TAG,
            self.COST_CENTER_TAG,
        ]

        # Check for missing required tags
        for tag in required_tags:
            if tag not in tags:
                errors.append(f"Missing required tag: {tag}")
            elif not tags[tag] or not tags[tag].strip():
                errors.append(f"Empty value for required tag: {tag}")

        # Validate tag value formats
        if self.PROJECT_TAG in tags and not tags[self.PROJECT_TAG].islower():
            errors.append(f"{self.PROJECT_TAG} tag must be lowercase")

        if self.SOLVER_TAG in tags and not tags[self.SOLVER_TAG].islower():
            errors.append(f"{self.SOLVER_TAG} tag must be lowercase")

        if self.ENVIRONMENT_TAG in tags and tags[self.ENVIRONMENT_TAG] not in ["production", "development", "testing"]:
            errors.append(f"{self.ENVIRONMENT_TAG} tag must be one of: production, development, testing")

        # Validate timestamp format
        if self.CREATED_AT_TAG in tags:
            try:
                datetime.fromisoformat(tags[self.CREATED_AT_TAG].replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{self.CREATED_AT_TAG} tag must be in ISO 8601 format")

        return errors

    @staticmethod
    def get_tag_filter(project: str, solver: str = None) -> list[dict]:
        """
        Get AWS tag filters for resource queries.

        Args:
            project: Project name to filter by
            solver: Optional solver name to filter by

        Returns:
            List of AWS tag filter dictionaries
        """
        filters = [{"Name": f"tag:{ResourceTaggingManager.PROJECT_TAG}", "Values": [project.lower()]}]

        if solver:
            filters.append({"Name": f"tag:{ResourceTaggingManager.SOLVER_TAG}", "Values": [solver.lower()]})

        return filters

    @staticmethod
    def get_resource_group_query(project: str, solver: str = None) -> dict:
        """
        Get AWS Resource Groups query for finding tagged resources.

        Args:
            project: Project name to filter by
            solver: Optional solver name to filter by

        Returns:
            Resource Groups query dictionary
        """
        tag_filters = [{"Key": ResourceTaggingManager.PROJECT_TAG, "Values": [project.lower()]}]

        if solver:
            tag_filters.append({"Key": ResourceTaggingManager.SOLVER_TAG, "Values": [solver.lower()]})

        return {
            "Type": "TAG_FILTERS_1_0",
            "Query": {"ResourceTypeFilters": ["AWS::AllSupported"], "TagFilters": tag_filters},
        }
