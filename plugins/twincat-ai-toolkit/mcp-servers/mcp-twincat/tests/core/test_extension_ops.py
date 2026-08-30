"""Tests for the VS Code / Cursor extension management operations and MCP tools."""

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import extension_ops


def test_get_extension_dir_and_package_json():
    ext_dir = extension_ops.get_extension_dir()
    assert ext_dir.is_dir(), f"Extension directory not found: {ext_dir}"
    
    pkg = extension_ops.get_package_json()
    assert pkg.get("name") == "twincat-iecst"
    assert pkg.get("publisher") == "ElektroBeckhoff"
    assert pkg.get("author") == "elektrobeckhoff"
    assert "version" in pkg


def test_build_vsix():
    res = extension_ops.build_vsix()
    assert res.get("success") is True
    vsix_path = Path(res["vsix_path"])
    assert vsix_path.is_file()
    assert vsix_path.suffix == ".vsix"
    assert vsix_path.stat().st_size > 1000

    # Verify internal structure of the generated VSIX
    with zipfile.ZipFile(vsix_path, "r") as zf:
        namelist = zf.namelist()
        assert "[Content_Types].xml" in namelist
        assert "extension.vsixmanifest" in namelist
        assert "extension/package.json" in namelist
        assert "extension/dist/extension.js" in namelist
        assert "extension/syntaxes/iecst.tmLanguage.json" in namelist
        assert "extension/syntaxes/xml.iecst.codeblock.json" in namelist
        assert "extension/themes/twincat-xae-light.json" in namelist
        assert "extension/themes/twincat-xae-dark.json" in namelist
        assert "extension/language-configuration.json" in namelist

        manifest_content = zf.read("extension.vsixmanifest").decode("utf-8")
        assert 'Id="twincat-iecst"' in manifest_content
        assert 'Publisher="ElektroBeckhoff"' in manifest_content


def test_get_installed_extensions_parser():
    mock_stdout = "ElektroBeckhoff.twincat-iecst@0.1.0\nserhioromano.vscode-st@1.13.2\nms-python.python@2024.1.0\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout, stderr="")
        installed = extension_ops.get_installed_extensions("cursor")
        assert installed.get("elektrobeckhoff.twincat-iecst") == "0.1.0"
        assert installed.get("serhioromano.vscode-st") == "1.13.2"
        assert installed.get("ms-python.python") == "2024.1.0"


def test_get_extension_status_structure():
    status = extension_ops.get_extension_status()
    assert "extension_id" in status
    assert "available_version" in status
    assert "installed" in status
    assert "status" in status
    assert status["status"] in ("up_to_date", "not_installed", "update_available")
    assert "recommendation" in status


def test_server_extension_tools():
    import server

    status_raw = server.twincat_extension_status()
    status_data = json.loads(status_raw)
    assert status_data.get("extension_id") == "ElektroBeckhoff.twincat-iecst"

    build_raw = server.twincat_extension_build()
    build_data = json.loads(build_raw)
    assert build_data.get("success") is True


def test_auto_update_if_needed_when_already_up_to_date():
    with patch("extension_ops.get_extension_status") as mock_status, \
         patch("extension_ops.install_extension") as mock_install:
        mock_status.return_value = {
            "installed": True,
            "needs_update": False,
            "status": "up_to_date",
        }
        res = extension_ops.auto_update_if_needed()
        assert res is None
        mock_install.assert_not_called()


def test_auto_update_if_needed_when_outdated():
    with patch("extension_ops.get_extension_status") as mock_status, \
         patch("extension_ops.install_extension") as mock_install:
        mock_status.return_value = {
            "installed": True,
            "needs_update": True,
            "status": "update_available",
        }
        mock_install.return_value = {"success": True, "message": "Updated"}
        res = extension_ops.auto_update_if_needed()
        assert res is not None
        assert res.get("success") is True
        mock_install.assert_called_once()

