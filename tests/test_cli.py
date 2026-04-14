"""Tests for CLI argument parsing in runner_cli.py.

Tests cover:
  - Subcommand enum parsing (ls, deploy, destroy)
  - Command conflict detection
  - Enum utilities (from_str, str_values)

Note: Full CLI integration tests require valid config files and are
complex to set up. These tests focus on the parsing logic that can
be tested in isolation.
"""

import pytest

from runner.runner_cli import (
    SatCompArgParser,
    LsSubcommand,
    ProvisionSubcommand,
    TeardownSubcommand,
    Subcommand,
)


# ---------------------------------------------------------------------------
# Subcommand enum tests
# ---------------------------------------------------------------------------

class TestLsSubcommandEnum:
    """Test LsSubcommand enum parsing and utilities."""

    def test_from_str_solvers(self):
        assert LsSubcommand.from_str("solvers") == LsSubcommand.SOLVERS

    def test_from_str_sqs(self):
        assert LsSubcommand.from_str("sqs") == LsSubcommand.SQS

    def test_from_str_ecr(self):
        assert LsSubcommand.from_str("ecr") == LsSubcommand.ECR

    def test_from_str_ecs(self):
        assert LsSubcommand.from_str("ecs") == LsSubcommand.ECS

    def test_from_str_resources(self):
        assert LsSubcommand.from_str("resources") == LsSubcommand.RESOURCES

    def test_from_str_case_insensitive(self):
        assert LsSubcommand.from_str("SOLVERS") == LsSubcommand.SOLVERS
        assert LsSubcommand.from_str("SqS") == LsSubcommand.SQS

    def test_from_str_invalid_raises(self):
        with pytest.raises(ValueError):
            LsSubcommand.from_str("invalid")

    def test_default_is_solvers(self):
        assert LsSubcommand.default() == LsSubcommand.SOLVERS

    def test_str_values_are_sorted(self):
        values = LsSubcommand.str_values()
        assert values == sorted(values)

    def test_str_conversion(self):
        assert str(LsSubcommand.SOLVERS) == "solvers"
        assert str(LsSubcommand.SQS) == "sqs"


class TestProvisionSubcommandEnum:
    """Test ProvisionSubcommand enum parsing and utilities."""

    def test_from_str_all(self):
        assert ProvisionSubcommand.from_str("all") == ProvisionSubcommand.ALL

    def test_from_str_solvers(self):
        assert ProvisionSubcommand.from_str("solvers") == ProvisionSubcommand.SOLVERS

    def test_from_str_logs(self):
        assert ProvisionSubcommand.from_str("logs") == ProvisionSubcommand.LOGS

    def test_from_str_vpc(self):
        assert ProvisionSubcommand.from_str("vpc") == ProvisionSubcommand.VPC

    def test_from_str_ecr(self):
        assert ProvisionSubcommand.from_str("ecr") == ProvisionSubcommand.ECR

    def test_from_str_s3(self):
        assert ProvisionSubcommand.from_str("s3") == ProvisionSubcommand.S3

    def test_from_str_case_insensitive(self):
        assert ProvisionSubcommand.from_str("ALL") == ProvisionSubcommand.ALL
        assert ProvisionSubcommand.from_str("Vpc") == ProvisionSubcommand.VPC

    def test_from_str_invalid_raises(self):
        with pytest.raises(ValueError):
            ProvisionSubcommand.from_str("invalid")

    def test_default_is_all(self):
        assert ProvisionSubcommand.default() == ProvisionSubcommand.ALL

    def test_str_values_are_sorted(self):
        values = ProvisionSubcommand.str_values()
        assert values == sorted(values)


class TestTeardownSubcommandEnum:
    """Test TeardownSubcommand enum parsing and utilities."""

    def test_from_str_all(self):
        assert TeardownSubcommand.from_str("all") == TeardownSubcommand.ALL

    def test_from_str_solvers(self):
        assert TeardownSubcommand.from_str("solvers") == TeardownSubcommand.SOLVERS

    def test_from_str_logs(self):
        assert TeardownSubcommand.from_str("logs") == TeardownSubcommand.LOGS

    def test_from_str_vpc(self):
        assert TeardownSubcommand.from_str("vpc") == TeardownSubcommand.VPC

    def test_from_str_ecr(self):
        assert TeardownSubcommand.from_str("ecr") == TeardownSubcommand.ECR

    def test_from_str_s3(self):
        assert TeardownSubcommand.from_str("s3") == TeardownSubcommand.S3

    def test_from_str_case_insensitive(self):
        assert TeardownSubcommand.from_str("ALL") == TeardownSubcommand.ALL

    def test_from_str_invalid_raises(self):
        with pytest.raises(ValueError):
            TeardownSubcommand.from_str("invalid")

    def test_default_is_solvers(self):
        assert TeardownSubcommand.default() == TeardownSubcommand.SOLVERS


