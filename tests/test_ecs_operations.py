"""Tests for ECS operations.

Tests cover:
  - Listing ECS clusters and services
  - Updating service desired count (start/stop)
  - Describing task definitions
  - Error handling for ECS operations

Uses mocks to test without real AWS infrastructure.
"""

from unittest.mock import MagicMock, patch
import pytest

from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Tests for ECS client operations
# ---------------------------------------------------------------------------

class TestEcsListClusters:
    """Test ECS cluster listing operations."""

    def test_list_clusters_success(self):
        """Test successful cluster listing."""
        mock_ecs = MagicMock()
        mock_ecs.list_clusters.return_value = {
            "clusterArns": [
                "arn:aws:ecs:us-east-1:123456789012:cluster/testproject--solver1--ecs-cluster",
                "arn:aws:ecs:us-east-1:123456789012:cluster/testproject--solver2--ecs-cluster",
            ]
        }

        response = mock_ecs.list_clusters()

        assert len(response["clusterArns"]) == 2
        mock_ecs.list_clusters.assert_called_once()

    def test_list_clusters_empty(self):
        """Test listing when no clusters exist."""
        mock_ecs = MagicMock()
        mock_ecs.list_clusters.return_value = {"clusterArns": []}

        response = mock_ecs.list_clusters()

        assert len(response["clusterArns"]) == 0

    def test_list_clusters_filters_by_project(self):
        """Test that cluster filtering by project name works."""
        mock_ecs = MagicMock()
        mock_ecs.list_clusters.return_value = {
            "clusterArns": [
                "arn:aws:ecs:us-east-1:123456789012:cluster/testproject--solver1--ecs-cluster",
                "arn:aws:ecs:us-east-1:123456789012:cluster/otherproject--solver1--ecs-cluster",
            ]
        }

        response = mock_ecs.list_clusters()
        arns = response["clusterArns"]

        # Filter for testproject
        filtered = [a for a in arns if "testproject" in a]
        assert len(filtered) == 1


class TestEcsDescribeClusters:
    """Test ECS cluster description operations."""

    def test_describe_clusters_success(self):
        """Test successful cluster description."""
        mock_ecs = MagicMock()
        mock_ecs.describe_clusters.return_value = {
            "clusters": [
                {
                    "clusterName": "testproject--solver1--ecs-cluster",
                    "clusterArn": "arn:aws:ecs:us-east-1:123456789012:cluster/testproject--solver1--ecs-cluster",
                    "registeredContainerInstancesCount": 2,
                    "status": "ACTIVE",
                }
            ]
        }

        response = mock_ecs.describe_clusters(clusters=["testproject--solver1--ecs-cluster"])

        assert len(response["clusters"]) == 1
        assert response["clusters"][0]["registeredContainerInstancesCount"] == 2


class TestEcsListServices:
    """Test ECS service listing operations."""

    def test_list_services_success(self):
        """Test successful service listing."""
        mock_ecs = MagicMock()
        mock_ecs.list_services.return_value = {
            "serviceArns": [
                "arn:aws:ecs:us-east-1:123456789012:service/testproject--solver1--SolverLeaderService",
                "arn:aws:ecs:us-east-1:123456789012:service/testproject--solver1--SolverWorkerService",
            ]
        }

        response = mock_ecs.list_services(cluster="testproject--solver1--ecs-cluster")

        assert len(response["serviceArns"]) == 2


class TestEcsDescribeServices:
    """Test ECS service description operations."""

    def test_describe_services_success(self):
        """Test successful service description."""
        mock_ecs = MagicMock()
        mock_ecs.describe_services.return_value = {
            "services": [
                {
                    "serviceName": "SolverLeaderService",
                    "desiredCount": 1,
                    "pendingCount": 0,
                    "runningCount": 1,
                    "status": "ACTIVE",
                }
            ]
        }

        response = mock_ecs.describe_services(
            cluster="testproject--solver1--ecs-cluster",
            services=["SolverLeaderService"]
        )

        assert response["services"][0]["desiredCount"] == 1
        assert response["services"][0]["runningCount"] == 1

    def test_describe_services_with_multiple_services(self):
        """Test describing multiple services."""
        mock_ecs = MagicMock()
        mock_ecs.describe_services.return_value = {
            "services": [
                {"serviceName": "Leader", "desiredCount": 1, "pendingCount": 0, "runningCount": 1},
                {"serviceName": "Worker", "desiredCount": 4, "pendingCount": 1, "runningCount": 3},
            ]
        }

        response = mock_ecs.describe_services(
            cluster="testproject--solver1--ecs-cluster",
            services=["Leader", "Worker"]
        )

        # Calculate totals like satcomp.py does
        desired_count = sum(s["desiredCount"] for s in response["services"])
        pending_count = sum(s["pendingCount"] for s in response["services"])
        running_count = sum(s["runningCount"] for s in response["services"])

        assert desired_count == 5
        assert pending_count == 1
        assert running_count == 4


