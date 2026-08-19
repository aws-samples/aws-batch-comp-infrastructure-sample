#!/usr/bin/env python3

import os
import sys
from pathlib import Path

# Check that `source venv.sh` has been run, by examining the PYTHONPATH
# If it isn't there, tell the user to go source the file
SCRIPT_DIR = os.path.normpath(os.path.dirname(__file__))
SCRIPTING_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "scripting"))
if os.environ.get("PYTHONPATH") is None or SCRIPTING_DIR not in os.environ["PYTHONPATH"]:
    print("Error: You must run `source satcomp-activate.sh` before using this project.", file=sys.stderr)
    exit(1)

import json
import subprocess

import boto3
from boto3 import Session
from botocore.exceptions import NoCredentialsError, ProfileNotFound
from common import LoggingManager, ResourceNamer
from common.constants import NODE_MINIMUM_VERSION, NODE_SUPPORTED_VERSIONS
from harness.aws_shim import STS
from runner.commands import (
    BootstrapCommand,
    BuildCommand,
    CommandContext,
    DeployCommand,
    DestroyCommand,
    LsCommand,
    ProcessCommand,
    PurgeCommand,
    PushCommand,
    RefreshCommand,
    StandbyCommand,
    StartCommand,
    StopCommand,
    SubmitCommand,
    TestLocalCommand,
)
from runner.runner_cli import SatCompArgParser
from runner.runner_config import ProjectConfig
from runner.runner_docker import SolverDockerClient
from runner.runner_jobs import SolverJobManager
from testing.test_runner import AcceptanceTestRunner

################################################################################

RUNNER_LOGGER_NAME = "runner"

lm = LoggingManager()
logger = lm.get_logger(RUNNER_LOGGER_NAME, formatted=False)


################################################################################


