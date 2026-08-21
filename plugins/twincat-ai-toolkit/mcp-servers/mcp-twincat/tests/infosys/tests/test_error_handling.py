"""Unit tests for structured error handling and error codes."""

import json
from infosys_mshc.cli import main


def test_cli_error_code_on_missing_mshc(capsys):
    """Verify structured error code when MSHC file does not exist."""
    ret = main(["--search", "test", "--file", "nonexistent/file.mshc", "--json"])
    assert ret == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["success"] is False
    assert data["error_code"] == "MSHC_NOT_INSTALLED"


def test_cli_error_code_on_page_not_found(capsys):
    """Verify structured error code when page path does not exist."""
    ret = main(["--read", "invalid/page.html", "--json"])
    assert ret == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["success"] is False
    assert data["error_code"] in ("PAGE_NOT_FOUND", "MSHC_NOT_INSTALLED")
