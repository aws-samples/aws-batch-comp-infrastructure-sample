"""Tests for the extracted command handlers in runner.commands."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from runner.commands.base import CommandContext, CommandHandler
from runner.commands.docker import BuildCommand, PushCommand
from runner.commands.deploy import DeployCommand, BootstrapCommand
from runner.commands.destroy import DestroyCommand
from runner.commands.ecs import EcsServiceManager, StartCommand, StandbyCommand, StopCommand, RefreshCommand
from runner.commands.jobs import SubmitCommand, ProcessCommand, PurgeCommand
from runner.commands.ls import LsCommand
from runner.commands.cdk import CdkHelper, exec_cdk_command
from runner.runner_cli import LsSubcommand, ProvisionSubcommand, TeardownSubcommand


@pytest.fixture
def mock_project():
    """Create a mock ProjectConfig."""
    project = MagicMock()
    project.project = "test-project"
    project.region = "us-west-2"
    project.profile = "default"
    project.solver_type = "SAT"
    project.has_image_to_push = True
    return project


@pytest.fixture
def mock_sdc(mock_project):
    """Create a mock SolverDockerClient."""
    sdc = MagicMock()
    sdc.project = mock_project
    sdc.get_solvers.return_value = ["solver1", "solver2"]
    sdc.get_aws_solvers.return_value = ["solver1", "solver2"]
    return sdc


@pytest.fixture
def mock_rn():
    """Create a mock ResourceNamer."""
    rn = MagicMock()
    rn.FIELD_SEP = "--"
    rn.INPUT_QUEUE = "input"
    rn.get_ecr_repo_name.return_value = "test-repo"
    rn.get_ecr_repo_url.return_value = "123456789.dkr.ecr.us-west-2.amazonaws.com/test-repo"
    rn.get_ecr_image_tag.return_value = "test-project--solver1"
    rn.get_sqs_queue_prefix.return_value = "test-project"
    rn.get_sqs_input_queue_name.return_value = "test-project--solver1--input"
    rn.get_sqs_output_queue_name.return_value = "test-project--solver1--output"
    rn.get_task_def_name.return_value = "test-project--solver1--leader"
    rn.get_container_name.return_value = "solver1-container"
    rn.get_ecs_cluster_name.return_value = "test-project--solver1--cluster"
    rn.get_ecs_cluster_postfix.return_value = "--cluster"
    rn.get_solver_stack_name.return_value = "test-project--solver1--stack"
    rn.get_asg_name.return_value = "test-project--solver1--asg"
    return rn


@pytest.fixture
def mock_session():
    """Create a mock boto3 session."""
    session = MagicMock()
    return session


@pytest.fixture
def ctx(mock_project, mock_sdc, mock_rn, mock_session):
    """Create a CommandContext with mocks."""
    ctx = CommandContext(
        project=mock_project,
        sdc=mock_sdc,
        cdk_path=Path("/tmp/cdk"),
        boto3_session=mock_session,
        account="123456789012",
        rn=mock_rn,
    )
    return ctx


class TestCommandContext:
    """Tests for CommandContext class."""

    def test_solvers_property(self, ctx):
        """Test that solvers property returns sdc.get_solvers()."""
        assert ctx.solvers == ["solver1", "solver2"]

    def test_aws_solvers_property(self, ctx):
        """Test that aws_solvers property returns sdc.get_aws_solvers()."""
        assert ctx.aws_solvers == ["solver1", "solver2"]

    def test_get_client_creates_and_caches(self, ctx, mock_session):
        """Test that get_client creates clients lazily and caches them."""
        mock_ecs = MagicMock()
        mock_session.client.return_value = mock_ecs

        client1 = ctx.get_client('ecs')
        client2 = ctx.get_client('ecs')

        assert client1 is client2
        mock_session.client.assert_called_once_with('ecs')

    def test_get_client_without_session_raises(self, mock_project, mock_sdc):
        """Test that get_client raises when session is None."""
        ctx = CommandContext(
            project=mock_project,
            sdc=mock_sdc,
            cdk_path=Path("/tmp/cdk"),
        )
        with pytest.raises(RuntimeError, match="AWS session not initialized"):
            ctx.get_client('ecs')

    def test_set_client_injects_mock(self, ctx):
        """Test that set_client allows injecting mock clients."""
        mock_client = MagicMock()
        ctx.set_client('ecs', mock_client)
        assert ctx.get_client('ecs') is mock_client


class TestBuildCommand:
    """Tests for BuildCommand."""

    def test_execute_calls_build_images(self, ctx):
        """Test that execute calls sdc.build_images()."""
        cmd = BuildCommand(ctx)
        result = cmd.execute()

        assert result == 0
        ctx.sdc.build_images.assert_called_once()


class TestPushCommand:
    """Tests for PushCommand."""

    def test_execute_returns_early_when_nothing_to_push(self, ctx):
        """Test that execute returns 0 when has_image_to_push is False."""
        ctx.project.has_image_to_push = False

        cmd = PushCommand(ctx)
        result = cmd.execute()

        assert result == 0

    def test_execute_calls_ecr_and_push(self, ctx):
        """Test that execute authenticates and pushes images."""
        mock_ecr = MagicMock()
        mock_ecr.get_authorization_token.return_value = {
            'authorizationData': [{
                'proxyEndpoint': 'https://123456789.dkr.ecr.us-west-2.amazonaws.com',
                'authorizationToken': 'QVdTOnBhc3N3b3Jk'  # base64 'AWS:password'
            }]
        }
        ctx.set_client('ecr', mock_ecr)
        ctx.sdc.tag_and_push_images.return_value = True

        cmd = PushCommand(ctx)
        result = cmd.execute()

        assert result == 0
        ctx.sdc.log_in_to_aws.assert_called_once()
        ctx.sdc.tag_and_push_images.assert_called_once()

    def test_execute_returns_error_on_push_failure(self, ctx):
        """Test that execute returns 1 when push fails."""
        mock_ecr = MagicMock()
        mock_ecr.get_authorization_token.return_value = {
            'authorizationData': [{
                'proxyEndpoint': 'https://123456789.dkr.ecr.us-west-2.amazonaws.com',
                'authorizationToken': 'QVdTOnBhc3N3b3Jk'
            }]
        }
        ctx.set_client('ecr', mock_ecr)
        ctx.sdc.tag_and_push_images.return_value = False

        cmd = PushCommand(ctx)
        result = cmd.execute()

        assert result == 1

    def test_execute_handles_ecr_auth_failure(self, ctx):
        """Test that execute handles ECR authentication failure."""
        mock_ecr = MagicMock()
        mock_ecr.get_authorization_token.side_effect = Exception("Auth failed")
        ctx.set_client('ecr', mock_ecr)

        cmd = PushCommand(ctx)
        with pytest.raises(Exception, match="Auth failed"):
            cmd.execute()


class TestDeployCommand:
    """Tests for DeployCommand."""

    @patch('runner.commands.deploy.CdkHelper')
    def test_execute_deploys_all_by_default(self, MockCdkHelper, ctx):
        """Test that execute deploys all stacks by default."""
        mock_cdk = MagicMock()
        mock_cdk.deploy_all.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = DeployCommand(ctx)
        result = cmd.execute(opt=ProvisionSubcommand.ALL)

        assert result == 0
        mock_cdk.deploy_all.assert_called_once()

    @patch('runner.commands.deploy.CdkHelper')
    def test_execute_deploys_solvers(self, MockCdkHelper, ctx):
        """Test that execute deploys solver stacks."""
        mock_cdk = MagicMock()
        mock_cdk.deploy_solvers.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = DeployCommand(ctx)
        result = cmd.execute(opt=ProvisionSubcommand.SOLVERS)

        assert result == 0
        mock_cdk.deploy_solvers.assert_called_once_with(["solver1", "solver2"])

    @patch('runner.commands.deploy.CdkHelper')
    def test_execute_deploys_vpc(self, MockCdkHelper, ctx):
        """Test that execute deploys VPC stack."""
        mock_cdk = MagicMock()
        mock_cdk.deploy_vpc.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = DeployCommand(ctx)
        result = cmd.execute(opt=ProvisionSubcommand.VPC)

        assert result == 0
        mock_cdk.deploy_vpc.assert_called_once()

    @patch('runner.commands.deploy.CdkHelper')
    def test_execute_deploys_ecr(self, MockCdkHelper, ctx):
        """Test that execute deploys ECR repository stack."""
        mock_cdk = MagicMock()
        mock_cdk.deploy_ecr_repo.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = DeployCommand(ctx)
        result = cmd.execute(opt=ProvisionSubcommand.ECR)

        assert result == 0
        mock_cdk.deploy_ecr_repo.assert_called_once()

    @patch('runner.commands.deploy.CdkHelper')
    def test_execute_deploys_s3(self, MockCdkHelper, ctx):
        """Test that execute deploys S3 bucket stack."""
        mock_cdk = MagicMock()
        mock_cdk.deploy_s3.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = DeployCommand(ctx)
        result = cmd.execute(opt=ProvisionSubcommand.S3)

        assert result == 0
        mock_cdk.deploy_s3.assert_called_once()

    @patch('runner.commands.deploy.CdkHelper')
    def test_execute_deploys_logs(self, MockCdkHelper, ctx):
        """Test that execute deploys log group stacks."""
        mock_cdk = MagicMock()
        mock_cdk.deploy_logs.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = DeployCommand(ctx)
        result = cmd.execute(opt=ProvisionSubcommand.LOGS)

        assert result == 0
        mock_cdk.deploy_logs.assert_called_once_with(["solver1", "solver2"])

    @patch('runner.commands.deploy.CdkHelper')
    def test_execute_handles_unknown_option(self, MockCdkHelper, ctx):
        """Test that execute returns error for unknown deploy option."""
        mock_cdk = MagicMock()
        MockCdkHelper.return_value = mock_cdk

        cmd = DeployCommand(ctx)
        # Create a mock enum value that isn't handled
        mock_opt = MagicMock()
        mock_opt.name = "UNKNOWN"
        result = cmd.execute(opt=mock_opt)

        assert result == 1


class TestBootstrapCommand:
    """Tests for BootstrapCommand."""

    @patch('runner.commands.deploy.CdkHelper')
    def test_execute_calls_cdk_bootstrap(self, MockCdkHelper, ctx):
        """Test that execute calls CDK bootstrap."""
        mock_cdk = MagicMock()
        mock_cdk.bootstrap.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = BootstrapCommand(ctx)
        result = cmd.execute()

        assert result == 0
        mock_cdk.bootstrap.assert_called_once()


class TestDestroyCommand:
    """Tests for DestroyCommand."""

    @patch('runner.commands.destroy.TeardownManager')
    @patch('runner.commands.destroy.CdkHelper')
    def test_execute_destroys_all_with_verification(self, MockCdkHelper, MockTeardown, ctx):
        """Test that destroy all includes verification."""
        mock_cdk = MagicMock()
        mock_cdk.destroy_all.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        mock_teardown = MagicMock()
        mock_teardown.preview_teardown.return_value = []
        mock_teardown.verify_cleanup.return_value = MagicMock(orphaned_resources=[])
        MockTeardown.return_value = mock_teardown

        cmd = DestroyCommand(ctx)
        result = cmd.execute(opt=TeardownSubcommand.ALL)

        assert result == 0
        mock_cdk.destroy_all.assert_called_once()
        mock_teardown.verify_cleanup.assert_called_once()

    @patch('runner.commands.destroy.TeardownManager')
    @patch('runner.commands.destroy.CdkHelper')
    def test_execute_destroys_all_with_orphaned_resources(self, MockCdkHelper, MockTeardown, ctx):
        """Test that destroy all cleans up orphaned resources."""
        mock_cdk = MagicMock()
        mock_cdk.destroy_all.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        mock_teardown = MagicMock()
        mock_teardown.preview_teardown.return_value = ['resource1', 'resource2']
        mock_teardown.verify_cleanup.return_value = MagicMock(
            orphaned_resources=['orphan1', 'orphan2']
        )
        mock_teardown.force_cleanup_orphaned.return_value = ['orphan1', 'orphan2']
        MockTeardown.return_value = mock_teardown

        cmd = DestroyCommand(ctx)
        result = cmd.execute(opt=TeardownSubcommand.ALL)

        assert result == 0
        mock_teardown.force_cleanup_orphaned.assert_called_once()

    @patch('runner.commands.destroy.TeardownManager')
    @patch('runner.commands.destroy.CdkHelper')
    def test_execute_destroys_solvers_with_verification(self, MockCdkHelper, MockTeardown, ctx):
        """Test that destroy solvers includes per-solver verification."""
        mock_cdk = MagicMock()
        mock_cdk.destroy_solvers.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        mock_teardown = MagicMock()
        mock_teardown.preview_teardown.return_value = []
        MockTeardown.return_value = mock_teardown

        cmd = DestroyCommand(ctx)
        result = cmd.execute(opt=TeardownSubcommand.SOLVERS)

        assert result == 0
        mock_cdk.destroy_solvers.assert_called_once_with(["solver1", "solver2"])
        # Should check each solver's remaining resources
        assert mock_teardown.preview_teardown.call_count == 2

    @patch('runner.commands.destroy.CdkHelper')
    def test_execute_destroys_vpc(self, MockCdkHelper, ctx):
        """Test that execute destroys VPC stack."""
        mock_cdk = MagicMock()
        mock_cdk.destroy_vpc.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = DestroyCommand(ctx)
        result = cmd.execute(opt=TeardownSubcommand.VPC)

        assert result == 0
        mock_cdk.destroy_vpc.assert_called_once()

    @patch('runner.commands.destroy.CdkHelper')
    def test_execute_destroys_ecr(self, MockCdkHelper, ctx):
        """Test that execute destroys ECR repository."""
        mock_cdk = MagicMock()
        mock_cdk.destroy_ecr_repo.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = DestroyCommand(ctx)
        result = cmd.execute(opt=TeardownSubcommand.ECR)

        assert result == 0
        mock_cdk.destroy_ecr_repo.assert_called_once()

    @patch('runner.commands.destroy.CdkHelper')
    def test_execute_destroys_s3(self, MockCdkHelper, ctx):
        """Test that execute destroys S3 bucket."""
        mock_cdk = MagicMock()
        mock_cdk.destroy_s3.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = DestroyCommand(ctx)
        result = cmd.execute(opt=TeardownSubcommand.S3)

        assert result == 0
        mock_cdk.destroy_s3.assert_called_once()

    @patch('runner.commands.destroy.CdkHelper')
    def test_execute_destroys_logs(self, MockCdkHelper, ctx):
        """Test that execute destroys log groups."""
        mock_cdk = MagicMock()
        mock_cdk.destroy_logs.return_value = 0
        MockCdkHelper.return_value = mock_cdk

        cmd = DestroyCommand(ctx)
        result = cmd.execute(opt=TeardownSubcommand.LOGS)

        assert result == 0
        mock_cdk.destroy_logs.assert_called_once_with(["solver1", "solver2"])


class TestEcsServiceManager:
    """Tests for EcsServiceManager."""

    def test_validate_ecr_images_returns_true_when_all_exist(self, ctx):
        """Test that validate_ecr_images returns True when images exist."""
        mock_ecr = MagicMock()
        mock_ecr.describe_images.return_value = {
            'imageDetails': [
                {'imageTags': ['test-project--solver1'], 'imageDigest': 'sha256:abc123'},
                {'imageTags': ['test-project--solver2'], 'imageDigest': 'sha256:def456'},
            ]
        }
        ctx.set_client('ecr', mock_ecr)
        ctx.rn.get_ecr_image_tag.side_effect = lambda s: f"test-project--{s}"

        manager = EcsServiceManager(ctx)
        result = manager.validate_ecr_images(["solver1", "solver2"])

        assert result is True

    def test_validate_ecr_images_returns_false_when_missing(self, ctx):
        """Test that validate_ecr_images returns False when image missing."""
        mock_ecr = MagicMock()
        mock_ecr.describe_images.return_value = {
            'imageDetails': [
                {'imageTags': ['test-project--solver1'], 'imageDigest': 'sha256:abc123'},
            ]
        }
        ctx.set_client('ecr', mock_ecr)
        ctx.rn.get_ecr_image_tag.side_effect = lambda s: f"test-project--{s}"

        manager = EcsServiceManager(ctx)
        result = manager.validate_ecr_images(["solver1", "solver2"])

        assert result is False

    def test_find_task_arn_returns_matching_arn(self, ctx):
        """Test that find_task_arn returns the matching ARN."""
        mock_ecs = MagicMock()
        # CloudFormation strips all hyphens from construct IDs
        mock_ecs.list_task_definitions.return_value = {
            'taskDefinitionArns': [
                'arn:aws:ecs:us-west-2:123:task-definition/testprojectsolver1leaderTaskDef:1',
                'arn:aws:ecs:us-west-2:123:task-definition/testprojectsolver2leaderTaskDef:1',
            ]
        }
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_task_def_name.return_value = "test-project--solver1--leader"

        manager = EcsServiceManager(ctx)
        arn = manager.find_task_arn("solver1", is_leader=True)

        assert arn == 'arn:aws:ecs:us-west-2:123:task-definition/testprojectsolver1leaderTaskDef:1'

    def test_find_task_arn_returns_none_when_not_found(self, ctx):
        """Test that find_task_arn returns None when ARN not found."""
        mock_ecs = MagicMock()
        mock_ecs.list_task_definitions.return_value = {
            'taskDefinitionArns': [
                'arn:aws:ecs:us-west-2:123:task-definition/other-task:1',
            ]
        }
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_task_def_name.return_value = "test-project--solver1--leader"

        manager = EcsServiceManager(ctx)
        arn = manager.find_task_arn("solver1", is_leader=True)

        assert arn is None

    def test_find_task_arn_for_worker(self, ctx):
        """Test that find_task_arn finds worker task ARNs correctly."""
        mock_ecs = MagicMock()
        # CloudFormation strips all hyphens from construct IDs
        mock_ecs.list_task_definitions.return_value = {
            'taskDefinitionArns': [
                'arn:aws:ecs:us-west-2:123:task-definition/testprojectsolver1workerTaskDef:1',
            ]
        }
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_task_def_name.return_value = "test-project--solver1--worker"

        manager = EcsServiceManager(ctx)
        arn = manager.find_task_arn("solver1", is_leader=False)

        assert arn == 'arn:aws:ecs:us-west-2:123:task-definition/testprojectsolver1workerTaskDef:1'

    def test_get_task_arns_caches_result(self, ctx):
        """Test that get_task_arns caches the result after first call."""
        mock_ecs = MagicMock()
        mock_ecs.list_task_definitions.return_value = {
            'taskDefinitionArns': ['arn1', 'arn2']
        }
        ctx.set_client('ecs', mock_ecs)

        manager = EcsServiceManager(ctx)
        result1 = manager.get_task_arns()
        result2 = manager.get_task_arns()

        assert result1 == result2
        mock_ecs.list_task_definitions.assert_called_once()

    def test_validate_env_vars_missing_env_vars(self, ctx):
        """Test that validate_env_vars returns False when env vars are missing."""
        mock_ecs = MagicMock()
        mock_ecs.list_task_definitions.return_value = {
            'taskDefinitionArns': ['arn:aws:ecs:us-west-2:123:task-definition/testprojectsolver1leaderTaskDef:1']
        }
        mock_ecs.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{
                    'name': 'solver1-container',
                    'environment': []  # Missing required env vars
                }]
            }
        }
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_task_def_name.return_value = "test-project--solver1--leader"

        mock_sc = MagicMock()
        mock_sc.name = "solver1"

        manager = EcsServiceManager(ctx)
        result = manager.validate_env_vars(mock_sc, is_leader=True)

        assert result is False

    def test_validate_env_vars_num_workers_mismatch(self, ctx):
        """Test that validate_env_vars returns False when NUM_WORKERS doesn't match."""
        from common.solver_env import SolverEnvironment

        mock_ecs = MagicMock()
        mock_ecs.list_task_definitions.return_value = {
            'taskDefinitionArns': ['arn:aws:ecs:us-west-2:123:task-definition/testprojectsolver1leaderTaskDef:1']
        }
        mock_ecs.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{
                    'name': 'solver1-container',
                    'environment': [
                        {'name': SolverEnvironment.NUM_WORKERS_KEY, 'value': '4'},
                        {'name': SolverEnvironment.NODE_TYPE_KEY, 'value': 'parallel'}
                    ]
                }]
            }
        }
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_task_def_name.return_value = "test-project--solver1--leader"

        mock_sc = MagicMock()
        mock_sc.name = "solver1"
        mock_sc.cdk_solver.num_workers = 2  # Different from AWS value of 4
        mock_sc.is_distributed = False

        manager = EcsServiceManager(ctx)
        result = manager.validate_env_vars(mock_sc, is_leader=True)

        assert result is False

    def test_validate_env_vars_node_type_mismatch(self, ctx):
        """Test that validate_env_vars returns False when NODE_TYPE doesn't match."""
        from common.solver_env import SolverEnvironment

        mock_ecs = MagicMock()
        mock_ecs.list_task_definitions.return_value = {
            'taskDefinitionArns': ['arn:aws:ecs:us-west-2:123:task-definition/testprojectsolver1leaderTaskDef:1']
        }
        mock_ecs.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{
                    'name': 'solver1-container',
                    'environment': [
                        {'name': SolverEnvironment.NUM_WORKERS_KEY, 'value': '1'},
                        {'name': SolverEnvironment.NODE_TYPE_KEY, 'value': 'parallel'}
                    ]
                }]
            }
        }
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_task_def_name.return_value = "test-project--solver1--leader"

        mock_sc = MagicMock()
        mock_sc.name = "solver1"
        mock_sc.cdk_solver.num_workers = 1
        mock_sc.is_distributed = True  # Config says distributed but AWS says parallel

        manager = EcsServiceManager(ctx)
        result = manager.validate_env_vars(mock_sc, is_leader=True)

        assert result is False

    def test_validate_env_vars_multiple_containers(self, ctx):
        """Test that validate_env_vars returns False when task has multiple containers."""
        mock_ecs = MagicMock()
        mock_ecs.list_task_definitions.return_value = {
            'taskDefinitionArns': ['arn:aws:ecs:us-west-2:123:task-definition/testprojectsolver1leaderTaskDef:1']
        }
        mock_ecs.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [
                    {'name': 'container1', 'environment': []},
                    {'name': 'container2', 'environment': []}
                ]
            }
        }
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_task_def_name.return_value = "test-project--solver1--leader"

        mock_sc = MagicMock()
        mock_sc.name = "solver1"

        manager = EcsServiceManager(ctx)
        result = manager.validate_env_vars(mock_sc, is_leader=True)

        assert result is False

    def test_validate_env_vars_container_name_mismatch(self, ctx):
        """Test that validate_env_vars returns False when container name doesn't match."""
        from common.solver_env import SolverEnvironment

        mock_ecs = MagicMock()
        mock_ecs.list_task_definitions.return_value = {
            'taskDefinitionArns': ['arn:aws:ecs:us-west-2:123:task-definition/testprojectsolver1leaderTaskDef:1']
        }
        mock_ecs.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{
                    'name': 'wrong-container-name',
                    'environment': [
                        {'name': SolverEnvironment.NUM_WORKERS_KEY, 'value': '1'},
                        {'name': SolverEnvironment.NODE_TYPE_KEY, 'value': 'parallel'}
                    ]
                }]
            }
        }
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_task_def_name.return_value = "test-project--solver1--leader"
        ctx.rn.get_container_name.return_value = "solver1-container"

        mock_sc = MagicMock()
        mock_sc.name = "solver1"

        manager = EcsServiceManager(ctx)
        result = manager.validate_env_vars(mock_sc, is_leader=True)

        assert result is False

    def test_adjust_service_success(self, ctx):
        """Test that adjust_service updates the service successfully."""
        mock_ecs = MagicMock()
        ctx.set_client('ecs', mock_ecs)

        manager = EcsServiceManager(ctx)
        service_arns = [
            'arn:aws:ecs:us-west-2:123:service/cluster/test-projectsolver1SolverLeaderService',
            'arn:aws:ecs:us-west-2:123:service/cluster/test-projectsolver1SolverWorkerService'
        ]

        result = manager.adjust_service(
            'test-cluster',
            service_arns,
            'SolverLeaderService',
            2,
            'solver1'
        )

        assert result is True
        mock_ecs.update_service.assert_called_once_with(
            cluster='test-cluster',
            service='arn:aws:ecs:us-west-2:123:service/cluster/test-projectsolver1SolverLeaderService',
            desiredCount=2
        )

    def test_adjust_service_not_found(self, ctx):
        """Test that adjust_service returns False when service not found."""
        mock_ecs = MagicMock()
        ctx.set_client('ecs', mock_ecs)

        manager = EcsServiceManager(ctx)
        service_arns = ['arn:aws:ecs:us-west-2:123:service/cluster/other-service']

        result = manager.adjust_service(
            'test-cluster',
            service_arns,
            'SolverLeaderService',
            2,
            'solver1'
        )

        assert result is False
        mock_ecs.update_service.assert_not_called()

    def test_scale_solver_distributed(self, ctx):
        """Test that scale_solver handles distributed solver with workers."""
        mock_ecs = MagicMock()
        # Service names must contain the pattern f"{solver_stack_name}-SolverLeaderService"
        mock_ecs.list_services.return_value = {
            'serviceArns': [
                'arn:aws:ecs:us-west-2:123:service/cluster/test-project--solver1--stack-SolverLeaderService',
                'arn:aws:ecs:us-west-2:123:service/cluster/test-project--solver1--stack-SolverWorkerService'
            ]
        }
        ctx.set_client('ecs', mock_ecs)

        mock_asg = MagicMock()
        ctx.set_client('autoscaling', mock_asg)

        # Setup solver config
        mock_sc = MagicMock()
        mock_sc.cdk_solver.num_workers = 3
        mock_sc.is_distributed = True
        ctx.project.get_solver.return_value = mock_sc

        ctx.rn.get_solver_stack_name.return_value = "test-project--solver1--stack"
        ctx.rn.get_asg_name.return_value = "test-project--solver1--asg"
        ctx.rn.get_ecs_cluster_name.return_value = "test-cluster"

        manager = EcsServiceManager(ctx)
        result = manager.scale_solver('solver1', num_leaders=2, num_copies=2)

        assert result is True
        # Should scale ASG to 2 * (1 leader + 3 workers) = 8 instances
        mock_asg.update_auto_scaling_group.assert_called_once_with(
            AutoScalingGroupName='test-project--solver1--asg',
            DesiredCapacity=8
        )
        # Should update leader service to 2 and worker service to 6
        assert mock_ecs.update_service.call_count == 2


