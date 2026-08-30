"""End-to-end process_folder tests with miniproject fixture."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autodocs.pipeline import process_folder

MINI = Path(__file__).resolve().parent.parent / "fixtures" / "raw" / "miniproject"


def test_pipeline_miniproject(tmp_path):
    out = tmp_path / "project"
    report = process_folder(MINI, out, verbose=False)
    assert report.errors == 0
    assert len(report.files_created) == 4
    assert (out / "docs" / "toc.md").exists()
    assert (out / "README.md").exists()
    # Default: no log file written (to keep CI diffs stable)
    assert not (out / "docs" / "autodocs.log").exists()

    toc = (out / "docs" / "toc.md").read_text(encoding="utf-8")
    assert "<!-- TOC -->" in toc
    assert re.search(r"_Automatically generated_", toc)

    # Optional: log file can be enabled explicitly
    out2 = tmp_path / "project_with_log"
    report2 = process_folder(
        MINI,
        out2,
        verbose=False,
        write_log=True,
    )
    assert report2.errors == 0
    assert (out2 / "docs" / "autodocs.log").exists()


def test_pipeline_report_fields(tmp_path):
    report = process_folder(MINI, tmp_path / "out", verbose=False)
    assert report.success is True
    assert report.skipped_hidden == 0
    assert report.duration_sec >= 0
    assert report.output.endswith("docs")
