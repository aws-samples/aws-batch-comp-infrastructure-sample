"""Base classes for command handlers.

This module provides the CommandContext dataclass for dependency injection
and the CommandHandler ABC that all commands inherit from.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

from boto3 import Session
from common import LoggingManager, ResourceNamer
from runner.runner_config import ProjectConfig
from runner.runner_docker import SolverDockerClient

lm = LoggingManager()


@dataclass
class CommandContext:
    """Context object containing shared dependencies for all commands.

    This enables dependency injection for testing - you can pass in mock
    clients and configs instead of having commands create their own.
    """

    project: ProjectConfig
    sdc: SolverDockerClient
    cdk_path: Path
    boto3_session: Session | None = None
    account: str | None = None
    rn: ResourceNamer | None = None
    _clients: dict = field(default_factory=dict, repr=False)

    @property
    def solvers(self) -> List[str]:
        """All solver names from config."""
        return self.sdc.get_solvers()

    @property
    def aws_solvers(self) -> List[str]:
        """AWS-deployable solver names from config."""
        return self.sdc.get_aws_solvers()

    def get_client(self, service: str) -> Any:
        """Lazy-create and cache boto3 clients.

        Args:
            service: AWS service name (e.g., 'ecs', 'ecr', 'sqs')

        Returns:
            boto3 client for the requested service

        Raises:
            RuntimeError: If boto3_session is not initialized
        """
        if self.boto3_session is None:
            raise RuntimeError("AWS session not initialized. This command requires AWS credentials.")

        if service not in self._clients:
            self._clients[service] = self.boto3_session.client(service)
        return self._clients[service]

    def set_client(self, service: str, client: Any) -> None:
        """Inject a client for testing purposes.

        Args:
            service: AWS service name
            client: Client instance (can be a mock)
        """
        self._clients[service] = client


class CommandHandler(ABC):
    """Abstract base class for all command handlers.

    Subclasses implement the execute() method with command-specific logic.
    The handler has access to the shared CommandContext for dependencies.
    """

    def __init__(self, ctx: CommandContext, logger=None):
        """Initialize the command handler.

        Args:
            ctx: Shared context with project config and AWS clients
            logger: Optional logger instance (defaults to class-named logger)
        """
        self.ctx = ctx
        self.logger = logger or lm.get_logger(self.__class__.__name__)

    @abstractmethod
    def execute(self, **kwargs) -> int:
        """Execute the command.

        Args:
            **kwargs: Command-specific arguments

        Returns:
            0 on success, non-zero on error
        """
        pass
