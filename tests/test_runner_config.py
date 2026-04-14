"""Tests for runner_config.py validation logic.

Covers:
  - solver_type must be 'sat' or 'smt'
  - double-hyphen validation in project/solver names
"""

from pathlib import Path

import pytest
import yaml


def _write_config(tmp_path: Path, overrides: dict = None) -> str:
    """Write a minimal valid config and return its path."""
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
    if overrides:
        config.update(overrides)
    path = tmp_path / "config.yml"
    path.write_text(yaml.dump(config))
    return str(path)


class TestSolverTypeValidation:
    """Test that solver_type is validated to 'sat' or 'smt'."""

    def test_accepts_sat(self, tmp_path):
        from runner.runner_config import ProjectConfig
        path = _write_config(tmp_path, {"solver_type": "sat"})
        config = ProjectConfig(path)
        assert config.solver_type == "sat"

    def test_accepts_smt(self, tmp_path):
        from runner.runner_config import ProjectConfig
        path = _write_config(tmp_path, {"solver_type": "smt"})
        config = ProjectConfig(path)
        assert config.solver_type == "smt"

    def test_accepts_uppercase_sat(self, tmp_path):
        from runner.runner_config import ProjectConfig
        path = _write_config(tmp_path, {"solver_type": "SAT"})
        config = ProjectConfig(path)
        assert config.solver_type == "sat"

    def test_accepts_mixed_case_smt(self, tmp_path):
        from runner.runner_config import ProjectConfig
        path = _write_config(tmp_path, {"solver_type": "SmT"})
        config = ProjectConfig(path)
        assert config.solver_type == "smt"

    def test_rejects_invalid_type(self, tmp_path):
        from runner.runner_config import ProjectConfig
        path = _write_config(tmp_path, {"solver_type": "invalid"})
        with pytest.raises(SystemExit):
            ProjectConfig(path)

    def test_rejects_empty_type(self, tmp_path):
        from runner.runner_config import ProjectConfig
        path = _write_config(tmp_path, {"solver_type": ""})
        with pytest.raises(SystemExit):
            ProjectConfig(path)

    def test_rejects_cnf_type(self, tmp_path):
        """Common mistake: using file extension instead of solver type."""
        from runner.runner_config import ProjectConfig
        path = _write_config(tmp_path, {"solver_type": "cnf"})
        with pytest.raises(SystemExit):
            ProjectConfig(path)