class TestStartCommand:
    """Tests for StartCommand."""

    @patch.object(EcsServiceManager, 'validate_ecr_images')
    @patch.object(EcsServiceManager, 'validate_env_vars')
    @patch.object(EcsServiceManager, 'scale_solver')
    def test_execute_validates_and_scales(self, mock_scale, mock_validate_env, mock_validate_ecr, ctx):
        """Test that execute validates images then scales solvers."""
        mock_validate_ecr.return_value = True
        mock_validate_env.return_value = True
        mock_scale.return_value = True

        # Mock get_solver to return a solver config
        mock_solver_config = MagicMock()
        mock_solver_config.is_distributed = False
        ctx.project.get_solver.return_value = mock_solver_config

        cmd = StartCommand(ctx)
        result = cmd.execute(num_copies=2)

        assert result == 0
        mock_validate_ecr.assert_called_once()
        assert mock_scale.call_count == 2  # Once per solver

    @patch.object(EcsServiceManager, 'validate_ecr_images')
    def test_execute_returns_error_on_ecr_validation_failure(self, mock_validate_ecr, ctx):
        """Test that execute returns 1 when ECR validation fails."""
        mock_validate_ecr.return_value = False

        cmd = StartCommand(ctx)
        result = cmd.execute(num_copies=1)

        assert result == 1

    @patch.object(EcsServiceManager, 'validate_ecr_images')
    @patch.object(EcsServiceManager, 'validate_env_vars')
    def test_execute_returns_error_on_env_validation_failure(self, mock_validate_env, mock_validate_ecr, ctx):
        """Test that execute returns 1 when environment validation fails."""
        mock_validate_ecr.return_value = True
        mock_validate_env.return_value = False

        mock_solver_config = MagicMock()
        mock_solver_config.is_distributed = False
        ctx.project.get_solver.return_value = mock_solver_config

        cmd = StartCommand(ctx)
        result = cmd.execute(num_copies=1)

        assert result == 1

    @patch.object(EcsServiceManager, 'validate_ecr_images')
    @patch.object(EcsServiceManager, 'validate_env_vars')
    @patch.object(EcsServiceManager, 'scale_solver')
    def test_execute_returns_error_on_scale_failure(self, mock_scale, mock_validate_env, mock_validate_ecr, ctx):
        """Test that execute returns 1 when scaling fails."""
        mock_validate_ecr.return_value = True
        mock_validate_env.return_value = True
        mock_scale.return_value = False

        mock_solver_config = MagicMock()
        mock_solver_config.is_distributed = False
        ctx.project.get_solver.return_value = mock_solver_config

        cmd = StartCommand(ctx)
        result = cmd.execute(num_copies=1)

        assert result == 1

    @patch.object(EcsServiceManager, 'validate_ecr_images')
    @patch.object(EcsServiceManager, 'validate_env_vars')
    def test_execute_validates_distributed_worker(self, mock_validate_env, mock_validate_ecr, ctx):
        """Test that execute validates both leader and worker for distributed solver."""
        mock_validate_ecr.return_value = True
        mock_validate_env.side_effect = [True, False]  # Leader passes, worker fails

        mock_solver_config = MagicMock()
        mock_solver_config.is_distributed = True
        ctx.project.get_solver.return_value = mock_solver_config

        cmd = StartCommand(ctx)
        result = cmd.execute(num_copies=1)

        assert result == 1
        # Should be called twice - once for leader, once for worker
        assert mock_validate_env.call_count == 2


