"""Handles CLI argument parsing for `satcomp.py`."""

import argparse
import os
import sys
from enum import Enum

import common.pathing as pathing
from common.resource_namer import ResourceNamer
from utils import Tabular

################################################################################

# CC: I couldn't figure out how to write an abstract @dataclass class that
#     implemented `Enum` to cut down on duplication in the way I wanted.
#     Hence why `LsSubcommand`, etc. classes have duplicated functions.
#     For more information, see
#     https://stackoverflow.com/questions/33679930/how-to-extend-python-enum


class Subcommand:
    def __init__(self, name: str, parent_command: str, header: str, help_message: str):
        self.name = name
        self.parent_command = parent_command
        self.header = header
        self.help_message = help_message

    @staticmethod
    def help_subcommand_for(parent_command: str) -> "Subcommand":
        return Subcommand(
            "help",
            parent_command,
            f"List the supported `{parent_command}` sub-commands.",
            "Prints this help message and exits.",
        )

    def __str__(self) -> str:
        return self.name

    def value(self) -> str:
        return str(self)

    def get_header(self) -> str:
        return f"{self.parent_command} {self.name}: {self.header}"

    @staticmethod
    def get_help_table(cmds: list["Subcommand"]) -> Tabular:
        table = Tabular(2, max_column_length=None)

        # Scan for the help command
        for cmd in cmds:
            if cmd.name == "help":
                table.add_row(cmd.get_header())
                break

        for cmd in cmds:
            table.add_row([f"  {cmd.name}", cmd.help_message])

        return table

    @staticmethod
    def print_help_table_and_exit(cmds: list["Subcommand"]):
        table = Subcommand.get_help_table(cmds)
        table.print()
        print("")
        exit(0)


class LsSubcommand(Enum):
    SOLVERS = Subcommand(
        "solvers",
        "ls",
        "List the solvers managed by the config file.",
        "Print solvers in the current config file. (Default)",
    )
    SQS = Subcommand(
        "sqs", "ls", "List information about the job queues.", "Print how many messages are in the job queues."
    )
    ECR = Subcommand("ecr", "ls", "List the Docker images uploaded to the ECR repo.", "Print pushed ECR images.")
    ECS = Subcommand(
        "ecs", "ls", "List the status of services and clusters in ECS.", "Print ECS clusters and services."
    )
    RESOURCES = Subcommand(
        "resources",
        "ls",
        "List all tagged resources using resource tracking.",
        "Print all AWS resources tracked by the resource inventory system.",
    )
    HELP = Subcommand.help_subcommand_for("ls")

    def __str__(self) -> str:
        return str(self.value)

    @staticmethod
    def default() -> "LsSubcommand":
        return LsSubcommand.SOLVERS

    @classmethod
    def values(cls) -> list[Subcommand]:
        return [cmd.value for cmd in cls]

    @classmethod
    def str_values(cls) -> list[str]:
        l = [str(s) for s in cls]
        l.sort()
        return l

    @classmethod
    def from_str(cls, s: str):
        s = s.lower()
        for cmd in cls:
            if s == str(cmd):
                return cmd
        raise ValueError(f"No matching subcommand found for string {s}")

    def print_header_message(self):
        print(f"{self.value.get_header()}\n")

    @classmethod
    def print_help_and_exit(cls):
        Subcommand.print_help_table_and_exit(cls.values())


