"""Unit tests for ResourceNamer and check_no_double_hyphen.

Validates: Requirements 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 3.3, 4.1, 5.1, 6.1, 6.2, 7.2, 7.3
"""

import pytest

from common.resource_namer import ResourceNamer
from runner.runner_config import check_no_double_hyphen


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rn():
    """ResourceNamer with project='satcomp25'."""
    return ResourceNamer(project="satcomp25")


# ---------------------------------------------------------------------------
# Exact output strings for known inputs (project="satcomp25", solver="mallob")
# Validates: Requirements 3.1, 3.2, 4.1, 5.1, 6.1
# ---------------------------------------------------------------------------

class TestKnownOutputs:

    def test_solver_stack_name(self, rn):
        assert rn.get_solver_stack_name("mallob") == "satcomp--solver--satcomp25--mallobStack"

    def test_log_group_stack_name(self, rn):
        assert rn.get_log_group_stack_name("mallob") == "satcomp--loggroup--satcomp25--mallobStack"

    def test_task_def_name_leader(self, rn):
        assert rn.get_task_def_name("mallob", is_leader=True) == "satcomp--taskdef--satcomp25--mallobLeader"

    def test_task_def_name_worker(self, rn):
        assert rn.get_task_def_name("mallob", is_leader=False) == "satcomp--taskdef--satcomp25--mallobWorker"

    def test_container_name(self, rn):
        assert rn.get_container_name("mallob") == "satcomp--container--satcomp25--mallob"

    def test_ecr_image_tag(self, rn):
        assert rn.get_ecr_image_tag("mallob") == "satcomp--image--satcomp25--mallob"


# ---------------------------------------------------------------------------
# Global stack names
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------

class TestGlobalStackNames:

    def test_results_bucket_stack_name(self, rn):
        assert rn.get_results_bucket_stack_name() == "satcomp--s3--satcomp25"

    def test_ecr_repo_stack_name(self, rn):
        assert rn.get_ecr_repo_stack_name() == "satcomp--ecr--satcomp25"

    def test_vpc_stack_name(self, rn):
        assert rn.get_vpc_stack_name() == "satcomp--vpc--satcomp25"


# ---------------------------------------------------------------------------
# get_reserved_stack_names returns the three global stack names
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------

class TestReservedStackNames:

    def test_returns_three_global_names(self, rn):
        reserved = rn.get_reserved_stack_names()
        assert reserved == [
            "satcomp--s3--satcomp25",
            "satcomp--ecr--satcomp25",
            "satcomp--vpc--satcomp25",
        ]

    def test_length(self, rn):
        assert len(rn.get_reserved_stack_names()) == 3


# ---------------------------------------------------------------------------
# Edge cases: solver with single hyphen, single-character project name
# Validates: Requirements 3.1, 5.1, 6.1
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_solver_with_single_hyphen(self, rn):
        assert rn.get_container_name("my-solver") == "satcomp--container--satcomp25--my-solver"
        assert rn.get_ecr_image_tag("my-solver") == "satcomp--image--satcomp25--my-solver"
        assert rn.get_solver_stack_name("my-solver") == "satcomp--solver--satcomp25--my-solverStack"

    def test_single_char_project_name(self):
        rn = ResourceNamer(project="x")
        assert rn.get_results_bucket_stack_name() == "satcomp--s3--x"
        assert rn.get_solver_stack_name("s") == "satcomp--solver--x--sStack"
        assert rn.get_ecr_image_tag("s") == "satcomp--image--x--s"


# ---------------------------------------------------------------------------
# Task definition Leader / Worker suffix
# Validates: Requirements 4.1
# ---------------------------------------------------------------------------

class TestTaskDefSuffix:

    def test_leader_suffix(self, rn):
        name = rn.get_task_def_name("mallob", is_leader=True)
        assert name.endswith("Leader")

    def test_worker_suffix(self, rn):
        name = rn.get_task_def_name("mallob", is_leader=False)
        assert name.endswith("Worker")

    def test_leader_and_worker_differ(self, rn):
        leader = rn.get_task_def_name("mallob", is_leader=True)
        worker = rn.get_task_def_name("mallob", is_leader=False)
        assert leader != worker


# ---------------------------------------------------------------------------
# ECR image tag round-trip and error handling
# Validates: Requirements 6.2, 7.2, 7.3
# ---------------------------------------------------------------------------

class TestEcrImageTagParsing:

    def test_round_trip(self, rn):
        tag = rn.get_ecr_image_tag("mallob")
        assert rn.get_solver_from_ecr_image_tag(tag) == "mallob"

    def test_round_trip_hyphenated_solver(self, rn):
        tag = rn.get_ecr_image_tag("my-solver")
        assert rn.get_solver_from_ecr_image_tag(tag) == "my-solver"

    def test_malformed_tag_raises(self, rn):
        with pytest.raises(ValueError):
            rn.get_solver_from_ecr_image_tag("bad-tag")

    def test_wrong_prefix_raises(self, rn):
        with pytest.raises(ValueError):
            rn.get_solver_from_ecr_image_tag("wrong--image--satcomp25--mallob")

    def test_too_few_segments_raises(self, rn):
        with pytest.raises(ValueError):
            rn.get_solver_from_ecr_image_tag("satcomp--image")


# ---------------------------------------------------------------------------
# Validation: check_no_double_hyphen
# Validates: Requirements 1.1, 1.2, 2.1, 2.2
# ---------------------------------------------------------------------------

class TestCheckNoDoubleHyphen:

    def test_rejects_double_hyphen(self):
        with pytest.raises(SystemExit):
            check_no_double_hyphen("bad--name", "Test")

    def test_accepts_good_name(self):
        # Should not raise
        check_no_double_hyphen("good-name", "Test")

    def test_accepts_no_hyphens(self):
        check_no_double_hyphen("goodname", "Test")

    def test_rejects_double_hyphen_at_start(self):
        with pytest.raises(SystemExit):
            check_no_double_hyphen("--leading", "Test")

    def test_rejects_double_hyphen_at_end(self):
        with pytest.raises(SystemExit):
            check_no_double_hyphen("trailing--", "Test")
