"""Tests for SolverDockerClient in runner_docker.py.

Tests cover:
  - Client initialization and Docker daemon connection
  - Solver listing methods
  - Image tagging logic
  - Error handling for missing images
  - Push error handling

Uses mocks to avoid requiring a running Docker daemon.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import pytest
import yaml

from docker.errors import DockerException, ImageNotFound


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_project_config(tmp_path):
    """Create a mock ProjectConfig with test solvers."""
    # Create a minimal config file
    config = {
        "project": "testproject",
        "profile": "default",
        "region": "us-east-1",
        "solver_type": "sat",
        "global_solver_options": {
            "is_distributed": False,
            "num_worker_nodes_per_leader": 0,
            "ec2_instance_type": "m6i.xlarge",
            "disk_size": 32,
        },
        "solvers": [
            {"name": "solver-a", "docker_dir": str(tmp_path), "dockerfile": "Dockerfile"},
            {"name": "solver-b", "docker_dir": str(tmp_path), "dockerfile": "Dockerfile"},
        ],
    }
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.dump(config))

    # Create dummy Dockerfiles
    (tmp_path / "Dockerfile").write_text("FROM ubuntu:latest\n")

    from runner.runner_config import ProjectConfig
    return ProjectConfig(str(config_path))


@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client."""
    mock_client = MagicMock()
    mock_client.images = MagicMock()
    mock_client.containers = MagicMock()
    mock_client.networks = MagicMock()
    mock_client.api = MagicMock()
    return mock_client


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------

class TestDockerClientInit:
    """Test SolverDockerClient initialization."""

    def test_init_success(self, mock_project_config, mock_docker_client):
        """Test successful initialization with Docker running."""
        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)
            assert client.dc == mock_docker_client
            assert client.project == mock_project_config

    def test_init_docker_not_running(self, mock_project_config):
        """Test initialization when Docker daemon is not running."""
        with patch("runner.runner_docker.docker.from_env", side_effect=DockerException("Connection refused")):
            from runner.runner_docker import SolverDockerClient
            with pytest.raises(SystemExit):
                SolverDockerClient(mock_project_config)


# ---------------------------------------------------------------------------
# Solver listing tests
# ---------------------------------------------------------------------------

class TestSolverListing:
    """Test solver listing methods."""

    def test_get_solvers_returns_sorted_list(self, mock_project_config, mock_docker_client):
        """Test that get_solvers returns sorted solver names."""
        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)
            solvers = client.get_solvers()
            # Verify list is sorted
            assert solvers == sorted(solvers)
            # Verify solvers from config are present
            assert "solver-a" in solvers
            assert "solver-b" in solvers

    def test_get_aws_solvers_returns_sorted_list(self, mock_project_config, mock_docker_client):
        """Test that get_aws_solvers returns sorted solver names."""
        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)
            solvers = client.get_aws_solvers()
            assert solvers == sorted(solvers)


# ---------------------------------------------------------------------------
# Image operations tests
# ---------------------------------------------------------------------------

class TestImageOperations:
    """Test image-related operations."""

    def test_get_image_caches_result(self, mock_project_config, mock_docker_client):
        """Test that get_image caches the image object."""
        mock_image = MagicMock()
        mock_docker_client.images.get.return_value = mock_image

        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)

            sc = mock_project_config.solvers[0]
            image1 = client.get_image(sc)
            image2 = client.get_image(sc)

            assert image1 == mock_image
            assert image2 == mock_image
            # Should only call docker once due to caching
            assert mock_docker_client.images.get.call_count == 1

    def test_get_image_raises_on_not_found(self, mock_project_config, mock_docker_client):
        """Test that get_image raises ImageNotFound if image doesn't exist."""
        mock_docker_client.images.get.side_effect = ImageNotFound("Image not found")

        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)

            sc = mock_project_config.solvers[0]
            with pytest.raises(ImageNotFound):
                client.get_image(sc)

    def test_get_repo_tagged_image_returns_none_if_not_found(self, mock_project_config, mock_docker_client):
        """Test that get_repo_tagged_image returns None if tagged image doesn't exist."""
        mock_docker_client.images.get.side_effect = ImageNotFound("Image not found")

        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)

            sc = mock_project_config.solvers[0]
            result = client.get_repo_tagged_image(sc, "test-repo")
            assert result is None

    def test_remove_image_handles_not_found(self, mock_project_config, mock_docker_client):
        """Test that remove_image handles ImageNotFound gracefully."""
        mock_docker_client.images.get.side_effect = ImageNotFound("Image not found")

        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)

            sc = mock_project_config.solvers[0]
            # Should not raise, just log warning
            client.remove_image(sc)