class ProvisionSubcommand(Enum):
    ALL = Subcommand(
        "all", "provision", "Provision all resources to AWS.", "Provision all resources in the CDK stack to AWS. (Default)"
    )
    SOLVERS = Subcommand(
        "solvers",
        "provision",
        "Provision solver-specific resources (including log groups!) to AWS.",
        "Provision solver-specific resources (including log groups!) to AWS.",
    )
    LOGS = Subcommand(
        "logs",
        "provision",
        "Create a log group for each solver listed by `ls`.",
        "Create a log group for each solver listed by `ls`.",
    )
    VPC = Subcommand(
        "vpc", "provision", "Create the shared virtual private cloud.", "Create the shared virtual private cloud."
    )
    ECR = Subcommand(
        "ecr",
        "provision",
        "Create the ECR repository. Docker images get uploaded here.",
        "Create the ECR repository. Docker images get uploaded here.",
    )
    S3 = Subcommand(
        "s3",
        "provision",
        "Create the S3 bucket in which to store solver results.",
        "Create the S3 bucket in which to store solver results.",
    )
    HELP = Subcommand.help_subcommand_for("provision")

    def __str__(self) -> str:
        return str(self.value)

    @staticmethod
    def default():
        return ProvisionSubcommand.ALL

    @classmethod
    def values(cls) -> list[Subcommand]:
        return [cmd.value for cmd in cls]

    @classmethod
    def str_values(cls) -> list[str]:
        l = [str(s) for s in cls]
        l.sort()
        return l

    @classmethod
    def from_str(cls, s: str):
        s = s.lower()
        for cmd in cls:
            if s == str(cmd):
                return cmd
        raise ValueError(f"No matching subcommand found for string {s}")

    def print_header_message(self):
        print(f"{self.value.get_header()}\n")

    @classmethod
    def print_help_and_exit(cls):
        table = Subcommand.get_help_table(cls.values())
        table.add_row("In most cases, `provision` is the correct command.")
        table.add_row("However, instead of using `provision all`, it can be faster")
        table.add_row("to `teardown` a specific resource and then `provision` that same resource later.")
        table.print()
        exit(0)


class TeardownSubcommand(Enum):
    SOLVERS = Subcommand(
        "solvers",
        "teardown",
        "Tear down solver compute-related resources on AWS. Retains logs.",
        "Tear down solver compute-related resources on AWS. (Default)",
    )
    ALL = Subcommand("all", "teardown", "Tear down all solver resources on AWS.", "Tear down all solver resources on AWS.")
    LOGS = Subcommand(
        "logs", "teardown", "Tear down solver log groups on AWS.", "Tear down log groups for each solver listed by `ls`."
    )
    VPC = Subcommand(
        "vpc",
        "teardown",
        "Tear down the virtual private cloud on AWS.",
        "Tear down the shared virtual private cloud on AWS.",
    )
    ECR = Subcommand(
        "ecr",
        "teardown",
        "Tear down the ECR repository where solver images are stored.",
        "Tear down the ECR repo where solver Docker images are stored.",
    )
    S3 = Subcommand(
        "s3",
        "teardown",
        "Tear down the S3 bucket where solver results are stored.",
        "Tear down the S3 bucket where solver results are stored.",
    )
    HELP = Subcommand.help_subcommand_for("teardown")

    def __str__(self) -> str:
        return str(self.value)

    @staticmethod
    def default():
        return TeardownSubcommand.SOLVERS

    @classmethod
    def values(cls) -> list[Subcommand]:
        return [cmd.value for cmd in cls]

    @classmethod
    def str_values(cls) -> list[str]:
        l = [str(s) for s in cls]
        l.sort()
        return l

    @classmethod
    def from_str(cls, s: str):
        s = s.lower()
        for cmd in cls:
            if s == str(cmd):
                return cmd
        raise ValueError(f"No matching subcommand found for string {s}")

    def print_header_message(self):
        print(f"{self.value.get_header()}\n")

    @classmethod
    def print_help_and_exit(cls):
        table = Subcommand.get_help_table(cls.values())
        table.add_row("In most cases, `teardown` is the correct command.")
        table.add_row("")
        table.add_row("Besides the actual EC2 instances (which the `terminate-instances` command stops),")
        table.add_row("the most costly resource is the VPC. We recommend running `teardown vpc`")
        table.add_row("if you intend on not running jobs for a while.")
        table.add_row("You can always re-deploy with `deploy vpc`.")
        table.print()
        exit(0)


################################################################################


