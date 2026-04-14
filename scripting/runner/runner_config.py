"""Classes representing data that appears in the config files."""

from pathlib import Path
from typing import Dict, List

import common.pathing as pathing
import yaml
from common.cdk_data import CdkSolver
from common.constants import INFRASTRUCTURE_SOLVER_NAME
from common.misc import check_not_none, union_overwrite_none
from common.solver_logging import LoggingManager

################################################################################

SCRIPT_DIR = pathing.normalize_path(__file__).parent

lm = LoggingManager()
logger = lm.get_logger("RunnerConfig", formatted=False)

FIELD_SEPARATOR = "--"

################################################################################


def check_no_double_hyphen(name: str, label: str):
    """Reject names containing the field separator '--'."""
    if FIELD_SEPARATOR in name:
        logger.error(
            f'Error: {label} "{name}" must not contain "{FIELD_SEPARATOR}" '
            f"because it is used as a field separator in resource names."
        )
        exit(1)


def check_valid_docker_str(s: str):
    # According to Docker's documentation, name and tag strings must be lowercase
    # TODO: This isn't actually true, see
    # https://ktomk.github.io/pipelines/doc/DOCKER-NAME-TAG.html#image-name
    if any(ch.isupper() for ch in s):
        logger.error(f'Error: Docker string "{s}" cannot contain uppercase characters')
        logger.error("This is because Docker only accepts image and tag names that are lowercase")
        exit(1)


class NetworkConfig:

    RESERVED_NETWORKS = ["bridge", "host", "none"]

    def __init__(self, d: dict):
        # Validate that the appropriate fields are present in the dictionary
        check_not_none(d, "network", logger, "Provide a `network` field in the config file.")
        check_not_none(
            d["network"], "name", logger, "Provide a `name` field under the `network` field in the config file."
        )
        check_not_none(
            d["network"], "bridge", logger, "Provide a `bridge` field under the `network` field in the config file."
        )

        nd = d["network"]

        # Get the name of the network, and check that it's not a reserved name
        self.name: str = nd["name"]
        if self.name in self.RESERVED_NETWORKS:
            logger.error(f'Error: Network name "{self.name}" cannot be one of {self.RESERVED_NETWORKS}.')
            exit(1)

        # For now, the driver should probably be "bridge"
        self.driver: str = nd["driver"]
        if self.driver != "bridge":
            logger.warning(f'Warning: Network driver "{self.driver}" is not "bridge". Be careful.')


class SolverConfig:

    NAME_KEY = "name"
    AUTHOR_KEY = "author"
    DOCKER_DIR_KEY = "docker_dir"
    DOCKERFILE_KEY = "dockerfile"

    def __init__(self, d: dict):
        check_not_none(d, self.NAME_KEY, logger)
        self.name = d[self.NAME_KEY]
        self.author = d.get(self.AUTHOR_KEY)  # Optional field
        check_no_double_hyphen(self.name, "Solver name")
        check_valid_docker_str(self.name)

        # Helper function to check the existence of keys
        def check_key(key: str, d: dict = d, err_ending: str | None = None):
            error_msg = f'Solver "{self.name}" is missing its `{key}` field'
            if err_ending is not None:
                error_msg += f" {err_ending}"
            check_not_none(d, key, logger, error_msg=error_msg)

        # Validate that certain required values are present
        check_key(self.DOCKER_DIR_KEY)
        check_key(self.DOCKERFILE_KEY)
        check_key(CdkSolver.IS_DIST_KEY)
        if d[CdkSolver.IS_DIST_KEY]:
            check_key(CdkSolver.NUM_WORKERS_KEY)

        # Process Docker options
        self.docker_dir: Path = pathing.normalize_path(d[self.DOCKER_DIR_KEY], relative_to=SCRIPT_DIR)
        self.dockerfile: Path = pathing.normalize_path(d[self.DOCKERFILE_KEY], relative_to=self.docker_dir)
        self.validate_dockerfile_paths()

        self.is_distributed = d[CdkSolver.IS_DIST_KEY]
        self.is_parallel = not self.is_distributed

        # Process AWS deployment options, if they exist
        self.push: bool = d.get(CdkSolver.EC2_INSTANCE_KEY) is not None
        self.cdk_solver = CdkSolver.from_dict(d) if self.push else None

    def validate_dockerfile_paths(self):
        """Check that the Dockerfile exists and is readable."""
        pathing.check_path_is_dir(self.docker_dir, logger)
        pathing.check_path_is_readable_file(self.dockerfile, logger)
        if not self.dockerfile.is_relative_to(self.docker_dir):
            logger.error(f'Error: "{self.docker_dir}" does not contain {self.dockerfile}')
            exit(1)

    @classmethod
    def satcomp_infra_solver(cls) -> "SolverConfig":
        return SolverConfig(
            {
                cls.NAME_KEY: INFRASTRUCTURE_SOLVER_NAME,
                cls.DOCKER_DIR_KEY: "../..",
                cls.DOCKERFILE_KEY: "docker/satcomp-infrastructure/Dockerfile",
                CdkSolver.IS_DIST_KEY: False,
            }
        )

    def get_docker_name(self):
        """Get the full Docker-formatted name of the image, i.e., `name:tag`."""
        return f"{self.name}:latest"

    def get_aws_name(self):
        """
        Get the solver's Docker name, formatted for AWS.

        Note for future developers:
        If you add a `tag` field to the configuration file per solver,
        then the AWS name must use `-` instead of `:` between the base
        name and the tag. This is because, on AWS, the image's "name"
        is actually a tag, so we can't use `:` as a separator.
        """
        return self.name

    def get_rel_dockerfile_path(self) -> Path:
        """Get the path of the Dockerfile, relative to the Docker build directory."""
        return self.dockerfile.relative_to(self.docker_dir)


