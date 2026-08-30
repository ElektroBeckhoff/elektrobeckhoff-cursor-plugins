"""
Tests for extended twincat_status / _impl_get_status diagnostics.

Covers instances[].dte_busy, MCP session fields, blocking dialogs,
SilentMode, SysManager errors, and dismissed-dialog reporting.
"""

import os
import sys
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

_fake_pythoncom = MagicMock()
_fake_pythoncom.CoInitialize = MagicMock()
_fake_pythoncom.CoUninitialize = MagicMock()
_fake_pythoncom.PumpWaitingMessages = MagicMock()
_fake_pythoncom.CLSCTX_LOCAL_SERVER = 4
_fake_pythoncom.IID_IDispatch = "IID_IDispatch"
_fake_pythoncom.CoCreateInstance = MagicMock()

sys.modules.setdefault("pythoncom", _fake_pythoncom)
sys.modules.setdefault("pywintypes", MagicMock())
sys.modules.setdefault("win32com", MagicMock())
sys.modules.setdefault("win32com.client", MagicMock())
sys.modules.setdefault("win32gui", MagicMock())
sys.modules.setdefault("win32con", MagicMock())

from twincat_automation_interface import (
    TcAutomationInterface,
    StatusResult,
    RPC_E_CALL_REJECTED,
)


def _make_com_error(hresult: int, msg: str = "COM error"):
    exc = Exception(msg)
    exc.hresult = hresult
    return exc


def _call_rejected(msg: str = "call rejected"):
    return _make_com_error(RPC_E_CALL_REJECTED, msg)


def _make_bridge() -> TcAutomationInterface:
    with patch.object(TcAutomationInterface, "__init__", lambda self: None):
        bridge = TcAutomationInterface.__new__(TcAutomationInterface)
    bridge._queue = None
    bridge._thread = MagicMock()
    bridge._dte = None
    bridge._sys_man = None
    bridge._plc_proj_item = None
    bridge._created_new = False
    bridge._we_opened_solution = False
    bridge._sln_path = None
    bridge._plcproj_file_path = None
    bridge._prog_id = "TcXaeShell.DTE.17.0"
    bridge._instances = {}
    bridge._dismissed_dialogs = []
    return bridge


def _idle_dte(sln_path: str = r"C:\proj\Lib.sln"):
    dte = MagicMock()
    dte.MainWindow.Caption = "TcXaeShell"
    dte.MainWindow.HWnd = 0
    dte.Solution.IsOpen = bool(sln_path)
    dte.Solution.FullName = sln_path
    return dte


def _busy_dte():
    dte = MagicMock()
    type(dte.MainWindow).Caption = PropertyMock(side_effect=_call_rejected())
    type(dte.Solution).IsOpen = PropertyMock(side_effect=_call_rejected())
    return dte


# ==================================================================
# _probe_dte_busy
# ==================================================================

class TestProbeDteBusy:
    def test_idle_false(self):
        bridge = _make_bridge()
        assert bridge._probe_dte_busy(_idle_dte()) is False

    def test_rejected_true(self):
        bridge = _make_bridge()
        assert bridge._probe_dte_busy(_busy_dte()) is True

    def test_none_false(self):
        bridge = _make_bridge()
        assert bridge._probe_dte_busy(None) is False


# ==================================================================
# _enumerate_xae_dialogs
# ==================================================================

class TestEnumerateXaeDialogs:
    def test_empty_without_gui(self):
        bridge = _make_bridge()
        with patch(
            "twincat_automation_interface.HAS_WIN32GUI", False,
        ):
            assert bridge._enumerate_xae_dialogs() == []

    def test_finds_visible_dialog(self):
        bridge = _make_bridge()
        fake_gui = MagicMock()
        fake_gui.IsWindowVisible.return_value = True
        fake_gui.GetWindowText.side_effect = lambda hwnd: (
            "TcXaeShell" if hwnd == 42 else "file has been modified outside"
        )
        fake_gui.GetClassName.side_effect = lambda hwnd: (
            "#32770" if hwnd == 42 else "Static"
        )

        def enum_windows(cb, _):
            cb(42, None)

        def enum_children(hwnd, cb, _):
            cb(100, None)

        fake_gui.EnumWindows.side_effect = enum_windows
        fake_gui.EnumChildWindows.side_effect = enum_children

        with patch(
            "twincat_automation_interface.HAS_WIN32GUI", True,
        ), patch(
            "twincat_automation_interface.win32gui", fake_gui,
        ):
            dialogs = bridge._enumerate_xae_dialogs()

        assert len(dialogs) == 1
        assert dialogs[0]["hwnd"] == 42
        assert dialogs[0]["auto_dismissable"] is True
        assert "modified outside" in dialogs[0]["matched_pattern"]

    def test_4024_changed_outside_wording(self):
        """4024 uses 'changed' not 'modified' — must still auto-dismiss."""
        bridge = _make_bridge()
        # Path and sentence often split across Static children (or newlines)
        child_text = {
            100: r"c:\proj\foo.tcpou",
            101: "file has been changed outside the environment.\nReload the new contents?",
        }
        fake_gui = MagicMock()
        fake_gui.IsWindowVisible.return_value = True
        fake_gui.GetWindowText.side_effect = lambda hwnd: (
            "TcXaeShell" if hwnd == 42 else child_text.get(hwnd, "")
        )
        fake_gui.GetClassName.side_effect = lambda hwnd: (
            "#32770" if hwnd == 42 else "Static"
        )

        def enum_windows(cb, _):
            cb(42, None)

        def enum_children(hwnd, cb, _):
            cb(100, None)
            cb(101, None)

        fake_gui.EnumWindows.side_effect = enum_windows
        fake_gui.EnumChildWindows.side_effect = enum_children

        with patch(
            "twincat_automation_interface.HAS_WIN32GUI", True,
        ), patch(
            "twincat_automation_interface.win32gui", fake_gui,
        ):
            dialogs = bridge._enumerate_xae_dialogs()

        assert len(dialogs) == 1
        assert dialogs[0]["auto_dismissable"] is True
        assert "changed outside" in dialogs[0]["matched_pattern"]

    def test_match_patterns_normalize_whitespace(self):
        bridge = _make_bridge()
        blob = bridge._normalize_dialog_text(
            "Foo.TcPOU\n\nfile has been   changed\toutside the environment"
        )
        assert bridge._match_safe_dialog_pattern(blob) == (
            "file has been changed outside"
        )


