"""A shim layer for the Docker Python SDK, specialized for AWS-based SAT/SMT solvers."""

import os
import subprocess
from typing import Dict, List

from common import LoggingManager, SolverEnvironment
from common.constants import DOCKER_PLATFORM
from common.resource_namer import ResourceNamer
from docker.errors import APIError, DockerException, ImageNotFound, NotFound
from docker.models.containers import Container
from docker.models.images import Image
from docker.models.networks import Network
from docker.types import Mount
from typing_extensions import deprecated

import docker

from .runner_config import ProjectConfig, SolverConfig

################################################################################
USE_DOCKER_CLI = int(os.getenv("USE_DOCKER_CLI", 1))

DOCKER_LOGGER_NAME = "Docker shim"
lm = LoggingManager()
logger = lm.get_logger(DOCKER_LOGGER_NAME, formatted=False)

################################################################################


@deprecated("Use this when local testing finally gets implemented")
class SolverContainer:
    def __init__(self, ydict: dict, solver: str = None):
        self.tag = ydict["tag"]
        self.image_name: str = ydict["image_name"] if "image_name" in ydict else solver
        self.name: str = ydict["name"] if "name" in ydict else solver
        self.num_copies: int = int(ydict["num_copies"])
        self.memory_limit: str = ydict["memory_limit"]
        self.shared_memory: str = ydict["shared_memory"]

    def full_name(self):
        return f"{self.name}:{self.tag}"

    def full_image_name(self):
        return f"{self.image_name}:{self.tag}"

    def docker_friendly_name(self):
        return self.full_name().replace(":", "-")


