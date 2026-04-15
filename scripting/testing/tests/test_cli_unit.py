"""Unit tests for CLI --acceptance-test, --acceptance-test-aws, --acceptance-test-timeout flags."""

# We need a valid config file for the parser. Use config-test.yml from examples/configs.
import os
from pathlib import Path

import pytest
from runner.runner_cli import SatCompArgParser

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_PATH = str(PROJECT_ROOT / "examples" / "configs" / "config-test.yml")


def _parse(args):
    """Helper: create a parser and parse the given args list."""
    parser = SatCompArgParser()
    parser.parse_args(args)
    return parser


class TestAcceptanceTestFlag:
    """Verify --acceptance-test flag behavior."""

    def test_acceptance_test_alone_sets_local_mode(self):
        p = _parse([CONFIG_PATH, "--acceptance-test"])
        assert p.acceptance_test is True
        assert p.acceptance_test_aws is False
        assert p.acceptance_test_opt is None  # __all__ → None (test all solvers)

    def test_acceptance_test_with_solver_name(self):
        p = _parse([CONFIG_PATH, "--acceptance-test", "mock-solver"])
        assert p.acceptance_test is True
        assert p.acceptance_test_opt == "mock-solver"

    def test_acceptance_test_with_aws_sets_aws_mode(self):
        p = _parse([CONFIG_PATH, "--acceptance-test", "--acceptance-test-aws"])
        assert p.acceptance_test is True
        assert p.acceptance_test_aws is True


class TestAcceptanceTestTimeout:
    """Verify --acceptance-test-timeout flag behavior."""

    def test_default_timeout_is_30(self):
        p = _parse([CONFIG_PATH, "--acceptance-test"])
        assert p.acceptance_test_timeout == 30

    def test_custom_timeout(self):
        p = _parse([CONFIG_PATH, "--acceptance-test", "--acceptance-test-timeout", "60"])
        assert p.acceptance_test_timeout == 60

    def test_non_positive_timeout_produces_error(self):
        with pytest.raises(SystemExit):
            _parse([CONFIG_PATH, "--acceptance-test", "--acceptance-test-timeout", "0"])

    def test_negative_timeout_produces_error(self):
        with pytest.raises(SystemExit):
            _parse([CONFIG_PATH, "--acceptance-test", "--acceptance-test-timeout", "-5"])


class TestAcceptanceTestAwsRequiresTest:
    """Verify --acceptance-test-aws requires --acceptance-test."""

    def test_acceptance_test_aws_without_test_produces_error(self):
        with pytest.raises(SystemExit):
            _parse([CONFIG_PATH, "--acceptance-test-aws"])