class TestStandbyCommand:
    """Tests for StandbyCommand."""

    @patch('runner.commands.ecs.prompt_purge_queues')
    @patch.object(EcsServiceManager, 'validate_ecr_images')
    @patch.object(EcsServiceManager, 'validate_env_vars')
    @patch.object(EcsServiceManager, 'scale_solver')
    def test_execute_keeps_instances_stops_tasks(self, mock_scale, mock_validate_env, mock_validate_ecr, mock_purge, ctx):
        """Test that standby keeps EC2 instances but stops tasks."""
        mock_validate_ecr.return_value = True
        mock_validate_env.return_value = True
        mock_scale.return_value = True

        mock_solver_config = MagicMock()
        mock_solver_config.is_distributed = False
        ctx.project.get_solver.return_value = mock_solver_config

        cmd = StandbyCommand(ctx)
        result = cmd.execute(num_copies=3)

        assert result == 0
        mock_purge.assert_called_once()
        # Verify scale_solver was called with 0 leaders but 3 copies
        for call in mock_scale.call_args_list:
            args, kwargs = call
            assert args[1] == 0  # num_leaders (stops tasks)
            assert args[2] == 3  # num_copies (keeps instances)


class TestStopCommand:
    """Tests for StopCommand."""

    @patch.object(EcsServiceManager, 'validate_ecr_images')
    @patch.object(EcsServiceManager, 'validate_env_vars')
    @patch.object(EcsServiceManager, 'scale_solver')
    def test_execute_scales_to_zero(self, mock_scale, mock_validate_env, mock_validate_ecr, ctx):
        """Test that stop scales to zero."""
        mock_validate_ecr.return_value = True
        mock_validate_env.return_value = True
        mock_scale.return_value = True

        mock_solver_config = MagicMock()
        mock_solver_config.is_distributed = False
        ctx.project.get_solver.return_value = mock_solver_config

        cmd = StopCommand(ctx)
        result = cmd.execute()

        assert result == 0
        # Verify scale_solver was called with 0 leaders and 0 copies
        for call in mock_scale.call_args_list:
            args, kwargs = call
            assert args[1] == 0  # num_leaders
            assert args[2] == 0  # num_copies