# ---------------------------------------------------------------------------
# Subcommand class tests
# ---------------------------------------------------------------------------

class TestSubcommandClass:
    """Test Subcommand base class."""

    def test_str_conversion(self):
        cmd = Subcommand("test", "parent", "Test header", "Test help")
        assert str(cmd) == "test"

    def test_value(self):
        cmd = Subcommand("test", "parent", "Test header", "Test help")
        assert cmd.value() == "test"

    def test_get_header(self):
        cmd = Subcommand("test", "parent", "Test header", "Test help")
        assert cmd.get_header() == "parent test: Test header"

    def test_help_subcommand_for(self):
        cmd = Subcommand.help_subcommand_for("mycommand")
        assert cmd.name == "help"
        assert cmd.parent_command == "mycommand"
        assert "mycommand" in cmd.header


# ---------------------------------------------------------------------------
# Parser initialization tests
# ---------------------------------------------------------------------------

class TestParserInitialization:
    """Test SatCompArgParser initialization."""

    def test_default_values(self):
        parser = SatCompArgParser()
        assert parser.build is False
        assert parser.push is False
        assert parser.terminate_instances is False
        assert parser.bootstrap is False
        assert parser.start_instances is None
        assert parser.ls is None
        assert parser.provision is None
        assert parser.teardown is None

    def test_docker_cmds_defined(self):
        assert "build" in SatCompArgParser.docker_cmds
        assert "push" in SatCompArgParser.docker_cmds
        assert "ls" in SatCompArgParser.docker_cmds

    def test_aws_cmds_defined(self):
        assert "provision" in SatCompArgParser.aws_cmds
        assert "teardown" in SatCompArgParser.aws_cmds
        assert "start-instances" in SatCompArgParser.aws_cmds
        assert "terminate-instances" in SatCompArgParser.aws_cmds
        assert "bootstrap" in SatCompArgParser.aws_cmds

    def test_all_cmds_is_union(self):
        all_cmds = set(SatCompArgParser.all_cmds)
        docker_cmds = set(SatCompArgParser.docker_cmds)
        aws_cmds = set(SatCompArgParser.aws_cmds)
        assert all_cmds == docker_cmds.union(aws_cmds)


# ---------------------------------------------------------------------------
# Command list tests
# ---------------------------------------------------------------------------

class TestCommandLists:
    """Test that command lists are consistent."""

    def test_no_duplicate_docker_cmds(self):
        cmds = SatCompArgParser.docker_cmds
        assert len(cmds) == len(set(cmds))

    def test_no_duplicate_aws_cmds(self):
        cmds = SatCompArgParser.aws_cmds
        assert len(cmds) == len(set(cmds))

    def test_ls_in_both_docker_and_aws(self):
        # ls is in both because it can list local Docker images or AWS resources
        assert "ls" in SatCompArgParser.docker_cmds
        assert "ls" in SatCompArgParser.aws_cmds

    def test_push_in_both_docker_and_aws(self):
        # push involves both Docker and AWS ECR
        assert "push" in SatCompArgParser.docker_cmds
        assert "push" in SatCompArgParser.aws_cmds


# ---------------------------------------------------------------------------
# CLI integration tests with config files
# ---------------------------------------------------------------------------

import yaml
from pathlib import Path


def _create_test_config(tmp_path: Path) -> Path:
    """Create a minimal valid config.yml for CLI testing."""
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
        "solvers": [],
    }
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.dump(config))
    return config_path