class ProjectConfig:

    GLOBAL_OPTS_KEY = "global_solver_options"

    def __init__(self, config_path: str | Path):
        self.config_path = pathing.normalize_path(config_path)
        pathing.check_path_is_readable_file(self.config_path)
        with open(self.config_path, "r") as f:
            self.config: dict = yaml.safe_load(f)

        FIELDS = ["project", "profile", "region", "solver_type", "solvers"]
        for field in FIELDS:
            check_not_none(
                self.config, field, logger, f"Config file at {config_path} is missing a top-level `{field}` field."
            )

        self.project = self.config["project"]
        check_no_double_hyphen(self.project, "Project name")
        self.profile = self.config["profile"]
        self.region = self.config["region"]

        raw_type = self.config["solver_type"].strip().lower()
        if raw_type not in ("sat", "smt"):
            logger.error(f"Error: `solver_type` must be 'sat' or 'smt' (was {self.config['solver_type']!r})")
            exit(1)
        self.solver_type: str = raw_type
        # TODO validate that `self.region` is a valid AWS region

        # Parse global options, to use as default values in the `solvers` list
        defaults = {}
        if self.config.get(self.GLOBAL_OPTS_KEY) is not None:
            global_opts = self.config[self.GLOBAL_OPTS_KEY]
            union_overwrite_none(defaults, global_opts, CdkSolver.CONFIG_KEYS)

        self.solvers: List[SolverConfig] = []
        self.aws_solvers: List[SolverConfig] = []
        self.solvers_by_name: Dict[str, SolverConfig] = {}
        self.has_image_to_push: bool = False

        # Helper function to add the solver to the various data structures
        def add_solver(solver: SolverConfig):
            # No duplicate solver names are allowed
            if solver.name in self.solvers_by_name:
                logger.error(f'Error: Solver "{solver.name}" appeared twice in the config file.')
                exit(1)

            self.solvers.append(solver)
            self.solvers_by_name[solver.name] = solver
            if solver.push:
                self.aws_solvers.append(solver)
                self.has_image_to_push = True

        # Actually add the solvers, including the base satcomp-infra solver
        add_solver(SolverConfig.satcomp_infra_solver())
        for s in self.config["solvers"]:
            union_overwrite_none(s, defaults, CdkSolver.CONFIG_KEYS)
            solver = SolverConfig(s)
            add_solver(solver)

    def get_solver(self, name: str) -> SolverConfig:
        """
        Gets the `SolverConfig` from the config file corresponding to `name`.

        The `name` parameter should come from `solver.name`.
        """
        if name not in self.solvers_by_name:
            logger.error(f'Error: Solver "{name}" not found in config file.')
            exit(1)
        return self.solvers_by_name[name]