class TestLsCommand:
    """Tests for LsCommand."""

    def test_ls_solvers(self, ctx):
        """Test that ls solvers returns solver list."""
        cmd = LsCommand(ctx)
        result = cmd.execute(opt=LsSubcommand.SOLVERS)

        assert result == 0

    def test_ls_unknown_option_returns_error(self, ctx):
        """Test that unknown ls option returns error."""
        cmd = LsCommand(ctx)
        # Create a mock enum value that isn't handled
        mock_opt = MagicMock()
        mock_opt.print_header_message = MagicMock()
        result = cmd.execute(opt=mock_opt)

        assert result == 1

    def test_ls_sqs_with_orphaned_queues(self, ctx):
        """Test that ls sqs handles orphaned queues not in config."""
        mock_sqs = MagicMock()
        mock_sqs.list_queues.return_value = {
            'QueueUrls': [
                f'https://sqs.us-west-2.amazonaws.com/123456789012/test-project--solver1--input',
                f'https://sqs.us-west-2.amazonaws.com/123456789012/test-project--solver1--output',
                f'https://sqs.us-west-2.amazonaws.com/123456789012/test-project--solver2--input',
                f'https://sqs.us-west-2.amazonaws.com/123456789012/test-project--solver2--output',
                f'https://sqs.us-west-2.amazonaws.com/123456789012/test-project--orphan--input',
                f'https://sqs.us-west-2.amazonaws.com/123456789012/test-project--orphan--output',
            ]
        }
        ctx.set_client('sqs', mock_sqs)

        with patch('runner.commands.ls.SqsQueue') as MockQueue:
            mock_queue = MagicMock()
            mock_queue.len.return_value = 5
            MockQueue.return_value = mock_queue

            cmd = LsCommand(ctx)
            result = cmd.execute(opt=LsSubcommand.SQS)

            assert result == 0
            # Should handle orphaned queues gracefully

    def test_ls_ecr_with_untracked_images(self, ctx):
        """Test that ls ecr handles images not tracked in config."""
        mock_ecr = MagicMock()
        mock_ecr.describe_images.return_value = {
            'imageDetails': [
                {
                    'imageTags': ['test-project--solver1'],
                    'imageDigest': 'sha256:abc123',
                    'imageSizeInBytes': 1024000,
                    'imagePushedAt': MagicMock(strftime=lambda x: '2024-01-01 12:00:00')
                },
                {
                    'imageTags': ['test-project--untracked'],
                    'imageDigest': 'sha256:def456',
                    'imageSizeInBytes': 2048000,
                    'imagePushedAt': MagicMock(strftime=lambda x: '2024-01-01 13:00:00')
                }
            ]
        }
        ctx.set_client('ecr', mock_ecr)
        ctx.rn.get_solver_from_ecr_image_tag.side_effect = lambda x: x.split('--')[1]

        cmd = LsCommand(ctx)
        result = cmd.execute(opt=LsSubcommand.ECR)

        assert result == 0

    def test_ls_ecs_with_no_services(self, ctx):
        """Test that ls ecs handles clusters with no services."""
        mock_ecs = MagicMock()
        mock_ecs.list_clusters.return_value = {
            'clusterArns': ['arn:aws:ecs:us-west-2:123:cluster/test-project--solver1--cluster']
        }
        mock_ecs.describe_clusters.return_value = {
            'clusters': [{
                'clusterName': 'test-project--solver1--cluster',
                'clusterArn': 'arn:aws:ecs:us-west-2:123:cluster/test-project--solver1--cluster',
                'registeredContainerInstancesCount': 0
            }]
        }
        mock_ecs.list_services.return_value = {'serviceArns': []}
        mock_ecs.describe_services.return_value = {'services': []}
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_solver_from_ecs_cluster_name.return_value = 'solver1'

        cmd = LsCommand(ctx)
        result = cmd.execute(opt=LsSubcommand.ECS)

        assert result == 0

    def test_ls_resources(self, ctx):
        """Test that ls resources lists all tagged project resources."""
        with patch('common.resource_inventory_tracker.ResourceInventoryTracker') as MockTracker:
            mock_tracker = MagicMock()
            mock_resource = MagicMock()
            mock_resource.resource_arn = 'arn:aws:s3:::test-bucket'
            mock_resource.solver = 'solver1'
            mock_resource.tags = {'CreatedAt': '2024-01-01T12:00:00Z'}

            mock_tracker.list_all_project_resources.return_value = [mock_resource]
            mock_tracker.group_resources_by_type.return_value = {
                's3': [mock_resource]
            }
            mock_tracker.get_resource_count.return_value = {'s3': 1}
            MockTracker.return_value = mock_tracker

            cmd = LsCommand(ctx)
            result = cmd.execute(opt=LsSubcommand.RESOURCES)

            assert result == 0
            mock_tracker.list_all_project_resources.assert_called_once()

    def test_ls_resources_no_resources_found(self, ctx):
        """Test that ls resources handles case when no resources found."""
        with patch('common.resource_inventory_tracker.ResourceInventoryTracker') as MockTracker:
            mock_tracker = MagicMock()
            mock_tracker.list_all_project_resources.return_value = []
            MockTracker.return_value = mock_tracker

            cmd = LsCommand(ctx)
            result = cmd.execute(opt=LsSubcommand.RESOURCES)

            assert result == 0


