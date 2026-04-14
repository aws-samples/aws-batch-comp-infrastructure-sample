"""Shared VPC stack that all solvers use."""

from aws_cdk import (
    Stack,
)
from aws_cdk import aws_ec2 as ec2
from common.constants import (
    MAX_AVAILABILITY_ZONES,
    SUBNET_CIDR_MASK,
    TCP_PORT_RANGE_END,
    TCP_PORT_RANGE_START,
    VPC_CIDR,
    VPC_INTERNAL_CIDR,
)
from constructs import Construct

from .resource_tagging_manager import ResourceTaggingManager


class SolverVpcStack(Stack):
    """VPC, security groups, and endpoints for solver native-AWS infrastructure."""

    VPC_ID = "SolverVpc"
    VPC_SUBSET_ID = "VpcSubsetConfig"
    SECURITY_GROUP_ID = "VpcSecurityGroup"
    SECURITY_GROUP_OUTPUT = f"{SECURITY_GROUP_ID}Output"
    S3_VPC_ENDPOINT_ID = "S3VpcEndpoint"
    DYNAMO_VPC_ENDPOINT_ID = "DynamoVpcEndpoint"

    def __init__(self, scope: Construct, construct_id: str, project: str, **kwargs):
        """
        Creates a new global VPC that all solvers use as a subnet/shared cloud.

        The VPC is overall isolated from the Internet, except for SSH traffic
        as well as endpoints to various AWS services used to run solvers
        and submit jobs to solvers.

        Note to future developers:
        If the infrastructure changes to use new AWS services (such as Lambda
        or EFS), then new VPC endpoints must be added to the VPC.
        Make these edits in `self.add_vpc_endpoints()`.

        Args:
            scope: CDK app scope.
            construct_id: CloudFormation stack name.
            project: Project name used for resource tagging.
        """
        kwargs["description"] = "Shared isolated virtual private cloud and subnets for solvers to communicate over"
        super().__init__(scope, construct_id, **kwargs)

        # Initialize resource tagging manager for global VPC resources
        self.tagging_manager = ResourceTaggingManager(
            project=project, solver="global", environment="production"  # This is a global resource
        )

        # Define the VPC
        self.vpc = ec2.Vpc(
            self,
            self.VPC_ID,
            ip_addresses=ec2.IpAddresses.cidr(VPC_CIDR),
            max_azs=MAX_AVAILABILITY_ZONES,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=self.VPC_SUBSET_ID,
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=SUBNET_CIDR_MASK,
                ),
            ],
        )

        # Apply tags to VPC
        self.tagging_manager.apply_tags(self.vpc, "VPC", {"VpcType": "SolverVpc"})

        self.add_security_groups()
        self.add_vpc_endpoints()

    def add_security_groups(self):
        self.security_group = ec2.SecurityGroup(
            self,
            self.SECURITY_GROUP_ID,
            vpc=self.vpc,
            allow_all_outbound=True,
        )

        # Apply tags to security group
        self.tagging_manager.apply_tags(
            self.security_group, "SECURITY_GROUP", {"SecurityGroupType": "SolverSecurityGroup"}
        )

        # Allow internal VPC traffic
        self.security_group.add_ingress_rule(
            ec2.Peer.ipv4(VPC_INTERNAL_CIDR),
            ec2.Port.tcp_range(TCP_PORT_RANGE_START, TCP_PORT_RANGE_END),
            "Internal VPC traffic",
        )

    def add_vpc_endpoints(self):
        """
        Adds interface and gateway VPC endpoints to the VPC.

        The stack's VPC and security group need to be created before calling this function.
        The VPC must be stored under `self.vpc`,
        and the security group must be stored under `self.security_group`.
        """

        # We need special VPC endpoints to S3 and Dynamo:
        #   - S3 to upload solver results
        #   - Dynamo for distributed solvers to coordinate (see `/docs/design/`)
        # These special endpoints are needed because S3 and Dynamo are "public" services.
        # The good news is that these endpoints are free!
        # For more, see https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html
        s3_endpoint = ec2.GatewayVpcEndpoint(
            self,
            self.S3_VPC_ENDPOINT_ID,
            vpc=self.vpc,
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # Apply tags to S3 VPC endpoint
        self.tagging_manager.apply_tags(s3_endpoint, "VPC_ENDPOINT", {"EndpointType": "S3Gateway"})

        dynamo_endpoint = ec2.GatewayVpcEndpoint(
            self,
            self.DYNAMO_VPC_ENDPOINT_ID,
            vpc=self.vpc,
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
        )

        # Apply tags to DynamoDB VPC endpoint
        self.tagging_manager.apply_tags(dynamo_endpoint, "VPC_ENDPOINT", {"EndpointType": "DynamoGateway"})

        # Add the interface endpoints, to work with interal AWS services.
        # The AWS user gets charged $0.02 per endpoint per hour,
        # so we want to minimize the size of this list.
        # TODO if the distributed protocol is adapted to use EFS and/or Lambda,
        # then they must be added to this list ("lambda" and "efs")
        services = [
            "sqs",
            "logs",
            "monitoring",
            "ecr.dkr",  # Used by ECR to pull and initialize Docker images
            "ecr.api",  # Generally used by ECR
            # According to https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent.html,
            # messages sent over SSM might get sent back via ec2messages, so we need an endpoint for it, too
            "ec2messages",
            "ecs-agent",
            "ecs-telemetry",
            "ecs",
            "ssm",
            "ssmmessages",
        ]

        # To see the full list of service endpoint names, see
        # https://docs.aws.amazon.com/general/latest/gr/aws-service-information.html
        for service in services:
            service_id = service.replace(".", "").replace("-", "").capitalize()
            endpoint = ec2.InterfaceVpcEndpoint(
                self,
                f"{service_id}Endpoint",
                vpc=self.vpc,
                service=ec2.InterfaceVpcEndpointService(f"com.amazonaws.{self.region}.{service}"),
                private_dns_enabled=True,
                security_groups=[self.security_group],
            )

            # Apply tags to interface VPC endpoint
            self.tagging_manager.apply_tags(endpoint, "VPC_ENDPOINT", {"EndpointType": f"{service_id}Interface"})
