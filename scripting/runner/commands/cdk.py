"""CDK command execution utilities."""

import os
import subprocess
import sys
from pathlib import Path
from typing import List

from common import ResourceNamer

DEPLOY_BASE_CMD = "deploy --require-approval never"
DESTROY_BASE_CMD = "destroy --require-approval never"


def exec_cdk_command(
    cdk_path: Path, cmd: str, info_msg: str, error_msg: str | None = None, with_output: bool = True
) -> int:
    """Execute a CDK command in the CDK directory.

    Args:
        cdk_path: Path to the CDK directory
        cmd: CDK command to run (e.g., "deploy --all")
        info_msg: Message to display before running
        error_msg: Additional error message if command fails
        with_output: Whether to handle output/errors (default True)

    Returns:
        Return code from the CDK command (0 on success)
    """
    first_cmd = cmd.split(" ")[0]
    print(f"{first_cmd}: {info_msg}")
    print(f"% cd {cdk_path}")
    print(f"% cdk {cmd}")

    # Turn off any CDK security notices
    # See https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-notices.html
    cmd_as_list = ["cdk", "--no-notices"] + cmd.split(" ")

    # Suppress the annoying !!!!! node untested version warning and deprecation warnings
    env = os.environ.copy()
    env["JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION"] = "1"
    env["JSII_DEPRECATED"] = "quiet"

    proc = subprocess.run(
        cmd_as_list,
        cwd=cdk_path,
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )

    if with_output:
        if proc.returncode != 0:
            print(f"Error: cdk {cmd} failed. Examine the output above for the precise error.", file=sys.stderr)
            if error_msg is not None:
                print(error_msg, file=sys.stderr)
            return 1
        else:
            print(f"cdk {cmd} success")

    return proc.returncode


class CdkHelper:
    """Helper class for executing CDK commands."""

    def __init__(self, cdk_path: Path, rn: ResourceNamer | None = None):
        """Initialize CDK helper.

        Args:
            cdk_path: Path to the CDK directory
            rn: ResourceNamer for generating stack names
        """
        self.cdk_path = cdk_path
        self.rn = rn

    def bootstrap(self) -> int:
        """Run CDK bootstrap to prepare AWS account for CDK deployments.

        Returns:
            0 on success, 1 on error
        """
        return exec_cdk_command(
            self.cdk_path,
            "bootstrap",
            "Prepare your AWS account for CDK deployments.",
            "Most likely, you haven't authenticated with an AWS account.",
        )

    def _mod_stack(self, stack: str, is_deploy: bool, msg: str) -> int:
        """Deploy or destroy a CDK stack.

        Args:
            stack: Stack name or --all
            is_deploy: True for deploy, False for destroy
            msg: Description message

        Returns:
            0 on success, 1 on error
        """
        action = "Deploy" if is_deploy else "Destroy"
        cmd = DEPLOY_BASE_CMD if is_deploy else DESTROY_BASE_CMD
        return exec_cdk_command(self.cdk_path, f"{cmd} {stack}", f"{action} {msg}")

    def mod_vpc(self, is_deploy: bool) -> int:
        """Deploy or destroy the VPC stack."""
        return self._mod_stack(
            self.rn.get_vpc_stack_name(), is_deploy, "the virtual private cloud. All ECS containers use the VPC."
        )

    def mod_ecr_repo(self, is_deploy: bool) -> int:
        """Deploy or destroy the ECR repository stack."""
        return self._mod_stack(
            self.rn.get_ecr_repo_stack_name(), is_deploy, "the ECR repository and all its uploaded Docker images."
        )

    def mod_s3(self, is_deploy: bool) -> int:
        """Deploy or destroy the S3 results bucket stack."""
        return self._mod_stack(
            self.rn.get_results_bucket_stack_name(), is_deploy, "the bucket containing solver results."
        )

    def mod_all(self, is_deploy: bool) -> int:
        """Deploy or destroy all CDK stacks."""
        return self._mod_stack("--all", is_deploy, "all currently-managed CDK resources. Takes 3-5 minutes per solver.")

    def mod_solvers(self, solvers: List[str], is_deploy: bool) -> int:
        """Deploy or destroy solver stacks.

        Note: Deploying solvers also deploys the logs,
        but destroying solvers does NOT destroy its logs.

        Args:
            solvers: List of solver names
            is_deploy: True for deploy, False for destroy

        Returns:
            0 on success, 1 on error
        """
        if is_deploy:
            stacks = []
            for s in solvers:
                stacks.append(self.rn.get_solver_stack_name(s))
            msg = "the solver and its log groups. Takes about 5 minutes per solver."
        else:
            stacks = [self.rn.get_solver_stack_name(s) for s in solvers]
            msg = "the solvers. (Not their log groups.) Takes about 3 minutes per solver."
        stacks_str = " ".join(stacks)
        return self._mod_stack(stacks_str, is_deploy, msg)

    def mod_logs(self, solvers: List[str], is_deploy: bool) -> int:
        """Deploy or destroy log group stacks.

        Args:
            solvers: List of solver names
            is_deploy: True for deploy, False for destroy

        Returns:
            0 on success, 1 on error
        """
        log_stacks = [self.rn.get_log_group_stack_name(s) for s in solvers]
        log_stacks_str = " ".join(log_stacks)
        return self._mod_stack(log_stacks_str, is_deploy, "the log group for each solver.")

    # Convenience deploy methods
    def deploy_vpc(self) -> int:
        return self.mod_vpc(True)

    def deploy_ecr_repo(self) -> int:
        return self.mod_ecr_repo(True)

    def deploy_s3(self) -> int:
        return self.mod_s3(True)

    def deploy_all(self) -> int:
        return self.mod_all(True)

    def deploy_solvers(self, solvers: List[str]) -> int:
        return self.mod_solvers(solvers, True)

    def deploy_logs(self, solvers: List[str]) -> int:
        return self.mod_logs(solvers, True)

    # Convenience destroy methods
    def destroy_vpc(self) -> int:
        return self.mod_vpc(False)

    def destroy_ecr_repo(self) -> int:
        return self.mod_ecr_repo(False)

    def destroy_s3(self) -> int:
        return self.mod_s3(False)

    def destroy_all(self) -> int:
        return self.mod_all(False)

    def destroy_solvers(self, solvers: List[str]) -> int:
        return self.mod_solvers(solvers, False)

    def destroy_logs(self, solvers: List[str]) -> int:
        return self.mod_logs(solvers, False)
