"""Tests for autodocs path resolution."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autodocs.paths import resolve_output_root


def test_resolve_explicit_output(tmp_path):
    inp = tmp_path / "Lib" / "sources"
    inp.mkdir(parents=True)
    explicit = tmp_path / "custom-root"
    explicit.mkdir()
    assert resolve_output_root(inp, explicit) == explicit.resolve()


def test_resolve_walk_up_readme(tmp_path):
    repo = tmp_path / "repo"
    solution = repo / "LibName"
    solution.mkdir(parents=True)
    (repo / "README.md").write_text("# Lib\n", encoding="utf-8")
    assert resolve_output_root(solution) == repo.resolve()


def test_resolve_walk_up_git(tmp_path):
    repo = tmp_path / "repo"
    solution = repo / "LibName"
    solution.mkdir(parents=True)
    (repo / ".git").mkdir()
    assert resolve_output_root(solution) == repo.resolve()


def test_resolve_input_is_repo_root(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Lib\n", encoding="utf-8")
    assert resolve_output_root(repo) == repo.resolve()


def test_resolve_fallback_parent(tmp_path):
    inp = tmp_path / "nested" / "sources"
    inp.mkdir(parents=True)
    assert resolve_output_root(inp) == (tmp_path / "nested").resolve()