# ==================================================================
# _impl_get_status
# ==================================================================

class TestImplGetStatus:
    def test_not_installed(self):
        bridge = _make_bridge()
        with patch.object(bridge, "_prune_stale_instances"), \
             patch.object(bridge, "_enumerate_xae_dialogs", return_value=[]), \
             patch(
                 "twincat_automation_interface._discover_registered_prog_ids",
                 return_value=[],
             ), \
             patch.object(bridge, "_enumerate_rot_dtes", return_value=[]):
            result = bridge._impl_get_status()

        assert isinstance(result, StatusResult)
        assert result.xae_available is False
        assert result.running_instance is False
        assert result.instances == []
        assert result.mcp_session_active is False

    def test_installed_not_running(self):
        bridge = _make_bridge()
        with patch.object(bridge, "_prune_stale_instances"), \
             patch.object(bridge, "_enumerate_xae_dialogs", return_value=[]), \
             patch(
                 "twincat_automation_interface._discover_registered_prog_ids",
                 return_value=["TcXaeShell.DTE.17.0"],
             ), \
             patch.object(bridge, "_enumerate_rot_dtes", return_value=[]), \
             patch(
                 "twincat_automation_interface.win32com.client.GetActiveObject",
                 side_effect=Exception("not running"),
             ):
            result = bridge._impl_get_status()

        assert result.xae_available is True
        assert result.running_instance is False
        assert "not running" in result.message

    def test_running_idle_instance(self):
        bridge = _make_bridge()
        dte = _idle_dte(r"C:\proj\Lib.sln")
        with patch.object(bridge, "_prune_stale_instances"), \
             patch.object(bridge, "_enumerate_xae_dialogs", return_value=[]), \
             patch(
                 "twincat_automation_interface._discover_registered_prog_ids",
                 return_value=["TcXaeShell.DTE.17.0"],
             ), \
             patch.object(
                 bridge, "_enumerate_rot_dtes",
                 return_value=[
                     ("TcXaeShell.DTE.17.0", "!TcXaeShell.DTE.17.0:1", dte),
                 ],
             ), \
             patch.object(bridge, "_get_dte_pid", return_value=1234):
            result = bridge._impl_get_status()

        assert result.running_instance is True
        assert len(result.instances) == 1
        assert result.instances[0]["dte_busy"] is False
        assert result.instances[0]["pid"] == 1234
        assert "Lib.sln" in result.solution_path or result.solution_path.endswith(
            "lib.sln"
        )

    def test_busy_instance_flagged(self):
        bridge = _make_bridge()
        dte = _busy_dte()
        with patch.object(bridge, "_prune_stale_instances"), \
             patch.object(bridge, "_enumerate_xae_dialogs", return_value=[]), \
             patch(
                 "twincat_automation_interface._discover_registered_prog_ids",
                 return_value=["TcXaeShell.DTE.17.0"],
             ), \
             patch.object(
                 bridge, "_enumerate_rot_dtes",
                 return_value=[
                     ("TcXaeShell.DTE.17.0", "!m:1", dte),
                 ],
             ), \
             patch.object(bridge, "_get_dte_pid", return_value=None):
            result = bridge._impl_get_status()

        assert result.instances[0]["dte_busy"] is True
        assert "COM-busy" in result.message or "busy" in result.message

    def test_mcp_session_and_silent_mode(self):
        bridge = _make_bridge()
        bridge._dte = _idle_dte()
        bridge._sln_path = r"C:\proj\Lib.sln"
        bridge._plc_proj_item = MagicMock()
        bridge._plc_proj_item.Name = "Tc3_Lib"
        settings = MagicMock()
        settings.SilentMode = True
        bridge._dte.GetObject.return_value = settings

        with patch.object(bridge, "_prune_stale_instances"), \
             patch.object(bridge, "_enumerate_xae_dialogs", return_value=[]), \
             patch(
                 "twincat_automation_interface._discover_registered_prog_ids",
                 return_value=["TcXaeShell.DTE.17.0"],
             ), \
             patch.object(bridge, "_enumerate_rot_dtes", return_value=[]), \
             patch(
                 "twincat_automation_interface.win32com.client.GetActiveObject",
                 side_effect=Exception("skip"),
             ):
            result = bridge._impl_get_status()

        assert result.mcp_session_active is True
        assert result.mcp_plc_project_name == "Tc3_Lib"
        assert result.silent_mode is True
        assert "MCP session active" in result.message

    def test_blocking_dialogs_and_dismissed(self):
        bridge = _make_bridge()
        bridge._dismissed_dialogs = ["[pattern] old dialog"]
        dialogs = [{
            "hwnd": 1,
            "title": "TcXaeShell",
            "text": "unknown prompt",
            "auto_dismissable": False,
            "matched_pattern": "",
        }]
        with patch.object(bridge, "_prune_stale_instances"), \
             patch.object(
                 bridge, "_enumerate_xae_dialogs", return_value=dialogs,
             ), \
             patch(
                 "twincat_automation_interface._discover_registered_prog_ids",
                 return_value=["TcXaeShell.DTE.17.0"],
             ), \
             patch.object(bridge, "_enumerate_rot_dtes", return_value=[]), \
             patch(
                 "twincat_automation_interface.win32com.client.GetActiveObject",
                 side_effect=Exception("skip"),
             ):
            result = bridge._impl_get_status()

        assert result.blocking_dialogs == dialogs
        assert result.dismissed_dialogs_recent == ["[pattern] old dialog"]
        assert bridge._dismissed_dialogs == []
        assert "dialog" in result.message.lower()

    def test_sys_manager_errors_and_runtime(self):
        bridge = _make_bridge()
        bridge._sys_man = MagicMock()
        bridge._sys_man.GetLastErrorMessages.return_value = "Link error XYZ"
        bridge._sys_man.IsTwinCATStarted.return_value = True

        with patch.object(bridge, "_prune_stale_instances"), \
             patch.object(bridge, "_enumerate_xae_dialogs", return_value=[]), \
             patch(
                 "twincat_automation_interface._discover_registered_prog_ids",
                 return_value=["TcXaeShell.DTE.17.0"],
             ), \
             patch.object(bridge, "_enumerate_rot_dtes", return_value=[]), \
             patch(
                 "twincat_automation_interface.win32com.client.GetActiveObject",
                 side_effect=Exception("skip"),
             ):
            result = bridge._impl_get_status()

        assert result.sys_manager_errors == "Link error XYZ"
        assert result.twincat_runtime_started is True
        assert "SysManager has error messages" in result.message


