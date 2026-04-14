"""Per-solver stacks of AWS resources."""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from common import CdkSolver, ResourceNamer, SolverEnvironment, SolverNodeType
from constructs import Construct

from .resource_tagging_manager import ResourceTaggingManager
from .ssm_config_manager import SsmConfigManager
from .vpc_stack import SolverVpcStack


class SolverStack(Stack):
    """
    Creates a stack with solver-specific AWS resources.

    This class references "global" AWS resources from other stacks.
    Use the `ResourceNamer` to ensure that these references use a
    consistent set of names.
    """

    ECS_CLUSTER_ID = "EcsCluster"
    LAUNCH_TEMPLATE_ID = "EcsLaunchTemplate"
    AUTO_SCALING_GROUP_ID = "AutoScalingGroup"
    AUTO_SCALING_GROUP_CAP_PROV_ID = "AsgCapacityProvider"
    ECR_ID = "EcrRepoImported"
    S3_BUCKET_ID = "SolverResultsBucketImported"
    LOG_GROUP_ID = "SolverLogGroupImported"

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc_stack: SolverVpcStack,
        rn: ResourceNamer,
        solver: CdkSolver,
        **kwargs,
    ):
        kwargs["description"] = f"Resources for solver {solver.name}"
        super().__init__(scope, construct_id, **kwargs)
        rn.set_stack(self)
        rn.set_solver(solver.name)

        # Alias the arguments to `self` so we don't need to pass them as args
        self.rn = rn
        self.solver = solver.name
        self.instance_type = solver.ec2_instance_type
        self.disk_size = solver.disk_size
        self.is_distributed = solver.is_distributed
        self.is_parallel = not self.is_distributed
        self.num_workers = solver.num_workers

        # Initialize resource tagging manager
        self.tagging_manager = ResourceTaggingManager(
            project=rn.project, solver=solver.name, environment="production"  # Could be made configurable
        )

        # Get references to "global" resources, declared in `app.py`
        # <referenced resources>
        self.bucket = s3.Bucket.from_bucket_name(
            self,
            SolverStack.S3_BUCKET_ID,
            bucket_name=self.rn.get_bucket_name(),
        )

        self.ecr_repo = ecr.Repository.from_repository_name(
            self,
            SolverStack.ECR_ID,
            repository_name=self.rn.get_ecr_repo_name(),
        )

        self.log_group = logs.LogGroup.from_log_group_name(
            self,
            SolverStack.LOG_GROUP_ID,
            log_group_name=self.rn.get_log_group_name(),
        )
        # </referenced resources>

        # ECS Cluster: manages solver compute (EC2 instances, containers)
        self.ecs_cluster = ecs.Cluster(
            self,
            SolverStack.ECS_CLUSTER_ID,
            cluster_name=rn.get_ecs_cluster_name(),
            container_insights_v2=ecs.ContainerInsights.ENABLED,
            vpc=vpc_stack.vpc,
        )

        # Apply tags to ECS cluster
        self.tagging_manager.apply_tags(self.ecs_cluster, "ECS_CLUSTER")

        # User data commands to run when EC2 instances gets launched in the ECS cluster
        user_data: ec2.UserData = ec2.UserData.for_linux(shebang="#!/bin/bash -xe")
        user_data.add_commands(f"echo ECS_CLUSTER={self.ecs_cluster.cluster_name} >> /etc/ecs/ecs.config")
        user_data.add_commands("yum install -y aws-cfn-bootstrap python-pip")
        user_data.add_commands("pip install awscli boto3")

        # Configure SSM agent to eliminate patching warnings
        SsmConfigManager.configure_user_data(user_data, disable_patching=True)

        user_data.add_commands(
            f"/opt/aws/bin/cfn-signal -e $? --stack {construct_id}"
            f" --resource ECSAutoScalingGroup --region {self.region}"
        )

        # IAM roles: give EC2 instances in the ECS cluster the permission
        #            to communicate with other AWS services
        self.instance_role = self.create_instance_role()
        self.ecs_role = self.create_ecs_role()
        self.task_role = self.create_task_role()
        self.execution_role = self.create_execution_role()

        # EC2 launch template: a recipe for initializing EC2 instances in the cluster
        ecs_instance_launch_config = ec2.LaunchTemplate(
            self,
            self.LAUNCH_TEMPLATE_ID,
            # Set the size of the EBS-backed storage device each EC2 instance will use
            block_devices=[
                ec2.BlockDevice(
                    # The name "xvd" is an acronym for "Xen Virtual block Device", see:
                    # https://askubuntu.com/questions/166083/what-is-the-dev-xvda1-device
                    # For Amazon's naming conventions for EBS storage blocks, see:
                    # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/device_naming.html
                    # tl;dr: the default name for the image's root storage is "/dev/xvda".
                    device_name="/dev/xvda",
                    mapping_enabled=True,
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=self.disk_size,  # The disk size, in GB
                        delete_on_termination=True,
                    ),
                )
            ],
            instance_type=ec2.InstanceType(str(self.instance_type)),
            machine_image=ecs.EcsOptimizedImage.amazon_linux2023(),
            security_group=vpc_stack.security_group,
            role=self.instance_role,
            user_data=user_data,
        )

        # Apply tags to launch template
        self.tagging_manager.apply_tags(ecs_instance_launch_config, "EC2_LAUNCH_TEMPLATE")

        # Auto scaling group (ASG): ensures we have enough underlying EC2 instances.
        # The ECS cluster runs ECS containers on "container EC2 instances,"
        # which are requested by the ASG (when its `desired_count > 0`).
        # If any EC2 instance crashes, then the ASG requests replacements.
        # Each EC2 instance launched by the ASG uses the `ecs_instance_launch_config`
        # that we defined above.
        # For information about auto-scaling groups, see:
        # https://docs.aws.amazon.com/autoscaling/ec2/userguide/auto-scaling-groups.html
        asg = autoscaling.AutoScalingGroup(
            self,
            self.AUTO_SCALING_GROUP_ID,
            auto_scaling_group_name=rn.get_asg_name(),
            launch_template=ecs_instance_launch_config,
            min_capacity=0,
            max_capacity=rn.ASG_MAX_CAPACITY,
            vpc=vpc_stack.vpc,
        )

        # Apply tags to auto scaling group
        self.tagging_manager.apply_tags(asg, "AUTO_SCALING_GROUP")

        # ASG capacity provider: specify the conditions that the ASG operates under.
        # We set certain values to enable manual adjustment of the # of EC2 instances.
        ascp = ecs.AsgCapacityProvider(
            self,
            self.AUTO_SCALING_GROUP_CAP_PROV_ID,
            auto_scaling_group=asg,
            # Auto-scaling is set to manual, managed by the user with `desired_count`
            enable_managed_scaling=False,
            # When the `desired_count` is decreased, EC2 instances are forcefully killed
            enable_managed_termination_protection=False,
        )

        # Apply tags to capacity provider
        self.tagging_manager.apply_tags(ascp, "ECS_CAPACITY_PROVIDER")

        self.ecs_cluster.add_asg_capacity_provider(ascp)

        # SQS: Each solver gets an input and output job queue
        self.input_queue = self.create_sqs_queue(self.rn.INPUT_QUEUE)
        self.output_queue = self.create_sqs_queue(self.rn.OUTPUT_QUEUE)

        # Create the DynamoDB tables used to pair leaders with worker nodes
        if self.is_distributed:
            self.set_up_ddb_tables()

        # Task Definitions
        self.leader_task_definition = self.create_task_definition(is_leader=True)
        if self.is_distributed:
            self.worker_task_definition = self.create_task_definition(is_leader=False)

        # ECS Services
        self.leader_service = ecs.Ec2Service(
            self,
            "SolverLeaderService",
            cluster=self.ecs_cluster,
            desired_count=0,
            min_healthy_percent=0,
            enable_execute_command=True,
            security_groups=[vpc_stack.security_group],
            task_definition=self.leader_task_definition,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
        )

        # Apply tags to leader service
        self.tagging_manager.apply_tags(self.leader_service, "ECS_SERVICE", {"ServiceType": "Leader"})

        if self.is_distributed:
            self.worker_service = ecs.Ec2Service(
                self,
                "SolverWorkerService",
                cluster=self.ecs_cluster,
                desired_count=0,
                min_healthy_percent=0,
                enable_execute_command=True,
                security_groups=[vpc_stack.security_group],
                task_definition=self.worker_task_definition,
                vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            )

            # Apply tags to worker service
            self.tagging_manager.apply_tags(self.worker_service, "ECS_SERVICE", {"ServiceType": "Worker"})

    def create_instance_role(self):
        role = iam.Role(
            self,
            "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2ContainerServiceforEC2Role"),
            ],
        )

        # Apply tags to instance role
        self.tagging_manager.apply_tags(role, "IAM_ROLE", {"RoleType": "InstanceRole"})

        # Add SSM permissions using the SSM configuration manager
        SsmConfigManager.add_ssm_permissions_to_role(role)

        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    # Rules which allow ECS to attach network interfaces to instances
                    # on your behalf in order for awsvpc networking mode to work right
                    "ec2:AttachNetworkInterface",
                    "ec2:CreateNetworkInterface",
                    "ec2:CreateNetworkInterfacePermission",
                    "ec2:DeleteNetworkInterface",
                    "ec2:DeleteNetworkInterfacePermission",
                    "ec2:Describe*",
                    "ec2:DetachNetworkInterface",
                    "elasticfilesystem:*",
                    "cloudwatch:*",
                    "ecs:*",
                    # Rules which allow ECS to update load balancers on your behalf
                    # with the information about how to send traffic to your containers
                    "elasticloadbalancing:DeregisterInstancesFromLoadBalancer",
                    "elasticloadbalancing:DeregisterTargets",
                    "elasticloadbalancing:Describe*",
                    "elasticloadbalancing:RegisterInstancesWithLoadBalancer",
                    "elasticloadbalancing:RegisterTargets",
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                ],
                resources=["*"],
            )
        )

        return role

    def create_ecs_role(self):
        role = iam.Role(self, "ECSRole", assumed_by=iam.ServicePrincipal("ecs.amazonaws.com"))

        # Apply tags to ECS role
        self.tagging_manager.apply_tags(role, "IAM_ROLE", {"RoleType": "ECSRole"})

        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:AttachNetworkInterface",
                    "ec2:CreateNetworkInterface",
                    "ec2:CreateNetworkInterfacePermission",
                    "ec2:DeleteNetworkInterface",
                    "ec2:DeleteNetworkInterfacePermission",
                    "ec2:Describe*",
                    "ec2:DetachNetworkInterface",
                    "elasticfilesystem:*",
                    "elasticloadbalancing:DeregisterInstancesFromLoadBalancer",
                    "elasticloadbalancing:DeregisterTargets",
                    "elasticloadbalancing:Describe*",
                    "elasticloadbalancing:RegisterInstancesWithLoadBalancer",
                    "elasticloadbalancing:RegisterTargets",
                ],
                resources=["*"],
            )
        )

        return role

    def create_task_role(self):
        role = iam.Role(
            self,
            "EcsTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"),
            ],
        )

        # Apply tags to task role
        self.tagging_manager.apply_tags(role, "IAM_ROLE", {"RoleType": "TaskRole"})

        # Add CloudWatch metrics policy
        role.add_to_policy(
            iam.PolicyStatement(effect=iam.Effect.ALLOW, actions=["cloudwatch:PutMetricData"], resources=["*"])
        )

        # Add SQS policy
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:GetQueueAttributes",
                    "sqs:SendMessage",
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:DeleteMessageBatch",
                    "sqs:GetQueueUrl",
                ],
                resources=["*"],
            )
        )

        # Add DynamoDB policy
        if self.is_distributed:
            role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "dynamodb:UpdateItem",
                        "dynamodb:DeleteItem",
                        "dynamodb:TransactWriteItems",
                        "dynamodb:GetItem",
                        "dynamodb:BatchGetItem",
                        "dynamodb:BatchWriteItem",
                        "dynamodb:Scan",
                    ],
                    resources=["*"],
                )
            )

        return role

    def create_execution_role(self):
        role = iam.Role(
            self,
            "ECSTaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # Apply tags to execution role
        self.tagging_manager.apply_tags(role, "IAM_ROLE", {"RoleType": "ExecutionRole"})

        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    # Allow the ECS Tasks to download images from ECR
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    # Allow the ECS tasks to upload logs to CloudWatch
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        return role

    def create_task_definition(self, is_leader: bool):
        task_def = ecs.TaskDefinition(
            self,
            self.rn.get_task_def_name(is_leader=is_leader),
            compatibility=ecs.Compatibility.EC2,
            execution_role=self.execution_role,
            network_mode=ecs.NetworkMode.AWS_VPC,
            task_role=self.task_role,
        )

        # Apply tags to task definition
        node_type = "Leader" if is_leader else "Worker"
        self.tagging_manager.apply_tags(task_def, "ECS_TASK_DEFINITION", {"NodeType": node_type})

        # Set the size of `/dev/shm` with a Linux parameter
        linux_params = ecs.LinuxParameters(
            self,
            self.rn.get_linux_params_name(is_leader),
            shared_memory_size=self.instance_type.shm_in_mib(),
        )

        node_type = SolverNodeType.from_bools(is_leader=is_leader, is_distributed=self.is_distributed)
        environment = SolverEnvironment.aws_env(self.rn, node_type, self.num_workers)

        stream_prefix = "ecs"
        if self.is_distributed:
            stream_prefix += "/leader" if is_leader else "/worker"

        # Reference the image from ECR
        container_name = self.rn.get_container_name()
        container = task_def.add_container(
            container_name,
            image=ecs.ContainerImage.from_ecr_repository(self.ecr_repo, self.rn.get_ecr_image_tag()),
            environment=environment.to_cdk_dict(),
            enable_restart_policy=True,  # Restart the container on crash without starting a new ECS task
            essential=True,  # All other containers in the task are stopped when this one does
            linux_parameters=linux_params,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix=stream_prefix,
                log_group=self.log_group,
            ),
            memory_reservation_mib=self.instance_type.soft_mem_limit_in_mib(),
            user=self.rn.LINUX_USER,  # Don't run as `root`
        )

        # Expose port 22 for TCP (to align with `EXPOSE 22` in the Dockerfile)
        container.add_port_mappings(
            ecs.PortMapping(
                container_port=22,
                host_port=22,
                protocol=ecs.Protocol.TCP,
            )
        )

        return task_def

    def create_sqs_queue(self, base_queue_name: str) -> sqs.Queue:
        queue_name = self.rn.get_sqs_queue_name(base_queue_name)
        queue = sqs.Queue(
            self,
            base_queue_name,
            queue_name=queue_name,
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            receive_message_wait_time=Duration.seconds(20),
            removal_policy=RemovalPolicy.DESTROY,
            retention_period=Duration.days(7),
            visibility_timeout=Duration.seconds(5),
        )

        # Apply tags to SQS queue
        self.tagging_manager.apply_tags(queue, "SQS_QUEUE", {"QueueType": base_queue_name})

        return queue

    def set_up_ddb_tables(self):
        def create_table(base_name: str):
            table_name = self.rn.get_dynamo_table_name(base_name)
            table = dynamodb.Table(
                self,
                base_name,
                table_name=table_name,
                billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
                partition_key=dynamodb.Attribute(
                    name=self.rn.PARTITION_KEY,
                    type=dynamodb.AttributeType.STRING,
                ),
                removal_policy=RemovalPolicy.DESTROY,
            )

            # Apply tags to DynamoDB table
            self.tagging_manager.apply_tags(table, "DYNAMODB_TABLE", {"TableType": base_name})

            return table

        self.ip_table = create_table(self.rn.IP_TABLE)
        self.timestamp_table = create_table(self.rn.TIMESTAMP_TABLE)
