"""SSM Configuration Manager for EC2 instances in ECS clusters."""

from typing import List

from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from common.constants import (
    SSM_COMMAND_WORKERS_LIMIT,
    SSM_HEALTH_FREQUENCY_MINUTES,
    SSM_NEGATIVE_HEALTH_FREQUENCY_MINUTES,
    SSM_STOP_TIMEOUT_MILLIS,
)


class SsmConfigManager:
    """
    Manages SSM (Systems Manager) configuration for EC2 instances.

    This class provides methods to configure EC2 instances with proper SSM agent
    settings to eliminate "missing patching agent" warnings and ensure proper
    patch management capabilities.
    """

    @staticmethod
    def configure_user_data(user_data: ec2.UserData, disable_patching: bool = True) -> None:
        """
        Add SSM configuration commands to EC2 user data.

        Args:
            user_data: The EC2 UserData object to modify
            disable_patching: Whether to disable patch scanning to prevent warnings
        """
        # Install SSM agent if not already present (should be on Amazon Linux 2023)
        user_data.add_commands(
            "# Configure SSM Agent",
            "yum install -y amazon-ssm-agent",
            "systemctl enable amazon-ssm-agent",
            "systemctl start amazon-ssm-agent",
        )

        if disable_patching:
            # Configure SSM agent to disable patch scanning to prevent warnings
            # This creates a configuration that tells SSM not to scan for patches
            user_data.add_commands(
                "# Configure SSM to disable patch scanning warnings",
                "mkdir -p /etc/amazon/ssm",
                "cat > /etc/amazon/ssm/amazon-ssm-agent.json << 'EOF'",
                "{",
                '  "Agent": {',
                '    "Region": "${AWS::Region}",',
                '    "AllowedUpdates": {',
                '      "PatchingEnabled": false',
                "    }",
                "  },",
                '  "Mds": {',
                f'    "CommandWorkersLimit": {SSM_COMMAND_WORKERS_LIMIT},',
                f'    "StopTimeoutMillis": {SSM_STOP_TIMEOUT_MILLIS}',
                "  },",
                '  "Ssm": {',
                f'    "HealthFrequencyMinutes": {SSM_HEALTH_FREQUENCY_MINUTES},',
                f'    "NegativeHealthFrequencyMinutes": {SSM_NEGATIVE_HEALTH_FREQUENCY_MINUTES}',
                "  }",
                "}",
                "EOF",
                "# Restart SSM agent to apply configuration",
                "systemctl restart amazon-ssm-agent",
            )

        # Verify SSM agent is running
        user_data.add_commands(
            "# Verify SSM agent status",
            "systemctl status amazon-ssm-agent --no-pager || echo 'SSM agent status check failed'",
        )

    @staticmethod
    def get_ssm_policies() -> List[iam.PolicyStatement]:
        """
        Return IAM policy statements for SSM agent functionality.

        Returns:
            List of IAM PolicyStatement objects for SSM permissions
        """
        policies = []

        # Core SSM permissions for agent functionality
        core_ssm_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # Core SSM agent permissions
                "ssm:UpdateInstanceInformation",
                "ssm:SendCommand",
                "ssm:ListCommandInvocations",
                "ssm:DescribeInstanceInformation",
                "ssm:GetDeployablePatchSnapshotForInstance",
                "ssm:GetDefaultPatchBaseline",
                "ssm:GetManifest",
                "ssm:GetParameter",
                "ssm:GetParameters",
                "ssm:GetParametersByPath",
                "ssm:PutInventory",
                "ssm:PutComplianceItems",
                "ssm:PutConfigurePackageResult",
                "ssm:UpdateAssociationStatus",
                "ssm:UpdateInstanceAssociationStatus",
                # EC2 permissions needed for SSM
                "ec2:DescribeInstanceStatus",
                "ec2:DescribeInstances",
                # CloudWatch permissions for SSM logging
                "logs:PutLogEvents",
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:DescribeLogStreams",
                "logs:DescribeLogGroups",
            ],
            resources=["*"],
        )
        policies.append(core_ssm_policy)

        # S3 permissions for SSM document storage and patch downloads
        s3_ssm_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "s3:GetBucketLocation",
                "s3:PutObject",
                "s3:GetObject",
                "s3:GetEncryptionConfiguration",
                "s3:AbortMultipartUpload",
                "s3:ListMultipartUploadParts",
                "s3:ListBucket",
                "s3:ListBucketMultipartUploads",
            ],
            resources=[
                "arn:aws:s3:::aws-ssm-*/*",
                "arn:aws:s3:::aws-windows-downloads-*/*",
                "arn:aws:s3:::amazon-ssm-*/*",
                "arn:aws:s3:::amazon-ssm-packages-*/*",
                "arn:aws:s3:::*-birdwatcher-prod",
                "arn:aws:s3:::*-birdwatcher-prod/*",
                "arn:aws:s3:::aws-ssm-distributor-file-*",
                "arn:aws:s3:::aws-ssm-distributor-file-*/*",
            ],
        )
        policies.append(s3_ssm_policy)

        return policies

    @staticmethod
    def get_managed_policies() -> List[str]:
        """
        Return list of AWS managed policy ARNs for SSM functionality.

        Returns:
            List of AWS managed policy names for SSM
        """
        return ["AmazonSSMManagedInstanceCore", "CloudWatchAgentServerPolicy"]

    @staticmethod
    def add_ssm_permissions_to_role(role: iam.Role) -> None:
        """
        Add SSM permissions to an existing IAM role.

        Args:
            role: The IAM role to add SSM permissions to
        """
        # Add managed policies
        for policy_name in SsmConfigManager.get_managed_policies():
            role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(policy_name))

        # Add custom policy statements
        for policy_statement in SsmConfigManager.get_ssm_policies():
            role.add_to_policy(policy_statement)