class SatCompArgParser:
    docker_cmds = ["ls", "build", "push", "test-local", "acceptance-test"]
    aws_cmds = [
        "push",
        "bootstrap",
        "provision",
        "start-instances",
        "standby-instances",
        "refresh-instances",
        "terminate-instances",
        "ls",
        "submit",
        "collect",
        "purge",
        "teardown",
    ]
    all_cmds = list(set(docker_cmds + aws_cmds))

    def __init__(self):
        # Default values for config.yml, jobs.yml, and CDK
        # We validate the existence of these paths in `parse_args()`
        # We use strings to match the type of input at the CLI (i.e., str and not Path)
        script_dir = pathing.normalize_path(os.path.dirname(__file__))
        project_dir = pathing.normalize_path(script_dir / ".." / "..")
        self.config = "config.yml"
        self.jobs = "jobs.yml"
        self.cdk = project_dir / "cdk_infra"

        self.parser = argparse.ArgumentParser(
            description="Manage solver Docker images, AWS resources, and formula jobs.",
            epilog="Example: ./satcomp.py bootstrap provision build push",
            # Note: this string is multiline on purpose
            usage="satcomp.py [config] [-h] [ls [OPT]] [build [--no-cache]] [push] [test-local [solver]] [acceptance-test [solver]] [bootstrap] [provision [OPT]] [start-instances [n]] [standby-instances [n]] [refresh-instances] [terminate-instances] [submit [path/jobs.yml]] [collect [path/jobs.yml]] [purge] [teardown [OPT]]",
        )

        # Docker options
        dg = self.parser.add_argument_group(
            "Docker options",
            "Build Docker images from a config file and push them to AWS. For fine-grained Docker management, use the Docker CLI directly.",
        )

        dg.add_argument(
            "config",
            nargs="?",
            default=self.config,
            type=str,
            help="Path to the configuration YAML file specifying your solver images.",
        )

        dg.add_argument(
            "--ls",
            nargs="?",
            type=str,
            default=None,
            const=str(LsSubcommand.default()),
            choices=LsSubcommand.str_values(),
            metavar="OPT",
            help="List resources managed by config.yml and by AWS. See `ls help` for more information.",
        )

        dg.add_argument(
            "--build",
            action="store_true",
            help="Build the Docker images. This is required before running the solver or pushing any images.",
        )

        dg.add_argument(
            "--no-cache",
            action="store_true",
            help="Disable Docker layer cache when building images. Use when upstream dependencies (git repos, packages) have changed.",
        )

        dg.add_argument(
            "--push",
            action="store_true",
            help="Push the Docker images to ECR. This is required before running the solver.",
        )

        dg.add_argument(
            "--start-instances",
            nargs="?",
            const=1,
            type=int,
            help="Start running your solvers on AWS. Specify how many copies of your solvers you want.",
        )

        dg.add_argument(
            "--standby-instances",
            nargs="?",
            const=1,
            type=int,
            help="Request/keep underlying EC2 instances, but stop any running solvers.",
        )

        dg.add_argument(
            "--refresh-instances",
            action="store_true",
            help="Cycle running tasks to pick up new ECR images. Standby, wait for drain, then restart.",
        )

        dg.add_argument(
            "--terminate-instances",
            action="store_true",
            help="Terminate any running AWS Docker containers and EC2 instances. Billing stops after this.",
        )

        # TODO: Probably unnecessary / cluttering-up comments

        # dg.add_argument("--rmc", action='store_true',
        #     help="Removes all containers associated with the images in your docker config file.")

        # dg.add_argument("--rmi", action='store_true',
        #     help="Removes all images listed in your docker config file.")

        # dg.add_argument("--rm", action='store_true',
        #     help="Removes everything buildable/runnable in your docker config file.")

        # AWS options
        awsg = self.parser.add_argument_group(
            "AWS options", "Manage your AWS solver infrastructure with these commands."
        )

        awsg.add_argument(
            "--bootstrap",
            action="store_true",
            help="A one-time bootstrap procedure to use AWS CDK to deploy AWS resources.",
        )

        awsg.add_argument(
            "--provision",
            nargs="?",
            type=str,
            default=None,
            const=str(ProvisionSubcommand.default()),
            choices=ProvisionSubcommand.str_values(),
            metavar="OPT",
            help="Provision the CDK stack to AWS. See `provision help` for more information.",
        )

        awsg.add_argument(
            "--teardown",
            nargs="?",
            type=str,
            default=None,
            const=str(TeardownSubcommand.default()),
            choices=TeardownSubcommand.str_values(),
            metavar="OPT",
            help="Tear down provisioned CDK resources. See `teardown help` for more information.",
        )

        # Formula jobs
        jobs_g = self.parser.add_argument_group(
            "Job management", "Submit and process formula jobs with these commands."
        )

        jobs_g.add_argument(
            "--submit", nargs="?", const=self.jobs, type=str, help="Send jobs to a running input queue."
        )

        jobs_g.add_argument(
            "--collect",
            nargs="?",
            const=self.jobs,
            type=str,
            help="Poll for solver results from the queue and collect them.",
        )

        jobs_g.add_argument(
            "--purge",
            action="store_true",
            help="Purge all input queues of messages. Useful with `stop`, if you don't want new solvers to run those jobs.",
        )

        jobs_g.add_argument(
            "--versioned",
            action="store_true",
            help="Create a new numbered results file (results-<project>-<n>.txt) instead of appending to a single file.",
        )

        # Testing
        tg = self.parser.add_argument_group(
            "Testing options", "Run (local) tests on built Docker solver images with these options."
        )

        tg.add_argument(
            "--test-local",
            nargs="?",
            type=str,
            default=None,
            const="",  # Empty string means test all solvers
            metavar="SOLVER",
            help="Run local tests on Docker images. Optionally specify a solver name to test only that solver.",
        )

        tg.add_argument(
            "--jobs-test-local",
            type=str,
            default=None,
            metavar="JOBS_FILE",
            help="Jobs file with test-local settings (formula_dir_test_local, expected_file_test_local).",
        )

        tg.add_argument(
            "--results-dir",
            type=str,
            default=None,
            metavar="DIR",
            help="Directory to write test results (summary.yml and per-formula output files).",
        )

        tg.add_argument(
            "--num-workers",
            type=int,
            default=None,
            metavar="N",
            help="Number of worker containers for distributed local testing. "
            "Defaults to config's num_worker_nodes_per_leader or 2.",
        )

        # Acceptance testing
        atg = self.parser.add_argument_group(
            "Acceptance testing", "Run acceptance tests on built Docker solver images."
        )

        atg.add_argument(
            "--acceptance-test",
            nargs="?",
            type=str,
            default=None,
            const="__all__",
            metavar="SOLVER",
            help="Run acceptance tests. Optionally specify a solver name to test only that solver.",
        )

        atg.add_argument(
            "--acceptance-test-aws",
            action="store_true",
            default=False,
            help="Run acceptance tests in AWS mode instead of local mode.",
        )

        atg.add_argument(
            "--acceptance-test-timeout",
            type=int,
            default=30,
            help="Per-problem timeout in seconds for acceptance tests (default: 30).",
        )

        self.is_using_docker = False
        self.is_using_aws = False

        self.build = False
        self.no_cache = False
        self.push = False
        self.terminate_instances = False
        self.rmi = False
        self.rmc = False
        self.rm = False
        self.test_local = None
        self.test_local_opt = None
        self.jobs_test_local = None
        self.results_dir = None
        self.num_workers = None

        # Acceptance testing attributes
        self.acceptance_test = None
        self.acceptance_test_opt = None
        self.acceptance_test_aws = False
        self.acceptance_test_timeout = 30

        # `start-instances` and `standby-instances` take optional numerical arguments
        self.start_instances = None
        self.start_instances_opt = None
        self.standby_instances = None
        self.standby_instances_opt = None
        self.refresh_instances = False

        self.bootstrap = False
        self.submit = None
        self.collect = None
        self.purge = False
        self.versioned = False

        # `ls`, `provision` and `teardown` have sub-commands
        self.ls = None
        self.ls_opt = None
        self.provision = None
        self.provision_opt = None
        self.teardown = None
        self.teardown_opt = None

    def parse_args(self, argv: list[str] | None = None):
        """
        Parses arguments and validates certain combinations. Stores parsed args in the `self` namespace.
        """

        # To allow reserved command options to appear without dashes "--",
        # we explicitly add them to reserved commands before parsing the CLI arguments
        # This means that other argument values cannot match the reserved commands,
        # but we should almost never run into an issue with this
        argv = argv or sys.argv[1:]
        argv = list(map(lambda x: "--" + x if x in SatCompArgParser.all_cmds else x, argv))

        self.parser.parse_args(argv, namespace=self)
        p = vars(self)

        # Note: argparse converts hyphens to underscores in argument names
        # Check if any command is specified. Boolean flags are True/False, optional args are None/string.
        # We need to handle empty strings (from test-local with const='') as truthy.
        def is_cmd_specified(cmd_name):
            val = p[cmd_name.replace("-", "_")]
            if isinstance(val, bool):
                return val
            return val is not None

        self.is_using_docker = any(is_cmd_specified(cmd) for cmd in SatCompArgParser.docker_cmds)
        self.is_using_aws = any(is_cmd_specified(cmd) for cmd in SatCompArgParser.aws_cmds)

        if not self.is_using_docker and not self.is_using_aws:
            self.parser.print_usage()
            exit(0)

        # Check for the existence of the config file and the CDK project directory
        self.config = pathing.normalize_path(self.config)
        self.cdk = pathing.normalize_path(self.cdk)
        pathing.check_path_is_readable_file(self.config, self.parser)
        pathing.check_path_is_dir(self.cdk, self.parser)

        # Can specify at most one Docker removal command
        # If removal is specified, shouldn't be building, pushing, or running
        removal_commands = ["rmc", "rmi", "rm"]
        other_docker_commands = ["build", "push", "start-instances", "refresh-instances", "terminate-instances"]
        has_removal = any(is_cmd_specified(cmd) for cmd in removal_commands)
        has_other_docker = any(is_cmd_specified(cmd) for cmd in other_docker_commands)

        if has_removal and has_other_docker:
            self.parser.error(f"Cannot specify a Docker removal command along with {other_docker_commands}")

        # If `rmi` or `rmc` is specified, can't specify `rm`
        if (p["rmi"] or p["rmc"]) and p["rm"]:
            self.parser.error("Cannot specify `rm` along with `rmi` or `rmc`")

        if self.no_cache and not self.build:
            self.parser.error("`--no-cache` can only be used with `build`")

        # Can't `teardown` along with any other "active" AWS commands
        if is_cmd_specified("teardown"):
            for cmd in self.aws_cmds:
                if cmd != "teardown" and is_cmd_specified(cmd):
                    self.parser.error(f"Cannot specify `{cmd}` and `teardown` at the same time.")

        self.validate_and_set_jobs_opts()

        # Only one instance lifecycle command at a time
        instance_cmds = []
        if self.start_instances is not None:
            instance_cmds.append("start-instances")
        if self.standby_instances is not None:
            instance_cmds.append("standby-instances")
        if self.refresh_instances:
            instance_cmds.append("refresh-instances")
        if self.terminate_instances:
            instance_cmds.append("terminate-instances")
        if len(instance_cmds) > 1:
            self.parser.error(f"Cannot specify multiple instance commands at the same time: {', '.join(instance_cmds)}")

        self.start_instances_opt = self.start_instances
        self.start_instances = self.start_instances is not None
        self.validate_startlike_opt(self.start_instances_opt, "start-instances")

        self.standby_instances_opt = self.standby_instances
        self.standby_instances = self.standby_instances is not None
        self.validate_startlike_opt(self.standby_instances_opt, "standby-instances")

        # Check `ls` sub-command. If `help` requested, print and exit
        self.ls_opt = None if self.ls is None else LsSubcommand.from_str(self.ls)
        self.ls = self.ls is not None
        if self.ls_opt == LsSubcommand.HELP:
            LsSubcommand.print_help_and_exit()

        # Check `provision` sub-command. If `help` requested, print and exit
        self.provision_opt = None if self.provision is None else ProvisionSubcommand.from_str(self.provision)
        self.provision = self.provision is not None
        if self.provision_opt == ProvisionSubcommand.HELP:
            ProvisionSubcommand.print_help_and_exit()

        # Check `teardown` sub-command. If `help` requested, print and exit
        self.teardown_opt = None if self.teardown is None else TeardownSubcommand.from_str(self.teardown)
        self.teardown = self.teardown is not None
        if self.teardown_opt == TeardownSubcommand.HELP:
            TeardownSubcommand.print_help_and_exit()

        # Check `test-local` option (stores optional solver name)
        # Note: argparse converts hyphens to underscores
        self.test_local_opt = self.test_local if self.test_local else None
        self.test_local = self.test_local is not None

        # Validate test-local related options
        if self.jobs_test_local is not None:
            self.jobs_test_local = pathing.normalize_path(self.jobs_test_local)
            if not self.jobs_test_local.is_file():
                self.parser.error(f'Jobs file for test-local "{self.jobs_test_local}" does not exist or is not a file')

        if self.results_dir is not None:
            self.results_dir = pathing.normalize_path(self.results_dir)

        # Validate --num-workers
        if self.num_workers is not None and self.num_workers <= 0:
            self.parser.error("`--num-workers` must be a positive integer.")

        # Check `--acceptance-test` acceptance testing option
        self.acceptance_test_opt = (
            self.acceptance_test if (self.acceptance_test and self.acceptance_test != "__all__") else None
        )
        self.acceptance_test = self.acceptance_test is not None

        # Validate acceptance testing options
        if self.acceptance_test_aws and not self.acceptance_test:
            self.parser.error("`--acceptance-test-aws` requires `--acceptance-test` to be specified.")

        if self.acceptance_test and self.acceptance_test_timeout <= 0:
            self.parser.error("`--acceptance-test-timeout` must be a positive integer.")

    def validate_startlike_opt(self, start_opt: int, opt_str: str):
        if start_opt is not None:
            if start_opt <= 0:
                self.parser.error(f"The `{opt_str}` argument must be a positive integer.")
            elif start_opt > ResourceNamer.ASG_MAX_CAPACITY:
                self.parser.error(
                    f"The `{opt_str}` argument cannot be greater "
                    f"than ASG_MAX_CAPCITY = {ResourceNamer.ASG_MAX_CAPACITY}."
                )

    def validate_and_set_jobs_opts(self):
        # Bug: user can provide default `jobs.yml`, but then specify a different jobs file
        # This will cause the different jobs file to overwrite the default one
        # Possible fix: make the default value store something other than `None`? Magic number value?

        # User-provided paths are resolved based on the CWD
        CWD = pathing.normalize_path(os.getcwd())
        default_jf = pathing.normalize_path(self.jobs, relative_to=CWD)
        jf = default_jf
        jobs_opts = [self.submit, self.collect]
        for job in jobs_opts:
            if job is not None:
                norm_jf = pathing.normalize_path(job)
                if norm_jf == default_jf:
                    continue
                # A non-default value overwrites a stored default value
                elif jf == default_jf:
                    jf = norm_jf
                # We have an error if two non-default job files disagree
                elif jf != norm_jf:
                    self.parser.error("The jobs files for `submit` and `process` must all be the same.")

        self.submit = self.submit is not None
        self.collect = self.collect is not None

        # If any option is specified, validate the jobs file path
        if self.submit or self.collect:
            if not jf.is_file() or not jf.exists():
                self.parser.error(f'Job file "{str(jf)}" either doesn\'t exist or is not a file')

        self.jobs = str(jf)