class TestCdkHelper:
    """Tests for CdkHelper."""

    def test_mod_vpc_deploy(self, mock_rn, tmp_path):
        """Test that mod_vpc generates correct command for deploy."""
        mock_rn.get_vpc_stack_name.return_value = "test-vpc-stack"

        with patch('runner.commands.cdk.exec_cdk_command') as mock_exec:
            mock_exec.return_value = 0
            helper = CdkHelper(tmp_path, mock_rn)
            result = helper.deploy_vpc()

            assert result == 0
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args
            assert "deploy" in call_args[0][1]
            assert "test-vpc-stack" in call_args[0][1]

    def test_mod_solvers_deploy(self, mock_rn, tmp_path):
        """Test that mod_solvers generates correct command for multiple solvers."""
        mock_rn.get_solver_stack_name.side_effect = lambda s: f"stack-{s}"

        with patch('runner.commands.cdk.exec_cdk_command') as mock_exec:
            mock_exec.return_value = 0
            helper = CdkHelper(tmp_path, mock_rn)
            result = helper.deploy_solvers(["solver1", "solver2"])

            assert result == 0
            call_args = mock_exec.call_args
            assert "stack-solver1" in call_args[0][1]
            assert "stack-solver2" in call_args[0][1]

    def test_exec_cdk_command_failure_with_error_msg(self, tmp_path):
        """Test that exec_cdk_command propagates error messages on failure."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = exec_cdk_command(
                tmp_path, "deploy test-stack",
                "Deploying stack",
                "Custom error message"
            )

            assert result == 1
            # Verify environment variables are set
            call_env = mock_run.call_args[1]['env']
            assert call_env['JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION'] == '1'
            assert call_env['JSII_DEPRECATED'] == 'quiet'


class TestPurgeCommand:
    """Tests for PurgeCommand."""

    def test_execute_purges_all_solver_queues(self, ctx):
        """Test that purge calls purge on each solver's input queue."""
        mock_queue = MagicMock()

        with patch('runner.commands.jobs.SqsQueue') as MockQueue:
            MockQueue.get_sqs_queue_from_session.return_value = mock_queue

            cmd = PurgeCommand(ctx)
            result = cmd.execute()

            assert result == 0
            # Should be called twice (once per solver)
            assert MockQueue.get_sqs_queue_from_session.call_count == 2
            assert mock_queue.purge.call_count == 2