def check_node_version():
    """Check the system's `node` version, to suppress the !!! node warning."""
    proc = subprocess.run(
        ["node", "--version"],
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        logger.error("Error: You don't seem to have `node` installed.")
        logger.error("Double-check that you have it installed, and that `node --version` returns something.")
        exit(1)
    else:
        version = proc.stdout.strip()[1:]
        version_parts = version.split(".")
        major_version = int(version_parts[0])
        if major_version < NODE_MINIMUM_VERSION:
            logger.error(
                f"Error: Active node version {version} is less than required node version ^{NODE_MINIMUM_VERSION}.0.0."
            )
            exit(1)
        elif major_version not in NODE_SUPPORTED_VERSIONS:
            supported_str = " and ".join(f"^{v}.0.0" for v in NODE_SUPPORTED_VERSIONS)
            logger.debug(
                f"Warning: Active node version {version}" f" is not one of the supported versions {supported_str}."
            )


def create_boto3_session(project: ProjectConfig) -> Session:
    """Create a boto3 session from the project config."""
    profile = project.profile
    env_profile = os.environ.get("AWS_PROFILE")
    if env_profile and env_profile != profile:
        logger.error(
            f'Error: AWS_PROFILE environment variable ("{env_profile}") does not match '
            f'the profile in your config file ("{profile}").'
        )
        logger.error("Either update your config file, or set AWS_PROFILE to match.")
        exit(1)
    try:
        session = boto3.Session(region_name=project.region, profile_name=profile)
        return session
    except ProfileNotFound:
        logger.error(
            f'Error: The AWS profile named "{profile}"' " could not be found in ~/.aws/credentials or ~/.aws/config."
        )
        logger.error("Double-check that this profile exists," " or edit the `profile` field of your config file.")
        exit(1)


def write_cdk_solver_list(sdc: SolverDockerClient, cdk_dir: Path):
    """Write solver configuration to solvers.json for CDK."""
    s_file = cdk_dir / "solvers.json"
    s_dict = {
        "project": sdc.project.project,
        "region": sdc.project.region,
        "solvers": [sc.cdk_solver.to_dict() for sc in sdc.project.aws_solvers],
    }

    should_write = True
    if os.path.exists(s_file) and os.path.isfile(s_file):
        with open(s_file, "r") as f:
            existing_dict = json.load(f)

        if s_dict == existing_dict:
            should_write = False

    if should_write:
        s = json.dumps(s_dict, indent=2)
        with open(s_file, "w") as f:
            f.write(s)


def get_account_id(boto3_session: Session) -> str:
    """Get the AWS account ID from the session."""
    if os.environ.get("AWS_ACCOUNT_ID") is not None:
        account = os.environ["AWS_ACCOUNT_ID"]
        logger.debug(f"AWS account (cached): {account}")
        return account

    logger.debug("Fetching AWS account id...")
    sts = STS.get_sts_from_session(boto3_session)
    try:
        account = sts.get_account_id()
    except NoCredentialsError:
        logger.error("Error: No AWS credentials found. Try running `aws configure`.")
        exit(1)
    logger.debug(f"AWS account: {account}      (Consider running `export AWS_ACCOUNT_ID={account}`)")
    return account


################################################################################

if __name__ == "__main__":
    parser = SatCompArgParser()
    parser.parse_args()

    project = ProjectConfig(parser.config)
    sdc = SolverDockerClient(project)

    # Create command context
    ctx = CommandContext(
        project=project,
        sdc=sdc,
        cdk_path=parser.cdk,
    )

    if parser.is_using_aws:
        # Emit a warning or complain if the config file only contains one solver
        if len(ctx.solvers) == 1 and not parser.ls and not parser.bootstrap:
            logger.warning(f"Warning: Your config file doesn't contain any solvers.")
            logger.warning(f"Do you have a different config file, or have you forgotten to add your solver?")

        check_node_version()
        ctx.boto3_session = create_boto3_session(project)
        write_cdk_solver_list(sdc, parser.cdk)
        ctx.account = get_account_id(ctx.boto3_session)
        ctx.rn = ResourceNamer(project.project, ctx.account, project.region)

    # Handle the commands in dependency order
    # e.g., we have to `bootstrap` before we `deploy` before we `push`

    if parser.ls:
        result = LsCommand(ctx).execute(opt=parser.ls_opt)
        if result != 0:
            exit(result)

    if parser.bootstrap:
        result = BootstrapCommand(ctx).execute()
        if result != 0:
            exit(result)

    if parser.provision:
        result = DeployCommand(ctx).execute(opt=parser.provision_opt)
        if result != 0:
            exit(result)

    if parser.build:
        result = BuildCommand(ctx).execute(no_cache=parser.no_cache)
        if result != 0:
            exit(result)

    if parser.test_local:
        # Create job manager if jobs file is provided for test-local
        job_manager = None
        if parser.jobs_test_local:
            job_manager = SolverJobManager(str(parser.jobs_test_local))
        result = TestLocalCommand(ctx, job_manager=job_manager, num_workers=parser.num_workers).execute(
            solver_name=parser.test_local_opt,
            results_dir=parser.results_dir,
        )
        if result != 0:
            exit(result)

    if parser.acceptance_test:
        # Acceptance testing
        solver_names = [parser.acceptance_test_opt] if parser.acceptance_test_opt else None
        runner_kwargs = dict(
            project=project,
            solver_names=solver_names,
            timeout_secs=parser.acceptance_test_timeout,
            aws_mode=parser.acceptance_test_aws,
        )
        if parser.acceptance_test_aws:
            if not ctx.boto3_session:
                ctx.boto3_session = create_boto3_session(project)
                ctx.account = get_account_id(ctx.boto3_session)
            runner_kwargs["boto3_session"] = ctx.boto3_session
            runner_kwargs["account_id"] = ctx.account
        runner = AcceptanceTestRunner(**runner_kwargs)
        report = runner.run()
        sys.exit(report.get_exit_code())

    if parser.push:
        result = PushCommand(ctx).execute()
        if result != 0:
            exit(result)

    if parser.start_instances:
        result = StartCommand(ctx).execute(num_copies=parser.start_instances_opt)
        if result != 0:
            exit(result)
    elif parser.refresh_instances:
        result = RefreshCommand(ctx).execute()
        if result != 0:
            exit(result)
    elif parser.standby_instances:
        result = StandbyCommand(ctx).execute(num_copies=parser.standby_instances_opt)
        if result != 0:
            exit(result)
    elif parser.terminate_instances:
        result = StopCommand(ctx).execute()
        if result != 0:
            exit(result)

    # Job commands share a job manager instance
    if parser.submit or parser.collect:
        jm = SolverJobManager(parser.jobs)

        if parser.submit:
            result = SubmitCommand(ctx, jm).execute()
            if result != 0:
                exit(result)

        if parser.collect:
            result = ProcessCommand(ctx, jm).execute()
            if result != 0:
                exit(result)

    if parser.purge:
        result = PurgeCommand(ctx).execute()
        if result != 0:
            exit(result)

    if parser.teardown:
        result = DestroyCommand(ctx).execute(opt=parser.teardown_opt)
        if result != 0:
            exit(result)
