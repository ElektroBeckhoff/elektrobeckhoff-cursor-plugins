"""Unit tests for robust .plcproj resolution and export progress artifacts."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_MCP_ROOT = Path(__file__).resolve().parents[3]
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
_AUTO_ROOT = _MCP_ROOT / "automation_interface"
if str(_AUTO_ROOT) not in sys.path:
    sys.path.insert(0, str(_AUTO_ROOT))

from com_retry import (
    is_call_rejected,
    RPC_E_CALL_REJECTED,
    RPC_E_CALL_CANCELED,
    RPC_E_SERVERCALL_RETRYLATER,
    RPC_E_DISCONNECTED,
    RPC_E_CANTCALLOUT_ININPUTSYNCCALL,
)
from results import ExportResult, ExportProgressResult
from twincat_automation_interface import TcAutomationInterface
from server import _auto_detect_plcproj, _resolve_plcproj_path


class TestComBusyHresults(unittest.TestCase):
    def test_extended_busy_hresults_recognized(self):
        for hr in (
            RPC_E_CALL_REJECTED,
            RPC_E_CALL_CANCELED,
            RPC_E_SERVERCALL_RETRYLATER,
            RPC_E_DISCONNECTED,
            RPC_E_CANTCALLOUT_ININPUTSYNCCALL,
        ):
            exc = Exception(f"COM error {hr}")
            exc.hresult = hr
            self.assertTrue(is_call_rejected(exc), f"HRESULT {hr} should be recognized as busy")

    def test_non_busy_hresults_not_rejected(self):
        exc = Exception("General failure")
        exc.hresult = -2147467259  # E_FAIL (0x80004005)
        self.assertFalse(is_call_rejected(exc))


class TestPlcprojResolution(unittest.TestCase):
    def test_direct_absolute_path_resolved_without_sln_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a deeply nested plcproj: level1/level2/level3/level4/level5/Sample.plcproj
            deep_dir = os.path.join(tmpdir, "a", "b", "c", "d", "e")
            os.makedirs(deep_dir, exist_ok=True)
            plcproj_file = os.path.join(deep_dir, "DeepSample.plcproj")
            with open(plcproj_file, "w") as f:
                f.write("<Project></Project>")

            # Explicit path should resolve directly
            resolved = _resolve_plcproj_path(plcproj_file)
            self.assertEqual(os.path.normcase(resolved), os.path.normcase(plcproj_file))

            # Quoted explicit path should also resolve
            quoted = f'"{plcproj_file}"'
            resolved_quoted = _resolve_plcproj_path(quoted)
            self.assertEqual(os.path.normcase(resolved_quoted), os.path.normcase(plcproj_file))

    def test_deep_recursion_in_sln_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sln_dir = os.path.join(tmpdir, "SolutionDir")
            deep_dir = os.path.join(sln_dir, "Sub1", "Sub2", "Sub3", "Sub4", "Sub5", "Sub6")
            os.makedirs(deep_dir, exist_ok=True)
            sln_file = os.path.join(sln_dir, "MySolution.sln")
            with open(sln_file, "w") as f:
                f.write("Microsoft Visual Studio Solution File")
            plcproj_file = os.path.join(deep_dir, "MyProject.plcproj")
            with open(plcproj_file, "w") as f:
                f.write("<Project></Project>")

            # Auto-detect from sln_path should find the deeply nested plcproj
            found = _auto_detect_plcproj(sln_file)
            self.assertEqual(os.path.normcase(found), os.path.normcase(plcproj_file))

    def test_active_bridge_priority_over_workspace_scan(self):
        bridge = MagicMock()
        bridge._plcproj_file_path = r"C:\active_repo\Tc3_EB_BA\Tc3_EB_BA.plcproj"
        bridge._sln_path = r"C:\active_repo\Tc3_EB_BA\Tc3_EB_BA.sln"

        with patch("os.path.isfile", side_effect=lambda p: p in (bridge._plcproj_file_path, bridge._sln_path)):
            # When plcproj_path is empty, plcproj_from_bridge must take precedence
            resolved = _resolve_plcproj_path(
                plcproj_path="",
                sln_path=bridge._sln_path,
                plcproj_from_bridge=bridge._plcproj_file_path,
            )
            self.assertEqual(os.path.normcase(resolved), os.path.normcase(bridge._plcproj_file_path))

    def test_detect_plcproj_path_in_session_ops(self):
        with patch.object(TcAutomationInterface, "__init__", lambda self: None):
            b = TcAutomationInterface.__new__(TcAutomationInterface)

        with tempfile.TemporaryDirectory() as tmpdir:
            sln_dir = os.path.join(tmpdir, "Nested", "Structure", "Deep", "Dirs")
            os.makedirs(sln_dir, exist_ok=True)
            sln_path = os.path.join(sln_dir, "App.sln")
            with open(sln_path, "w") as f:
                f.write("sln")
            plcproj_path = os.path.join(sln_dir, "AppPLC.plcproj")
            with open(plcproj_path, "w") as f:
                f.write("<Project/>")

            b._sln_path = sln_path
            b._plc_proj_item = MagicMock()
            b._plc_proj_item.Name = "AppPLC"

            detected = b._detect_plcproj_path()
            self.assertIsNotNone(detected)
            self.assertEqual(os.path.normcase(detected), os.path.normcase(plcproj_path))


class TestExportProgressDirectArtifacts(unittest.TestCase):
    def test_export_progress_returns_artifacts_at_root(self):
        with patch.object(TcAutomationInterface, "__init__", lambda self: None):
            b = TcAutomationInterface.__new__(TcAutomationInterface)
        b._export_lock = MagicMock()
        b._export_lock.__enter__ = MagicMock()
        b._export_lock.__exit__ = MagicMock()

        done_result = {
            "success": True,
            "library_path": r"C:\Versions\1.6.8.0\Tc3_EB_BA-1.6.8.0.library",
            "compiled_library_path": r"C:\Versions\1.6.8.0\Tc3_EB_BA-1.6.8.0.compiled-library",
            "artifacts_on_disk": True,
            "artifacts": [
                {
                    "kind": "library",
                    "path": r"C:\Versions\1.6.8.0\Tc3_EB_BA-1.6.8.0.library",
                    "size_kb": 45.2,
                    "exists": True,
                },
                {
                    "kind": "compiled_library",
                    "path": r"C:\Versions\1.6.8.0\Tc3_EB_BA-1.6.8.0.compiled-library",
                    "size_kb": 89.1,
                    "exists": True,
                },
            ],
        }

        b._export_progress = {
            "running": False,
            "phase": "done",
            "output_dir": r"C:\Versions\1.6.8.0",
            "project_title": "Tc3_EB_BA",
            "project_version": "1.6.8.0",
            "percent": 100.0,
            "started_unix": 100.0,
            "updated_unix": 120.0,
            "message": "Export complete",
            "result": done_result,
        }

        prog = b.get_export_progress()
        self.assertFalse(prog.running)
        self.assertEqual(prog.phase, "done")
        self.assertTrue(prog.artifacts_on_disk)
        self.assertEqual(len(prog.artifacts), 2)
        self.assertEqual(prog.library_path, r"C:\Versions\1.6.8.0\Tc3_EB_BA-1.6.8.0.library")
        self.assertEqual(prog.compiled_library_path, r"C:\Versions\1.6.8.0\Tc3_EB_BA-1.6.8.0.compiled-library")


if __name__ == "__main__":
    unittest.main()