class TestSubmitCommand:
    """Tests for SubmitCommand."""

    def test_execute_prepares_and_submits_jobs(self, ctx):
        """Test that submit prepares jobs and submits to each solver queue."""
        mock_jm = MagicMock()
        mock_jm.prepare_jobs.return_value = 10  # 10 jobs found

        with patch('runner.commands.jobs.S3FileSystem') as MockS3, \
             patch('runner.commands.jobs.SqsQueue') as MockQueue:

            mock_s3 = MagicMock()
            MockS3.get_s3_file_system_from_session.return_value = mock_s3
            MockQueue.get_sqs_queue_from_session.return_value = MagicMock()

            cmd = SubmitCommand(ctx, mock_jm)
            result = cmd.execute()

            assert result == 0
            mock_jm.prepare_jobs.assert_called_once()
            assert mock_jm.submit_jobs.call_count == 2  # Once per solver

    def test_execute_returns_error_when_no_jobs_found(self, ctx):
        """Test that submit returns error when no jobs found."""
        mock_jm = MagicMock()
        mock_jm.prepare_jobs.return_value = 0  # No jobs found

        with patch('runner.commands.jobs.S3FileSystem') as MockS3:
            MockS3.get_s3_file_system_from_session.return_value = MagicMock()

            cmd = SubmitCommand(ctx, mock_jm)
            result = cmd.execute()

            assert result == 1


