"""Unit tests for async library export / progress (no live XAE)."""
from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from twincat_automation_interface import TcAutomationInterface
from results import ExportResult


def _make_bridge() -> TcAutomationInterface:
    with patch.object(TcAutomationInterface, "__init__", lambda self: None):
        bridge = TcAutomationInterface.__new__(TcAutomationInterface)
    bridge._dte = MagicMock()
    bridge._plc_proj_item = MagicMock()
    bridge._sln_path = r"C:\repo\Lib\Lib.sln"
    bridge._plcproj_file_path = r"C:\repo\Lib\Lib.plcproj"
    bridge._call_sta = lambda func, *a, timeout=300, **kw: func(*a, **kw)
    bridge._ensure_export_progress_state()
    return bridge


class TestExportAsync(unittest.TestCase):
    def test_wait_false_returns_async_started(self):
        b = _make_bridge()
        done = ExportResult(
            success=True,
            library_path=r"C:\repo\Versions\1.0.0.0\Lib-1.0.0.0.library",
            library_size_kb=12.0,
            message="Exported 12.0 KB .library",
        )

        def slow_export(*_a, **_k):
            time.sleep(0.15)
            return done

        with patch.object(b, "_impl_export_library", side_effect=slow_export):
            r = b.export_library(
                r"C:\repo\Versions\1.0.0.0",
                "Lib",
                "1.0.0.0",
                library=True,
                compiled_library=False,
                wait=False,
                timeout_s=60,
            )
            self.assertTrue(r.async_started)
            self.assertEqual(r.method, "async_started")
            for _ in range(40):
                if not b.get_export_progress().running:
                    break
                time.sleep(0.05)
            prog = b.get_export_progress()
            self.assertFalse(prog.running)
            self.assertEqual(prog.phase, "done")
            self.assertIsNotNone(prog.result)
            self.assertTrue(prog.result["success"])

    def test_busy_when_export_running(self):
        b = _make_bridge()
        b._export_progress["running"] = True
        r = b.export_library(
            r"C:\out", "Lib", "1.0.0.0", wait=False,
        )
        self.assertFalse(r.success)
        self.assertEqual(r.method, "busy")


if __name__ == "__main__":
    unittest.main()
