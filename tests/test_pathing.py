"""Tests for common/pathing.py path normalization."""

import os
from pathlib import Path

import pytest

from common import pathing


class TestNormalizePath:
    """Tests for normalize_path function."""

    def test_returns_none_for_none_input(self):
        """Test that None input returns None."""
        assert pathing.normalize_path(None) is None

    def test_expands_user_home(self, tmp_path):
        """Test that ~ is expanded to user home directory."""
        result = pathing.normalize_path("~/test")
        # Check that ~ was expanded (not literal ~) and ends with test
        assert "~" not in str(result)
        assert str(result).endswith("test")

    def test_resolves_relative_path(self, tmp_path):
        """Test that relative paths are resolved to absolute."""
        result = pathing.normalize_path(".")
        assert result.is_absolute()

    def test_relative_to_parameter(self, tmp_path):
        """Test that relative_to parameter affects resolution."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()

        result = pathing.normalize_path("subdir", relative_to=base_dir)
        assert result == base_dir / "subdir"

    def test_absolute_path_ignores_relative_to(self, tmp_path):
        """Test that absolute paths ignore relative_to parameter."""
        absolute_path = "/absolute/path"
        result = pathing.normalize_path(absolute_path, relative_to=tmp_path)
        assert str(result) == absolute_path


class TestEnvironmentVariableExpansion:
    """Tests for environment variable expansion in normalize_path."""

    def test_expands_env_var_dollar_syntax(self, tmp_path, monkeypatch):
        """Test that $VAR syntax is expanded."""
        monkeypatch.setenv("TEST_VAR", str(tmp_path))
        result = pathing.normalize_path("$TEST_VAR/subdir")
        assert result == tmp_path / "subdir"

    def test_expands_env_var_brace_syntax(self, tmp_path, monkeypatch):
        """Test that ${VAR} syntax is expanded."""
        monkeypatch.setenv("TEST_VAR", str(tmp_path))
        result = pathing.normalize_path("${TEST_VAR}/subdir")
        assert result == tmp_path / "subdir"

    def test_expands_satcomp_root(self, tmp_path, monkeypatch):
        """Test that $SATCOMP_ROOT is expanded correctly."""
        monkeypatch.setenv("SATCOMP_ROOT", str(tmp_path))
        result = pathing.normalize_path("$SATCOMP_ROOT/examples/smt/z3")
        assert result == tmp_path / "examples" / "smt" / "z3"

    def test_unset_env_var_preserved(self):
        """Test that unset env vars are preserved in path (not expanded)."""
        # Ensure the var doesn't exist
        var_name = "DEFINITELY_NOT_SET_12345"
        if var_name in os.environ:
            del os.environ[var_name]

        result = pathing.normalize_path(f"${var_name}/subdir")
        # The unexpanded var becomes part of the path
        assert var_name in str(result)

    def test_multiple_env_vars(self, tmp_path, monkeypatch):
        """Test that multiple env vars in one path are expanded."""
        monkeypatch.setenv("VAR1", "first")
        monkeypatch.setenv("VAR2", "second")
        result = pathing.normalize_path("$VAR1/$VAR2/file.txt", relative_to=tmp_path)
        assert "first" in str(result)
        assert "second" in str(result)

    def test_env_var_with_relative_to(self, tmp_path, monkeypatch):
        """Test env var expansion works with relative_to parameter."""
        subdir = tmp_path / "base"
        subdir.mkdir()
        monkeypatch.setenv("SUBPATH", "nested/dir")

        result = pathing.normalize_path("$SUBPATH/file.txt", relative_to=subdir)
        assert result == subdir / "nested" / "dir" / "file.txt"

    def test_env_var_absolute_path(self, tmp_path, monkeypatch):
        """Test that env var expanding to absolute path works."""
        monkeypatch.setenv("ABS_PATH", str(tmp_path / "absolute"))
        result = pathing.normalize_path("$ABS_PATH/file.txt")
        assert result == tmp_path / "absolute" / "file.txt"