def _create_test_jobs(tmp_path: Path) -> Path:
    """Create a minimal valid jobs.yml for CLI testing."""
    jobs = {
        "results_dir": str(tmp_path / "results"),
        "formulas": [],
        "job_options": {"timeout_secs": 10, "solver_options": []},
    }
    jobs_path = tmp_path / "jobs.yml"
    jobs_path.write_text(yaml.dump(jobs))
    return jobs_path


def _create_cdk_dir(tmp_path: Path) -> Path:
    """Create a mock cdk_infra directory."""
    cdk_path = tmp_path / "cdk_infra"
    cdk_path.mkdir()
    return cdk_path


class TestCliIntegration:
    """Integration tests for CLI with actual config files."""

    def test_parse_build_command(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        parser.parse_args([str(config_path), "build"])

        assert parser.build is True
        assert parser.is_using_docker is True

    def test_parse_ls_command(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        parser.parse_args([str(config_path), "ls"])

        assert parser.ls is True
        assert parser.ls_opt == LsSubcommand.SOLVERS

    def test_parse_ls_with_subcommand(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        parser.parse_args([str(config_path), "ls", "ecr"])

        assert parser.ls is True
        assert parser.ls_opt == LsSubcommand.ECR

    def test_parse_deploy_command(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        parser.parse_args([str(config_path), "provision"])

        assert parser.provision is True
        assert parser.provision_opt == ProvisionSubcommand.ALL

    def test_parse_deploy_vpc(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        parser.parse_args([str(config_path), "provision", "vpc"])

        assert parser.provision is True
        assert parser.provision_opt == ProvisionSubcommand.VPC

    def test_parse_destroy_command(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        parser.parse_args([str(config_path), "teardown"])

        assert parser.teardown is True
        assert parser.teardown_opt == TeardownSubcommand.SOLVERS

    def test_parse_start_with_count(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        parser.parse_args([str(config_path), "start-instances", "3"])

        assert parser.start_instances is True
        assert parser.start_instances_opt == 3

    def test_parse_multiple_commands(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        parser.parse_args([str(config_path), "build", "push"])

        assert parser.build is True
        assert parser.push is True

    def test_parse_bootstrap_deploy_start(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        parser.parse_args([str(config_path), "bootstrap", "provision", "start-instances"])

        assert parser.bootstrap is True
        assert parser.provision is True
        assert parser.start_instances is True

    def test_parse_submit_with_jobs_file(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        jobs_path = _create_test_jobs(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        # Pass jobs file explicitly as argument
        parser.parse_args([str(config_path), "submit", str(jobs_path)])

        assert parser.submit is True

    def test_parse_process_with_jobs_file(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        jobs_path = _create_test_jobs(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path
        # Pass jobs file explicitly as argument
        parser.parse_args([str(config_path), "collect", str(jobs_path)])

        assert parser.collect is True


class TestCliValidationErrors:
    """Test CLI validation error handling."""

    def test_missing_config_file_exits(self, tmp_path):
        cdk_path = _create_cdk_dir(tmp_path)
        nonexistent = tmp_path / "nonexistent.yml"

        parser = SatCompArgParser()
        parser.cdk = cdk_path

        with pytest.raises(SystemExit):
            parser.parse_args([str(nonexistent), "build"])

    def test_missing_cdk_dir_exits(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        nonexistent_cdk = tmp_path / "nonexistent_cdk"

        parser = SatCompArgParser()
        parser.cdk = nonexistent_cdk

        with pytest.raises(SystemExit):
            parser.parse_args([str(config_path), "build"])

    def test_destroy_with_other_command_exits(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path

        with pytest.raises(SystemExit):
            parser.parse_args([str(config_path), "teardown", "provision"])

    def test_start_and_standby_together_exits(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path

        with pytest.raises(SystemExit):
            parser.parse_args([str(config_path), "start-instances", "standby-instances"])

    def test_start_zero_exits(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path

        with pytest.raises(SystemExit):
            parser.parse_args([str(config_path), "start-instances", "0"])

    def test_start_negative_exits(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path

        with pytest.raises(SystemExit):
            parser.parse_args([str(config_path), "start-instances", "-1"])

    def test_no_commands_exits(self, tmp_path):
        config_path = _create_test_config(tmp_path)
        cdk_path = _create_cdk_dir(tmp_path)

        parser = SatCompArgParser()
        parser.cdk = cdk_path

        with pytest.raises(SystemExit):
            parser.parse_args([str(config_path)])