class TestDismissSafeDialogs:
    def test_dismisses_auto_dismissable_queue(self):
        bridge = _make_bridge()
        dlg = {
            "hwnd": 42,
            "title": "TcXaeShell",
            "text": "file has been changed outside the environment",
            "auto_dismissable": True,
            "matched_pattern": "file has been changed outside",
        }
        calls = {"n": 0}

        def enum():
            calls["n"] += 1
            # First pass: one dialog; after PostMessage: empty
            if calls["n"] == 1:
                return [dlg]
            return []

        fake_gui = MagicMock()
        with patch(
            "twincat_automation_interface.HAS_WIN32GUI", True,
        ), patch(
            "twincat_automation_interface.win32gui", fake_gui,
        ), patch(
            "twincat_automation_interface.win32con", MagicMock(WM_COMMAND=273),
        ), patch.object(bridge, "_enumerate_xae_dialogs", side_effect=enum):
            result = bridge.dismiss_safe_dialogs()

        assert result.success is True
        assert result.dismissed_count == 1
        assert result.remaining_blocking == []
        fake_gui.PostMessage.assert_called()

    def test_leaves_non_safe_dialogs(self):
        bridge = _make_bridge()
        unsafe = {
            "hwnd": 7,
            "title": "TcXaeShell",
            "text": "save changes to untitled?",
            "auto_dismissable": False,
            "matched_pattern": "",
        }
        with patch(
            "twincat_automation_interface.HAS_WIN32GUI", True,
        ), patch.object(
            bridge, "_enumerate_xae_dialogs", return_value=[unsafe],
        ):
            result = bridge.dismiss_safe_dialogs()

        assert result.success is True
        assert result.dismissed_count == 0
        assert len(result.remaining_blocking) == 1
        assert "not auto-dismissable" in result.message.lower() or (
            "remain" in result.message.lower()
        )
