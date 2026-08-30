"""Smoke test for twincat_autodocs MCP tool wiring."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MINI = Path(__file__).resolve().parent.parent / "fixtures" / "raw" / "miniproject"


def test_twincat_autodocs_smoke(tmp_path):
    import server

    result_json = server.twincat_autodocs(
        input=str(MINI),
        output=str(tmp_path / "out"),
    )
    data = json.loads(result_json)
    assert data["success"] is True
    assert data["errors"] == 0
    assert len(data["files_created"]) == 4
    assert "log" in data
    assert "repo_root" in data
    assert data["output"].endswith("docs")
