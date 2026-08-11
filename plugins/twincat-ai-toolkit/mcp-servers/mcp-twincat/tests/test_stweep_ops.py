"""Unit tests for STweep Format-code helpers (no live XAE)."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from twincat_automation_interface import TcAutomationInterface
from stweep_ops import (
    STWEEP_CMD_EDITOR,
    STWEEP_CMD_FOLDER,
    discover_stweep_installs,
)


def _make_bridge() -> TcAutomationInterface:
    with patch.object(TcAutomationInterface, "__init__", lambda self: None):
        bridge = TcAutomationInterface.__new__(TcAutomationInterface)
    bridge._dte = None
    bridge._sys_man = None
    bridge._plc_proj_item = None
    bridge._plcproj_file_path = None
    bridge._sln_path = None
    bridge._stweep_license_ok = None
    bridge._stweep_license_detail = ""
    bridge._call_sta = lambda func, *a, timeout=300, **kw: func(*a, **kw)
    bridge._retry_com = lambda func, *a, max_retries=5, delay_s=2, **kw: func(*a, **kw)
    bridge._ensure_format_progress_state()
    return bridge


class TestDiscoverInstall(unittest.TestCase):
    def test_discover_returns_list(self):
        installs = discover_stweep_installs()
        self.assertIsInstance(installs, list)


class TestStweepStatus(unittest.TestCase):
    def test_status_without_dte_uses_filesystem(self):
        b = _make_bridge()
        with patch(
            "stweep_ops.discover_stweep_installs",
            return_value=[{
                "path": r"C:\fake\STweep for TwinCAT (XAE Shell x64)",
                "version": "4.4.7.0",
            }],
        ):
            r = b.get_stweep_status(probe_license=False)
        self.assertTrue(r.success)
        self.assertTrue(r.installed)
        self.assertEqual(r.version, "4.4.7.0")
        self.assertFalse(r.dte_attached)
        self.assertEqual(r.license_state, "needs_session")
        self.assertFalse(r.ready)

    def test_status_default_no_wizard_ready_when_commands_loaded(self):
        b = _make_bridge()
        cmd = MagicMock()
        cmd.IsAvailable = True
        cmd.Guid = "{3395FA64-3C7F-4FB2-9551-CE197238B175}"
        cmd.ID = 257
        b._dte = MagicMock()
        b._dte.Commands.Item.side_effect = lambda name: cmd
        with patch("stweep_ops.discover_stweep_installs", return_value=[{
            "path": r"C:\fake\STweep", "version": "4.4.7.0",
        }]):
            with patch.object(b, "_probe_license_wizard") as probe:
                r = b.get_stweep_status()
                probe.assert_not_called()
        self.assertTrue(r.success)
        self.assertTrue(r.commands_loaded)
        self.assertIsNone(r.license_ok)
        self.assertEqual(r.license_state, "unknown")
        self.assertTrue(r.ready)


class TestFormatCode(unittest.TestCase):
    def test_requires_dte(self):
        b = _make_bridge()
        r = b.format_code(path=r"C:\x\A.TcPOU")
        self.assertFalse(r.success)
        self.assertIn("twincat_open", r.message)

    def test_rejects_unsupported_extension(self):
        b = _make_bridge()
        b._dte = MagicMock()
        cmd = MagicMock()
        cmd.IsAvailable = True
        cmd.Guid = "g"
        cmd.ID = 1
        b._dte.Commands.Item.return_value = cmd
        with tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False,
        ) as tmp:
            path = tmp.name
        try:
            with patch("stweep_ops.discover_stweep_installs", return_value=[]):
                r = b.format_code(path=path)
            self.assertFalse(r.success)
            self.assertIn("Unsupported", r.message)
        finally:
            os.unlink(path)

    def test_formats_single_file_via_editor_command(self):
        b = _make_bridge()
        b._dte = MagicMock()
        cmd = MagicMock()
        cmd.IsAvailable = True
        cmd.Guid = "g"
        cmd.ID = 257
        b._dte.Commands.Item.return_value = cmd
        doc = MagicMock()
        doc.FullName = ""
        doc.Saved = False
        b._dte.ActiveDocument = doc

        with tempfile.NamedTemporaryFile(
            suffix=".TcPOU", delete=False,
        ) as tmp:
            path = tmp.name
            tmp.write(b"dummy")
        doc.FullName = path
        try:
            with patch("stweep_ops.discover_stweep_installs", return_value=[{
                "path": r"C:\fake\STweep", "version": "4.4.7.0",
            }]):
                with patch.object(b, "_probe_license_wizard") as probe:
                    with patch("stweep_ops.time.sleep", return_value=None):
                        with patch(
                            "stweep_ops._tai",
                            return_value=MagicMock(
                                pythoncom=MagicMock(
                                    PumpWaitingMessages=MagicMock(),
                                ),
                            ),
                        ):
                            r = b.format_code(path=path, timeout_s=30)
                    probe.assert_not_called()
            self.assertTrue(r.success)
            self.assertEqual(r.files_formatted, 1)
            self.assertEqual(r.command, STWEEP_CMD_EDITOR)
            self.assertTrue(r.license_ok)
            b._dte.ItemOperations.OpenFile.assert_called()
            b._dte.ExecuteCommand.assert_any_call(STWEEP_CMD_EDITOR)
            doc.Save.assert_called()
        finally:
            os.unlink(path)

    def test_format_fail_fast_on_license_error(self):
        b = _make_bridge()
        b._dte = MagicMock()
        cmd = MagicMock()
        cmd.IsAvailable = True
        b._dte.Commands.Item.return_value = cmd
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "A.TcPOU")
            bpath = os.path.join(tmp, "B.TcPOU")
            for p in (a, bpath):
                with open(p, "wb") as fh:
                    fh.write(b"x")
            with patch("stweep_ops.discover_stweep_installs", return_value=[{
                "path": r"C:\fake\STweep", "version": "4.4.7.0",
            }]):
                with patch.object(
                    b, "_format_one_file",
                    side_effect=RuntimeError(
                        "Your copy of STweep for TwinCAT does not have a valid license"
                    ),
                ) as fmt:
                    with patch(
                        "stweep_ops._read_stweep_license_wizard",
                        return_value=None,
                    ):
                        r = b.format_code(path=tmp, recursive=False)
            self.assertFalse(r.success)
            self.assertEqual(r.method, "unlicensed")
            self.assertEqual(fmt.call_count, 1)
            self.assertFalse(r.license_ok)

    def test_collects_folder_files(self):
        b = _make_bridge()
        b._dte = MagicMock()
        cmd = MagicMock()
        cmd.IsAvailable = True
        b._dte.Commands.Item.return_value = cmd
        doc = MagicMock()
        doc.Saved = True

        with tempfile.TemporaryDirectory() as tmp:
            pou = os.path.join(tmp, "A.TcPOU")
            gvl = os.path.join(tmp, "B.TcGVL")
            tcio = os.path.join(tmp, "I_Foo.TcIO")
            skip = os.path.join(tmp, "C.txt")
            for p, body in (
                (pou, b"a"), (gvl, b"b"), (tcio, b"c"), (skip, b"d"),
            ):
                with open(p, "wb") as fh:
                    fh.write(body)
            doc.FullName = pou
            b._dte.ActiveDocument = doc

            def _open(p):
                doc.FullName = p

            b._dte.ItemOperations.OpenFile.side_effect = _open

            with patch("stweep_ops.discover_stweep_installs", return_value=[{
                "path": r"C:\fake\STweep", "version": "4.4.7.0",
            }]):
                with patch("stweep_ops.time.sleep", return_value=None):
                    with patch(
                        "stweep_ops._tai",
                        return_value=MagicMock(
                            pythoncom=MagicMock(
                                PumpWaitingMessages=MagicMock(),
                            ),
                        ),
                    ):
                        r = b.format_code(path=tmp, recursive=False)
            self.assertTrue(r.success)
            self.assertEqual(r.files_total, 3)
            self.assertEqual(r.files_formatted, 3)
            self.assertNotIn(STWEEP_CMD_FOLDER, r.command)

    def test_project_scope_requires_confirm(self):
        b = _make_bridge()
        b._dte = MagicMock()
        cmd = MagicMock()
        cmd.IsAvailable = True
        b._dte.Commands.Item.return_value = cmd

        with tempfile.TemporaryDirectory() as tmp:
            plcproj = os.path.join(tmp, "Lib.plcproj")
            with open(plcproj, "wb") as fh:
                fh.write(b"<Project/>")
            b._plcproj_file_path = plcproj

            r_empty = b.format_code(path="", confirm=False)
            self.assertFalse(r_empty.success)
            self.assertIn("confirm=true", r_empty.message)

            r_proj = b.format_code(path=plcproj, confirm=False)
            self.assertFalse(r_proj.success)
            self.assertIn("confirm=true", r_proj.message)

            r_root = b.format_code(path=tmp, confirm=False)
            self.assertFalse(r_root.success)
            self.assertIn("confirm=true", r_root.message)

    def test_plcproj_path_formats_with_confirm(self):
        b = _make_bridge()
        b._dte = MagicMock()
        cmd = MagicMock()
        cmd.IsAvailable = True
        b._dte.Commands.Item.return_value = cmd
        doc = MagicMock()
        doc.Saved = True

        with tempfile.TemporaryDirectory() as tmp:
            plcproj = os.path.join(tmp, "Lib.plcproj")
            with open(plcproj, "wb") as fh:
                fh.write(b"<Project/>")
            sub = os.path.join(tmp, "POUs")
            os.makedirs(sub)
            pou = os.path.join(sub, "A.TcPOU")
            tcio = os.path.join(sub, "I_A.TcIO")
            for p in (pou, tcio):
                with open(p, "wb") as fh:
                    fh.write(b"x")
            doc.FullName = pou
            b._dte.ActiveDocument = doc
            b._dte.ItemOperations.OpenFile.side_effect = (
                lambda p: setattr(doc, "FullName", p)
            )

            with patch("stweep_ops.discover_stweep_installs", return_value=[{
                "path": r"C:\fake\STweep", "version": "4.4.7.0",
            }]):
                with patch("stweep_ops.time.sleep", return_value=None):
                    with patch(
                        "stweep_ops._tai",
                        return_value=MagicMock(
                            pythoncom=MagicMock(
                                PumpWaitingMessages=MagicMock(),
                            ),
                        ),
                    ):
                        r = b.format_code(path=plcproj, confirm=True)
            self.assertTrue(r.success)
            self.assertEqual(r.files_total, 2)
            self.assertEqual(r.files_formatted, 2)

    def test_progress_updated_and_idle_after_sync_format(self):
        b = _make_bridge()
        b._dte = MagicMock()
        cmd = MagicMock()
        cmd.IsAvailable = True
        b._dte.Commands.Item.return_value = cmd
        doc = MagicMock()
        doc.Saved = True
        with tempfile.NamedTemporaryFile(
            suffix=".TcPOU", delete=False,
        ) as tmp:
            path = tmp.name
            tmp.write(b"x")
        doc.FullName = path
        b._dte.ActiveDocument = doc
        try:
            with patch("stweep_ops.discover_stweep_installs", return_value=[{
                "path": r"C:\fake\STweep", "version": "4.4.7.0",
            }]):
                with patch("stweep_ops.time.sleep", return_value=None):
                    with patch(
                        "stweep_ops._tai",
                        return_value=MagicMock(
                            pythoncom=MagicMock(
                                PumpWaitingMessages=MagicMock(),
                            ),
                        ),
                    ):
                        r = b.format_code(path=path, wait=True)
            self.assertTrue(r.success)
            prog = b.get_format_progress()
            self.assertFalse(prog.running)
            self.assertEqual(prog.phase, "done")
            self.assertEqual(prog.files_formatted, 1)
            self.assertEqual(prog.percent, 100.0)
            self.assertIsNotNone(prog.result)
        finally:
            os.unlink(path)

    def test_async_start_and_busy_reject(self):
        b = _make_bridge()
        b._dte = MagicMock()
        started = []

        def slow_sta(func, *a, timeout=300, **kw):
            import time as _t
            started.append(True)
            _t.sleep(0.35)
            return func(*a, **kw)

        b._call_sta = slow_sta
        with patch.object(
            b, "_impl_format_code",
            return_value=__import__(
                "results", fromlist=["StweepFormatResult"]
            ).StweepFormatResult(
                success=True, method="DTE_Editor_Formatcode",
                files_total=1, files_formatted=1, message="ok",
            ),
        ):
            r = b.format_code(path=r"C:\x\A.TcPOU", wait=False)
            self.assertTrue(r.async_started)
            self.assertEqual(r.method, "async_started")
            busy = b.format_code(path=r"C:\x\B.TcPOU", wait=False)
            self.assertFalse(busy.success)
            self.assertEqual(busy.method, "busy")
            # Wait for background job
            for _ in range(40):
                if not b.get_format_progress().running:
                    break
                import time as _t
                _t.sleep(0.05)
            prog = b.get_format_progress()
            self.assertFalse(prog.running)
            self.assertEqual(prog.phase, "done")


if __name__ == "__main__":
    unittest.main()