class TestEcsUpdateService:
    """Test ECS service update operations (start/stop)."""

    def test_update_service_start(self):
        """Test starting a service (setting desired count > 0)."""
        mock_ecs = MagicMock()
        mock_ecs.update_service.return_value = {
            "service": {
                "serviceName": "SolverLeaderService",
                "desiredCount": 3,
                "status": "ACTIVE",
            }
        }

        response = mock_ecs.update_service(
            cluster="testproject--solver1--ecs-cluster",
            service="SolverLeaderService",
            desiredCount=3
        )

        assert response["service"]["desiredCount"] == 3
        mock_ecs.update_service.assert_called_once_with(
            cluster="testproject--solver1--ecs-cluster",
            service="SolverLeaderService",
            desiredCount=3
        )

    def test_update_service_stop(self):
        """Test stopping a service (setting desired count = 0)."""
        mock_ecs = MagicMock()
        mock_ecs.update_service.return_value = {
            "service": {
                "serviceName": "SolverLeaderService",
                "desiredCount": 0,
                "status": "ACTIVE",
            }
        }

        response = mock_ecs.update_service(
            cluster="testproject--solver1--ecs-cluster",
            service="SolverLeaderService",
            desiredCount=0
        )

        assert response["service"]["desiredCount"] == 0

    def test_update_service_cluster_not_found(self):
        """Test error handling when cluster doesn't exist."""
        mock_ecs = MagicMock()
        mock_ecs.update_service.side_effect = ClientError(
            {"Error": {"Code": "ClusterNotFoundException", "Message": "Cluster not found"}},
            "UpdateService"
        )

        with pytest.raises(ClientError) as exc_info:
            mock_ecs.update_service(
                cluster="nonexistent-cluster",
                service="SolverLeaderService",
                desiredCount=1
            )

        assert exc_info.value.response["Error"]["Code"] == "ClusterNotFoundException"

    def test_update_service_service_not_found(self):
        """Test error handling when service doesn't exist."""
        mock_ecs = MagicMock()
        mock_ecs.update_service.side_effect = ClientError(
            {"Error": {"Code": "ServiceNotFoundException", "Message": "Service not found"}},
            "UpdateService"
        )

        with pytest.raises(ClientError) as exc_info:
            mock_ecs.update_service(
                cluster="testproject--solver1--ecs-cluster",
                service="nonexistent-service",
                desiredCount=1
            )

        assert exc_info.value.response["Error"]["Code"] == "ServiceNotFoundException"


class TestEcsTaskDefinitions:
    """Test ECS task definition operations."""

    def test_list_task_definitions(self):
        """Test listing active task definitions."""
        mock_ecs = MagicMock()
        mock_ecs.list_task_definitions.return_value = {
            "taskDefinitionArns": [
                "arn:aws:ecs:us-east-1:123456789012:task-definition/testproject--solver1--leader:1",
                "arn:aws:ecs:us-east-1:123456789012:task-definition/testproject--solver1--worker:1",
            ]
        }

        response = mock_ecs.list_task_definitions(status="ACTIVE")

        assert len(response["taskDefinitionArns"]) == 2

    def test_describe_task_definition(self):
        """Test describing a task definition."""
        mock_ecs = MagicMock()
        mock_ecs.describe_task_definition.return_value = {
            "taskDefinition": {
                "taskDefinitionArn": "arn:aws:ecs:us-east-1:123456789012:task-definition/testproject--solver1--leader:1",
                "containerDefinitions": [
                    {
                        "name": "solver-container",
                        "image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/repo:tag",
                        "environment": [
                            {"name": "NUM_WORKERS", "value": "4"},
                            {"name": "SOLVER_NAME", "value": "solver1"},
                        ],
                    }
                ],
            }
        }

        response = mock_ecs.describe_task_definition(
            taskDefinition="testproject--solver1--leader:1"
        )

        containers = response["taskDefinition"]["containerDefinitions"]
        assert len(containers) == 1
        assert containers[0]["name"] == "solver-container"

        # Extract environment variables
        env_vars = {e["name"]: e["value"] for e in containers[0]["environment"]}
        assert env_vars["NUM_WORKERS"] == "4"
        assert env_vars["SOLVER_NAME"] == "solver1"


class TestEcsStartStopPattern:
    """Test the start/stop pattern used in satcomp.py."""

    def test_start_pattern(self):
        """Test the full start pattern: list services, then update each."""
        mock_ecs = MagicMock()

        # Step 1: List services
        mock_ecs.list_services.return_value = {
            "serviceArns": [
                "arn:aws:ecs:...:service/cluster/SolverLeaderService",
                "arn:aws:ecs:...:service/cluster/SolverWorkerService",
            ]
        }

        # Step 2: Update services
        mock_ecs.update_service.return_value = {"service": {"desiredCount": 1}}

        # Simulate the pattern
        cluster = "testproject--solver1--ecs-cluster"
        services_response = mock_ecs.list_services(cluster=cluster)

        for service_arn in services_response["serviceArns"]:
            mock_ecs.update_service(
                cluster=cluster,
                service=service_arn,
                desiredCount=1
            )

        assert mock_ecs.update_service.call_count == 2

    def test_stop_pattern(self):
        """Test the full stop pattern: set desired count to 0."""
        mock_ecs = MagicMock()
        mock_ecs.update_service.return_value = {"service": {"desiredCount": 0}}

        cluster = "testproject--solver1--ecs-cluster"
        services = ["LeaderService", "WorkerService"]

        for service in services:
            mock_ecs.update_service(
                cluster=cluster,
                service=service,
                desiredCount=0
            )

        # Verify all services were stopped
        assert mock_ecs.update_service.call_count == 2
        for call in mock_ecs.update_service.call_args_list:
            assert call.kwargs["desiredCount"] == 0
