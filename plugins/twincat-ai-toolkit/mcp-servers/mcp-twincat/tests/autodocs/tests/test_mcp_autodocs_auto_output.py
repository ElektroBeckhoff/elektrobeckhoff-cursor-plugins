"""MCP autodocs with auto-detected repo root."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MINI = Path(__file__).resolve().parent.parent / "fixtures" / "raw" / "miniproject"


def test_twincat_autodocs_auto_repo_root(tmp_path):
    import server

    repo = tmp_path / "repo"
    solution = repo / "LibName"
    solution.mkdir(parents=True)
    (repo / "README.md").write_text("# Lib\n", encoding="utf-8")

    for src in MINI.iterdir():
        if src.is_file():
            (solution / src.name).write_bytes(src.read_bytes())

    result_json = server.twincat_autodocs(input=str(solution))
    data = json.loads(result_json)
    assert data["success"] is True
    assert data["errors"] == 0
    assert Path(data["repo_root"]) == repo.resolve()
    assert data["output"].endswith("docs")
    assert (repo / "docs" / "toc.md").exists()