class TestProcessCommand:
    """Tests for ProcessCommand."""

    def test_execute_processes_all_solver_queues(self, ctx):
        """Test that process command processes output from all solver queues."""
        mock_jm = MagicMock()

        with patch('runner.commands.jobs.SqsQueue') as MockQueue:
            mock_queue = MagicMock()
            MockQueue.get_sqs_queue_from_session.return_value = mock_queue

            cmd = ProcessCommand(ctx, mock_jm)
            result = cmd.execute()

            assert result == 0
            mock_jm.make_results_dir.assert_called_once()
            # Should process each solver's output queue
            assert mock_jm.process_jobs.call_count == 2
            assert MockQueue.get_sqs_queue_from_session.call_count == 2


class TestRefreshCommand:
    """Tests for RefreshCommand."""

    @patch.object(EcsServiceManager, 'wait_for_tasks_stopped')
    @patch.object(EcsServiceManager, 'scale_solver')
    @patch.object(EcsServiceManager, 'validate_ecr_images')
    @patch.object(EcsServiceManager, 'validate_env_vars')
    @patch.object(EcsServiceManager, 'get_current_desired_count')
    @patch.object(EcsServiceManager, 'has_stale_images')
    def test_refresh_errors_if_count_is_zero(
        self, mock_has_stale, mock_get_count, mock_validate_env,
        mock_validate_ecr, mock_scale, mock_wait, ctx
    ):
        """Test that RefreshCommand returns error when current desired count is 0."""
        mock_get_count.return_value = 0

        cmd = RefreshCommand(ctx)
        result = cmd.execute()

        assert result == 1
        mock_scale.assert_not_called()

    @patch('runner.commands.ecs.prompt_purge_queues')
    @patch.object(EcsServiceManager, 'wait_for_tasks_stopped')
    @patch.object(EcsServiceManager, 'scale_solver')
    @patch.object(EcsServiceManager, 'validate_ecr_images')
    @patch.object(EcsServiceManager, 'validate_env_vars')
    @patch.object(EcsServiceManager, 'get_current_desired_count')
    @patch.object(EcsServiceManager, 'has_stale_images')
    def test_refresh_calls_standby_then_start(
        self, mock_has_stale, mock_get_count, mock_validate_env,
        mock_validate_ecr, mock_scale, mock_wait, mock_purge, ctx
    ):
        """Test that RefreshCommand calls standby (scale to 0 leaders) then start with correct count."""
        mock_get_count.return_value = 3
        mock_scale.return_value = True
        mock_wait.return_value = True
        mock_validate_ecr.return_value = True
        mock_validate_env.return_value = True
        mock_has_stale.return_value = False

        mock_solver_config = MagicMock()
        mock_solver_config.is_distributed = False
        ctx.project.get_solver.return_value = mock_solver_config

        cmd = RefreshCommand(ctx)
        result = cmd.execute()

        assert result == 0
        # First standby calls scale_solver with num_leaders=0
        # Then start calls scale_solver with num_leaders=max_count
        # We have 2 solvers, so scale_solver is called 2 times for standby + 2 for start
        assert mock_scale.call_count == 4
        # First two calls (standby): num_leaders=0, num_copies=3
        standby_calls = mock_scale.call_args_list[:2]
        for call in standby_calls:
            args = call[0]
            assert args[1] == 0  # num_leaders
            assert args[2] == 3  # num_copies

        # Last two calls (start): num_leaders=3, num_copies=3
        start_calls = mock_scale.call_args_list[2:]
        for call in start_calls:
            args = call[0]
            assert args[1] == 3  # num_leaders
            assert args[2] == 3  # num_copies