class SolverDockerClient:
    def __init__(self, project: ProjectConfig):
        self.project = project
        self.rn = ResourceNamer(project.project)

        try:
            self.dc = docker.from_env()
            logger.debug("Getting the Docker local client... success")
        except DockerException:
            logger.error("Error: Failed to connect to the Docker server. Is the Docker daemon running?")
            logger.error("If it isn't, try opening the Docker Desktop application.")
            exit(1)

        self.images: Dict[str, Image] = {}
        self.containers: Dict[str, Container] = {}
        self.network: Network | None = None

    def __init_network(self) -> None:
        exit(0)  # TODO refactor later
        self.network_info = SolverNetwork(self.config)
        self.get_network()

    def get_network(self) -> None:
        exit(0)  # TODO refactor later
        if self.network_info is None:
            self.__init_network()
        # CC: We use `.list()` rather than `.get()` because multiple networks of the same name might exist
        # CC: We try to prevent this case by using `check_duplicate=True` below, but this might exist beforehand
        ns: List[Network] = self.dc.networks.list(names=[self.network_info.name])
        if len(ns) == 1:
            self.network = ns[0]
            # Force a reload of the network's attributes (including `.containers`)
            # CC: My working theory is that when querying potentially many objects,
            # CC: the objects' `attrs` are not loaded. So `dc.networks.list()` gives
            # CC: you networks without attributes (such as containers) loaded.
            # CC: Since we are singling out a single network here, it's okay to reload
            self.network.reload()
        elif len(ns) > 1:
            logger.error(f'Error: Multiple Docker networks exist with the name "{self.network_info.name}".')
            logger.error("Try deleting all but one of them, or use a different name.")

    def get_or_create_network(self) -> None:
        """Gets a matching Docker network, or creates a new network with the specified name and driver.

        The (possibly new) network is set to `self.network`.
        Its information from `ydict` is stored in `self.network_info`.

        If the network already exists, this function checks whether any images
        are currently running on the network. If so, an error is reported,
        and the process exits.
        """
        # First, check to see if the network already exists
        self.get_network()
        if self.network is None:
            # Create the network
            self.network = self.dc.networks.create(
                self.network_info.name,
                driver=self.network_info.driver,  # This should be "bridge"
                check_duplicate=True,  # Ensure we don't create a duplicate network
                scope="local",
            )
            logger.info(f'Creating Docker network "{self.network_info.name}"... success')
        else:
            # The network already exists in the Docker client
            # Check that the network's driver matches the requested one
            if self.network.attrs.get("Driver") is None or self.network.attrs["Driver"] != self.network_info.driver:
                logger.error(f'Error: Network "{self.network_info.name}" already exists, but with the wrong driver.')
                exit(1)

            # Check that there are no running containers attached to the network
            # TODO: This only catches running containers. While unlikely,
            #       exited containers still "on the network" could be restarted
            #       (although local/Fargate won't start them?)
            #       Potentially expand this search for `dc.containers.list(all=True, ...)`
            # CC: Interestingly enough, exited containers still store their networks
            # CC: Trying to restart an exited container with a removed network causes an error
            cs: List[Container] = self.network.containers
            num_active = len(list(filter(lambda c: c.status != "exited", cs)))
            if num_active > 0:
                logger.error(
                    f'Error: Network "{self.network_info.name}" already exists and has {num_active} active containers.'
                )
                logger.error("Please delete all (active) containers on the network and try again.")
                exit(1)
            logger.info(f'Docker network "{self.network_info.name}" already exists... success')

    def remove_network(self) -> bool:
        """Removes the Docker network. Returns whether the removal succeeded.

        Removal can fail for several reasons. The most likely is that a container
        is still actively running on the network. The network could also not exist.
        """
        if self.network is None:
            logger.error(f"Error: The Docker network object for {self.network_info.name} is `None`.")
            logger.error(f"Make sure to call `get_or_create_docker_network()` somewhere.")
            return False
        else:
            try:
                self.network.remove()
                logger.info(f'Removing Docker network "{self.network_info.name}"... success')
                return True
            except APIError as e:
                logger.error(f'Error: API error when trying to remove network "{self.network_info.name}".')
                logger.exception(e)
                return False

    def get_image(self, sc: SolverConfig) -> Image:
        """
        Gets the `Image` object from `self.dc` and caches it in `self.images`.

        If the image doesn't exist, `ImageNotFound` is raised (by `self.dc`).
        """
        image_name = sc.get_docker_name()
        if image_name not in self.images:
            image = self.dc.images.get(image_name)
            self.images[image_name] = image
        return self.images[image_name]

    def get_repo_tagged_image(self, sc: SolverConfig, repo: str) -> Image | None:
        """
        Gets the (tagged) Docker `Image` object for remote repository `repo`.

        The result is not cached in `self.images`.
        If the tagged image doesn't exist, returns `None`.
        """
        try:
            remote_name = f"{repo}:{self.rn.get_ecr_image_tag(sc.name)}"
            image = self.dc.images.get(remote_name)
            return image
        except ImageNotFound:
            return None

    def build_image(self, sc: SolverConfig, no_cache: bool = False) -> None:
        name = sc.get_docker_name()
        d_cwd = str(sc.docker_dir)
        d_path = sc.get_rel_dockerfile_path()

        logger.info(f"Building {name}\n" f"    from {d_cwd}\n" f"    with {d_path}\n")

        # 6/4/25 (CC): Extensive testing showed that Docker's Python SDK
        # is tempramental when building multiple containers at a time.
        # For example, the cache is cleared between runs of the Python program,
        # which means that images with no underlying changes must be rebuilt,
        # which leads to long build times.
        #
        # The Docker SDK also produces larger images than the CLI (2.3GB vs. 400MB)),
        # which is most likely due to the SDK taking snapshots of each
        # layer of the image, or building an image for every possible
        # architecture, even though we only build for Linux/amd64.
        #
        # Thus, we prefer invoking the Docker CLI directly via a subprocess call,
        # but we preserve the Python SDK code path, just in case.
        # Set/export the environment variable `USE_DOCKER_CLI = 0`
        # to build with Python SDK instead.
        if USE_DOCKER_CLI:
            # This is the default code path

            # The Docker CLI strongly prefers the working directory to be set by the shell,
            # and not with the ending `path` argument (which is normally `.`)

            # The command we are replicating:
            # `docker build --platform=${PLATFORM} -f path/to/Dockerfile -t ${image}:${tag} .`
            cmd = [
                "docker",
                "build",
                f"--platform={DOCKER_PLATFORM}",
                "-f",
                d_path,
                "-t",
                name,
            ]
            if no_cache:
                cmd.append("--no-cache")
            cmd.append(".")

            subproc_result = subprocess.run(
                cmd,
                # capture_output=True,  # Un-comment to stop sending Docker build output to the terminal
                cwd=d_cwd,
                text=True,
            )

            returncode = subproc_result.returncode
            if returncode != 0:
                logger.error(f"Error: Docker build failed with return code {returncode}")
                logger.error(subproc_result.stderr)
                exit(1)

            image = self.dc.images.get(name)
        else:
            # This is the non-default code path
            image, _ = self.dc.images.build(
                path=d_cwd,
                dockerfile=d_path,
                platform=DOCKER_PLATFORM,
                tag=name,  # 'tag' is semantically overloaded. Here, the value is expected to be `name:tag`
                rm=True,  # Remove any intermediate images (the CLI removes these by default)
                forcerm=True,  # Remove any intermediate images, even on unsuccessful builds
                nocache=no_cache,
            )

        self.images[name] = image
        logger.info(f"Building image {name}... success")

    def cache_or_build_image(self, sc: SolverConfig, force_rebuild: bool, no_cache: bool = False) -> None:
        """
        Caches the Docker image, or builds it if it doesn't exist or if `force_rebuild` is `True`.

        The built image is cached in `self.images`.
        """
        name = sc.get_docker_name()
        if force_rebuild:
            self.build_image(sc, no_cache=no_cache)
        else:
            # See if the image is in the Docker client already - don't build if it is
            try:
                image = self.dc.images.get(name)
                self.images[name] = image
                logger.info(f'The image "{name}" has already been built... success')
            except ImageNotFound:
                self.build_image(image, no_cache=no_cache)

    def build_images(self, force_rebuild: bool = True, no_cache: bool = False) -> None:
        """
        Builds the images in `self.project.images`.

        By default, `force_rebuild` is set to `True`, because otherwise
        this script thinks the Docker image has already been built, even
        if the underlying solver's code has changed, and skips rebuilding
        the solver. This means we need to rebuild every solver.
        The good news is that Docker does its own caching, so even if
        an image needs to be rebuilt, many of the build steps (i.e. layers)
        get cached by the Docker engine, and the build happens quickly.
        """

        # Note: we must loop over the project's solvers in the order in which
        # they appear in the config file, since later solvers might depend
        # on earlier ones (although this should be rare).
        for image in self.project.solvers:
            self.cache_or_build_image(image, force_rebuild, no_cache=no_cache)
        logger.info("Building all Docker images... success")

    def remove_image(self, sc: SolverConfig) -> None:
        name = sc.get_docker_name()
        try:
            image = self.dc.images.get(name)
            image.remove()
            if name in self.images:
                del self.images[name]
            logger.info(f"Removing Docker image {name}... success")
        except ImageNotFound:
            logger.warning(f"Warning: Image {name} not found. Was it already removed?")

    def remove_images(self) -> None:
        for solver in self.project.solvers:
            self.remove_image(solver)
        logger.info("Removing all Docker images... success")

    def get_solvers(self) -> List[str]:
        """
        Returns a list of all solvers in the current config file.

        The names are sorted in ascending alphabetical order.
        """
        solvers = [s.name for s in self.project.solvers]
        solvers.sort()
        return solvers

    def get_aws_solvers(self) -> List[str]:
        """
        Returns a list of the solvers in the current config file that can be deployed to AWS.

        The names are sorted in ascending alphabetical order.
        """
        solvers = [s.name for s in self.project.aws_solvers]
        solvers.sort()
        return solvers

    def tag_image(self, sc: SolverConfig, repo: str) -> bool:
        image = self.get_image(sc)

        # Remove previous tagged images if the hashes are different
        # This prevents dangling Docker images, which can clog up disk space
        remote_image = self.get_repo_tagged_image(sc, repo)
        removed = True
        if remote_image is not None and remote_image.id != image.id:
            try:
                remote_image.remove()
            except APIError:
                removed = False

        image.tag(repo, self.rn.get_ecr_image_tag(sc.name))
        logger.debug(f"Tagging {sc.name} for repo {repo}... success")
        return removed

    def tag_images(self, repo: str) -> None:
        stale_count = 0
        for solver in self.project.aws_solvers:
            if not self.tag_image(solver, repo):
                stale_count += 1
        if stale_count > 0:
            logger.warning(
                f"{stale_count} stale image(s) could not be removed. "
                "Run `docker system prune` to reclaim disk space."
            )
        logger.info("Tagging images for remote repository... success")

    def push_image(self, sc: SolverConfig, repo: str) -> bool:
        logger.info(f"Pushing {sc.name} to repo {repo}...")
        response = self.dc.api.push(repo, self.rn.get_ecr_image_tag(sc.name), stream=True, decode=True)

        prev_strs = set()
        NUM_REPEATS_BEFORE_PRINT_AGAIN = 50
        counter = 0
        has_error = False

        for d in response:
            # Check for errors first
            if d.get("errorDetail") is not None:
                error_msg = d.get("errorDetail", {}).get("message", "Unknown error")
                logger.error(f"Docker push error: {error_msg}")
                has_error = True
                continue

            if d.get("error") is not None:
                logger.error(f"Docker push error: {d['error']}")
                has_error = True
                continue

            s = None
            if d.get("status") is not None:
                st = d["status"]
                # Only print something if the status is non-trivial
                if st not in ["Waiting", "Layer already exists"]:
                    if d.get("progress") is not None:
                        s = f"docker push: {d['status']}, {d['progress']}"
                    else:
                        s = f"docker push: {d['status']}"
            else:
                # Missing the 'status' key (as in Docker v28)
                # Check under 'aux' instead (as in Docker v25)
                if d.get("aux") is not None:
                    s = f"docker push: {d['aux']}"
                else:
                    s = f"docker push: {d}"

            if s is not None:
                if s in prev_strs:
                    counter += 1
                    if counter == NUM_REPEATS_BEFORE_PRINT_AGAIN:
                        counter = 0
                        logger.info(s)
                else:
                    prev_strs.add(s)
                    logger.info(s)

        if has_error:
            logger.error(f"Failed to push {sc.name} to repo {repo}")
            return False
        else:
            logger.info(f"Successfully pushed {sc.name} to repo {repo}")
            return True

    def push_images(self, repo: str) -> bool:
        success_count = 0
        total_count = len(self.project.aws_solvers)

        for solver in self.project.aws_solvers:
            if self.push_image(solver, repo):
                success_count += 1

        if success_count == total_count:
            logger.info("Pushing images to remote repository... success")
            return True
        else:
            failed_count = total_count - success_count
            logger.error(f"Pushing images to remote repository... failed ({failed_count}/{total_count} failed)")
            return False

    def tag_and_push_images(self, repo: str) -> bool:
        self.tag_images(repo)
        return self.push_images(repo)

    def log_in_to_aws(self, ecr_endpoint: str, region: str) -> None:
        """
        Log in to AWS ECR using the AWS CLI method.
        This is more reliable than the Python Docker SDK's login method.
        """
        try:
            # Use the same approach as: aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <endpoint>
            import subprocess

            # Get the ECR password
            get_password_cmd = ["aws", "ecr", "get-login-password", "--region", region]
            password_result = subprocess.run(get_password_cmd, capture_output=True, text=True, check=True)
            password = password_result.stdout.strip()

            # Login to Docker
            login_cmd = ["docker", "login", "--username", "AWS", "--password-stdin", ecr_endpoint]
            login_result = subprocess.run(login_cmd, input=password, capture_output=True, text=True, check=True)

            logger.debug("Logging in to ECR... success")

        except subprocess.CalledProcessError as e:
            logger.error(f"Error: Cannot log in to AWS ECR")
            logger.error(f"Command failed: {e.cmd}")
            logger.error(f"Return code: {e.returncode}")
            logger.error(f"Stderr: {e.stderr}")
            exit(1)
        except Exception as e:
            logger.error(f"Error: Cannot log in to AWS ECR")
            logger.exception(e)
            exit(1)

    def __init_container(self, ydict: dict) -> None:
        container_info = SolverContainer(ydict, self.solver)
        cname = container_info.full_name()
        iname = container_info.full_image_name()

        # Check that the container has not already been added
        # TODO: This requires that the tags be unique among containers
        if cname in self.container_infos:
            logger.error(f'Error: Container "{cname} was already processed.')
            logger.error("Was it included twice in the config file?")
            exit(1)
        else:
            self.container_infos[cname] = container_info

        # Check that the container is referencing a valid image
        if iname not in self.image_infos:
            logger.error(f'Error: Container "{container_info.name}" references image "{iname}", which doesn\'t exist.')
            logger.error("Does the `image_name` and `tag` match an image in the config file?")
            exit(1)

    def __init_containers(self) -> None:
        for c in self.config["containers"]:
            self.__init_container(c)

    def __run_container(self, c: SolverContainer, senv: SolverEnvironment) -> None:
        cname = c.full_name()
        iname = c.full_image_name()
        docker_cname = c.docker_friendly_name()
        image: Image = self.images[iname]

        # While the container should be removed by `remove=True` below,
        # we double-check that there is no container with this name already
        try:
            _ = self.dc.containers.get(docker_cname)
            logger.error(f'Error: A container with the name "{docker_cname}" already exists')
            if c.num_copies > 1:
                logger.error(f"If you're making multiple copies of the image {iname}, use unique names.")
            else:
                logger.error("Perhaps a previous container was not deleted?")
            return
        except NotFound:
            pass

        # TODO: Add mounts to the fun config - useful for getting copies of the input/output files
        mounts: List[Mount] = []

        logger.info(f"Starting container {cname}...")
        self.containers[cname] = self.dc.containers.run(
            image,  # The actual Docker `Image` object to use
            # command="/competition/init_solver.sh; exec bash", # First command to run, via the entrypoint
            detach=True,  # Runs the container in the background and returns a `Container` object
            # entrypoint="bash",                # The entrypoint (first program the container runs)
            environment=senv.to_dict(),
            mem_limit=c.memory_limit,  # TODO there are "soft" and "hard" memory limits (i.e. limit vs. reservation)
            mounts=mounts,  # Any mounted volumes or directories, shared with the underlying host
            name=docker_cname,  # The (unique) name of the new container
            network=self.network_info.name,  # The name of the bridge network we created previously
            # TODO: ports={'22/tcp': ... },
            platform=DOCKER_PLATFORM,  # TODO for now, assume we run solvers on AL2, which is Linux x86
            # remove=True,                        # Removes the container when it is done running
            shm_size=c.shared_memory,  # The size of the container's shared memory
            stdin_open=True,  # Keep `stdin` open, even if not attached
        )

    def run_containers(self, senv: SolverEnvironment):
        for c in self.container_infos.values():
            self.__run_container(c, senv)
        logger.info("Running all containers... success")

    def __remove_container(self, container_info: SolverContainer) -> None:
        cname = container_info.full_name()
        docker_cname = container_info.docker_friendly_name()

        try:
            container = self.dc.containers.get(docker_cname)
            container.remove(force=True)
            logger.info(f"Removing container {cname}... success")
        except docker.errors.NotFound:
            logger.error(f'Error: Container "{cname}" ({docker_cname}) not found.')
            logger.error("Perhaps it was already removed?")

    def __remove_containers_associated_with(self, sc: SolverConfig) -> None:
        cs = self.dc.containers.list(filters={"ancestor": sc.full_name()})
        for c in cs:
            self.__remove_container(c)

    def remove_containers(self) -> None:
        for image in self.image_infos.values():
            self.__remove_containers_associated_with(image)
        logger.info("Removing containers... success")
