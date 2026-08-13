"""Unit tests for async library export / progress (no live XAE)."""
from __future__ import annotations

import os
import tempfile
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

    def test_wait_true_long_timeout_coerced_to_async(self):
        b = _make_bridge()
        done = ExportResult(success=True, message="ok")

        def quick(*_a, **_k):
            return done

        with patch.object(b, "_impl_export_library", side_effect=quick):
            r = b.export_library(
                r"C:\out", "Lib", "1.0.0.0",
                library=True, compiled_library=False,
                wait=True, timeout_s=1800,
            )
        self.assertTrue(r.async_started)
        self.assertIn("coerced", r.message.lower())
        for _ in range(40):
            if not b.get_export_progress().running:
                break
            time.sleep(0.05)

    def test_check_export_artifacts_present(self):
        b = _make_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            lib = os.path.join(tmp, "Lib-1.0.0.0.library")
            with open(lib, "wb") as fh:
                fh.write(b"x" * 100)
            r = b.check_export_artifacts(
                output_dir=tmp,
                project_title="Lib",
                project_version="1.0.0.0",
                library=True,
                compiled_library=False,
            )
        self.assertTrue(r.success)
        self.assertTrue(r.all_present)

    def test_check_export_artifacts_missing(self):
        b = _make_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            r = b.check_export_artifacts(
                output_dir=tmp,
                project_title="Lib",
                project_version="1.0.0.0",
                library=True,
                compiled_library=True,
            )
        self.assertTrue(r.success)
        self.assertFalse(r.all_present)

    def test_zero_byte_library_fails_export(self):
        b = _make_bridge()
        with tempfile.TemporaryDirectory() as tmp:
            lib_path = os.path.join(tmp, "Lib-1.0.0.0.library")

            def save_as(path, _install):
                with open(path, "wb") as fh:
                    fh.write(b"")

            b._plc_proj_item.SaveAsLibrary.side_effect = save_as
            with patch.object(b, "_impl_check_all_objects") as chk:
                chk.return_value = MagicMock(success=True, error_count=0)
                with patch.object(
                    b, "_find_git_root", return_value=tmp,
                ):
                    b._sln_path = os.path.join(tmp, "Lib.sln")
                    r = b._impl_export_library(
                        tmp, "Lib", "1.0.0.0",
                        library=True, compiled_library=False,
                        install_library=False,
                        install_compiled_library=False,
                    )
            self.assertFalse(r.success)
            self.assertFalse(r.artifacts_on_disk)
            self.assertIn("zero-size", r.message.lower())
            self.assertTrue(os.path.isfile(lib_path))

    def test_export_heartbeat_updates_progress(self):
        b = _make_bridge()
        updates = []

        def slow(*_a, **_k):
            time.sleep(0.35)
            return ExportResult(success=True, message="ok")

        orig = b._update_export_progress

        def track(**kw):
            updates.append(dict(kw))
            return orig(**kw)

        b._update_export_progress = track
        with patch("build_ops._EXPORT_HEARTBEAT_S", 0.1):
            with patch.object(b, "_impl_export_library", side_effect=slow):
                r = b._run_export_sta(
                    r"C:\out", "Lib", "1.0.0.0",
                    True, False, False, False, 60,
                )
        self.assertTrue(r.success)
        self.assertTrue(
            any("in progress" in str(u.get("message", "")) for u in updates),
        )


if __name__ == "__main__":
    unittest.main()