class TestHasStaleImages:
    """Tests for EcsServiceManager.has_stale_images."""

    def test_has_stale_images_returns_true_when_digests_differ(self, ctx):
        """Test that has_stale_images returns True when running container has different digest."""
        mock_ecr = MagicMock()
        mock_ecr.describe_images.return_value = {
            'imageDetails': [
                {'imageTags': ['test-project--solver1'], 'imageDigest': 'sha256:new123'},
                {'imageTags': ['test-project--solver2'], 'imageDigest': 'sha256:new456'},
            ]
        }
        ctx.set_client('ecr', mock_ecr)

        mock_ecs = MagicMock()
        mock_ecs.list_tasks.return_value = {
            'taskArns': ['arn:aws:ecs:us-west-2:123:task/cluster/task1']
        }
        mock_ecs.describe_tasks.return_value = {
            'tasks': [{
                'containers': [{
                    'imageDigest': 'sha256:old999'  # Different from ECR
                }]
            }]
        }
        ctx.set_client('ecs', mock_ecs)

        ctx.rn.get_ecr_image_tag.side_effect = lambda s: f"test-project--{s}"
        ctx.rn.get_ecr_repo_name.return_value = "test-repo"
        ctx.rn.get_ecs_cluster_name.return_value = "test-cluster"

        manager = EcsServiceManager(ctx)
        result = manager.has_stale_images(["solver1"])

        assert result is True

    def test_has_stale_images_returns_false_when_digests_match(self, ctx):
        """Test that has_stale_images returns False when running container has same digest."""
        mock_ecr = MagicMock()
        mock_ecr.describe_images.return_value = {
            'imageDetails': [
                {'imageTags': ['test-project--solver1'], 'imageDigest': 'sha256:abc123'},
            ]
        }
        ctx.set_client('ecr', mock_ecr)

        mock_ecs = MagicMock()
        mock_ecs.list_tasks.return_value = {
            'taskArns': ['arn:aws:ecs:us-west-2:123:task/cluster/task1']
        }
        mock_ecs.describe_tasks.return_value = {
            'tasks': [{
                'containers': [{
                    'imageDigest': 'sha256:abc123'  # Same as ECR
                }]
            }]
        }
        ctx.set_client('ecs', mock_ecs)

        ctx.rn.get_ecr_image_tag.side_effect = lambda s: f"test-project--{s}"
        ctx.rn.get_ecr_repo_name.return_value = "test-repo"
        ctx.rn.get_ecs_cluster_name.return_value = "test-cluster"

        manager = EcsServiceManager(ctx)
        result = manager.has_stale_images(["solver1"])

        assert result is False


class TestGetCurrentDesiredCount:
    """Tests for EcsServiceManager.get_current_desired_count."""

    def test_returns_desired_count_from_service(self, ctx):
        """Test that get_current_desired_count returns the service's desiredCount."""
        mock_ecs = MagicMock()
        mock_ecs.list_services.return_value = {
            'serviceArns': [
                'arn:aws:ecs:us-west-2:123:service/cluster/test-project--solver1--stack-SolverLeaderService-abc123'
            ]
        }
        mock_ecs.describe_services.return_value = {
            'services': [{
                'desiredCount': 5
            }]
        }
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_ecs_cluster_name.return_value = "test-cluster"
        ctx.rn.get_solver_stack_name.return_value = "test-project--solver1--stack"

        manager = EcsServiceManager(ctx)
        result = manager.get_current_desired_count("solver1")

        assert result == 5

    def test_returns_zero_when_no_leader_service_found(self, ctx):
        """Test that get_current_desired_count returns 0 when leader service is not found."""
        mock_ecs = MagicMock()
        mock_ecs.list_services.return_value = {
            'serviceArns': [
                'arn:aws:ecs:us-west-2:123:service/cluster/some-other-service'
            ]
        }
        ctx.set_client('ecs', mock_ecs)
        ctx.rn.get_ecs_cluster_name.return_value = "test-cluster"
        ctx.rn.get_solver_stack_name.return_value = "test-project--solver1--stack"

        manager = EcsServiceManager(ctx)
        result = manager.get_current_desired_count("solver1")

        assert result == 0