# ---------------------------------------------------------------------------
# Tag operations tests
# ---------------------------------------------------------------------------

class TestTagOperations:
    """Test image tagging operations."""

    def test_tag_image_calls_docker_tag(self, mock_project_config, mock_docker_client):
        """Test that tag_image calls Docker's tag method."""
        mock_image = MagicMock()
        mock_docker_client.images.get.return_value = mock_image

        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)

            sc = mock_project_config.solvers[0]
            client.tag_image(sc, "test-repo")

            mock_image.tag.assert_called_once()
            call_args = mock_image.tag.call_args
            assert call_args[0][0] == "test-repo"

    def test_tag_image_removes_old_tagged_image_if_different(self, mock_project_config, mock_docker_client):
        """Test that tag_image removes old tagged image if hashes differ."""
        mock_image = MagicMock()
        mock_image.id = "new-hash"

        mock_old_tagged_image = MagicMock()
        mock_old_tagged_image.id = "old-hash"

        # First call returns the new image, second returns the old tagged image
        mock_docker_client.images.get.side_effect = [mock_image, mock_old_tagged_image]

        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)

            sc = mock_project_config.solvers[0]
            client.tag_image(sc, "test-repo")

            # Old image should be removed
            mock_old_tagged_image.remove.assert_called_once()

    def test_tag_image_still_tags_when_remove_raises_api_error(self, mock_project_config, mock_docker_client):
        """Test that tag_image still applies the tag even when remote_image.remove() raises APIError.

        Previously the method returned False early, skipping the tag. Now it catches
        the APIError, still applies the tag, but returns False to indicate stale removal failed.
        """
        from docker.errors import APIError

        mock_image = MagicMock()
        mock_image.id = "new-hash"

        mock_old_tagged_image = MagicMock()
        mock_old_tagged_image.id = "old-hash"
        mock_old_tagged_image.remove.side_effect = APIError("Conflict: image is in use")

        # First call returns the new image, second returns the old tagged image
        mock_docker_client.images.get.side_effect = [mock_image, mock_old_tagged_image]

        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)

            sc = mock_project_config.solvers[0]
            result = client.tag_image(sc, "test-repo")

            # The tag should still be applied even though remove failed
            mock_image.tag.assert_called_once()
            # Result should be False because stale removal failed
            assert result is False


# ---------------------------------------------------------------------------
# Push operations tests
# ---------------------------------------------------------------------------

class TestPushOperations:
    """Test image push operations."""

    def test_push_image_success(self, mock_project_config, mock_docker_client):
        """Test successful image push."""
        # Mock the push response stream
        mock_docker_client.api.push.return_value = iter([
            {"status": "Pushing"},
            {"status": "Pushed"},
        ])

        # Mock get_image to return a valid image
        mock_image = MagicMock()
        mock_docker_client.images.get.return_value = mock_image

        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)
            client.images[mock_project_config.solvers[0].get_docker_name()] = mock_image

            sc = mock_project_config.solvers[0]
            result = client.push_image(sc, "test-repo")

            assert result is True

    def test_push_image_handles_error(self, mock_project_config, mock_docker_client):
        """Test push_image handles errors in response."""
        # Mock the push response with an error
        mock_docker_client.api.push.return_value = iter([
            {"status": "Pushing"},
            {"errorDetail": {"message": "Access denied"}},
        ])

        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)

            sc = mock_project_config.solvers[0]
            result = client.push_image(sc, "test-repo")

            assert result is False

    def test_push_images_returns_false_on_any_failure(self, mock_project_config, mock_docker_client):
        """Test push_images returns False if any push fails."""
        # First push succeeds, second fails
        call_count = [0]
        def mock_push(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return iter([{"status": "Pushed"}])
            else:
                return iter([{"error": "Failed"}])

        mock_docker_client.api.push.side_effect = mock_push

        with patch("runner.runner_docker.docker.from_env", return_value=mock_docker_client):
            from runner.runner_docker import SolverDockerClient
            client = SolverDockerClient(mock_project_config)

            result = client.push_images("test-repo")

            assert result is False


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------

class TestDockerConstants:
    """Test Docker-related constants."""

    def test_docker_platform_is_linux_amd64(self):
        from runner.runner_docker import DOCKER_PLATFORM
        assert DOCKER_PLATFORM == "linux/amd64"
