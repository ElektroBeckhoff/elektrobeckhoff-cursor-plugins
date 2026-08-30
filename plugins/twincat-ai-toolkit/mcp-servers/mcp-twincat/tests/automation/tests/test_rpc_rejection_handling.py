"""
Tests for RPC_E_CALL_REJECTED handling in TcAutomationInterface.

Verifies that modal-dialog-busy (RPC_E_CALL_REJECTED) is correctly
distinguished from truly-dead-DTE errors across all code paths:
  - _is_dte_alive
  - _ensure_silent_mode
  - _restore_from_registry
  - _prune_stale_instances
  - _try_get_active_dte
  - _retry_com budget for CheckAllObjects / Build
"""

import os
import sys
import time
import threading
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ---------- Patch away pywin32 so we can run without COM ----------

_fake_pythoncom = MagicMock()
_fake_pythoncom.CoInitialize = MagicMock()
_fake_pythoncom.CoUninitialize = MagicMock()
_fake_pythoncom.PumpWaitingMessages = MagicMock()
_fake_pythoncom.CLSCTX_LOCAL_SERVER = 4
_fake_pythoncom.IID_IDispatch = "IID_IDispatch"
_fake_pythoncom.CoCreateInstance = MagicMock()

_fake_pywintypes = MagicMock()
_fake_win32com = MagicMock()
_fake_win32com_client = MagicMock()
_fake_win32com.client = _fake_win32com_client

sys.modules.setdefault("pythoncom", _fake_pythoncom)
sys.modules.setdefault("pywintypes", _fake_pywintypes)
sys.modules.setdefault("win32com", _fake_win32com)
sys.modules.setdefault("win32com.client", _fake_win32com_client)
sys.modules.setdefault("win32gui", MagicMock())
sys.modules.setdefault("win32con", MagicMock())

from twincat_automation_interface import (
    TcAutomationInterface,
    RPC_E_CALL_REJECTED,
    RPC_S_SERVER_UNAVAILABLE,
)


# ---- Helpers ----

def _make_com_error(hresult: int, msg: str = "COM error"):
    """Create a fake COM exception with .hresult attribute."""
    exc = Exception(msg)
    exc.hresult = hresult
    return exc


def _call_rejected(msg: str = "Aufruf wurde durch Aufgerufenen abgelehnt."):
    return _make_com_error(RPC_E_CALL_REJECTED, msg)


def _server_unavailable(msg: str = "RPC server unavailable"):
    return _make_com_error(RPC_S_SERVER_UNAVAILABLE, msg)


def _generic_com_error(msg: str = "Generic COM failure"):
    return Exception(msg)


def _make_bridge() -> TcAutomationInterface:
    """Create a TcAutomationInterface WITHOUT starting the STA thread."""
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


# ==================================================================
# _is_dte_alive -- busy != dead
# ==================================================================

class TestIsDteAlive:
    def test_alive_returns_true(self):
        bridge = _make_bridge()
        bridge._dte = MagicMock()
        bridge._dte.MainWindow.Caption = "TcXaeShell"

        assert bridge._is_dte_alive() is True

    def test_call_rejected_returns_true(self):
        """RPC_E_CALL_REJECTED means busy, NOT dead."""
        bridge = _make_bridge()
        bridge._dte = MagicMock()
        type(bridge._dte.MainWindow).Caption = PropertyMock(
            side_effect=_call_rejected()
        )

        assert bridge._is_dte_alive() is True, (
            "_is_dte_alive must return True on RPC_E_CALL_REJECTED"
        )

    def test_server_unavailable_returns_false(self):
        """RPC_S_SERVER_UNAVAILABLE means truly dead."""
        bridge = _make_bridge()
        bridge._dte = MagicMock()
        type(bridge._dte.MainWindow).Caption = PropertyMock(
            side_effect=_server_unavailable()
        )

        assert bridge._is_dte_alive() is False

    def test_generic_error_returns_false(self):
        bridge = _make_bridge()
        bridge._dte = MagicMock()
        type(bridge._dte.MainWindow).Caption = PropertyMock(
            side_effect=_generic_com_error()
        )

        assert bridge._is_dte_alive() is False

    def test_no_dte_returns_false(self):
        bridge = _make_bridge()
        bridge._dte = None

        assert bridge._is_dte_alive() is False


# ==================================================================
# _ensure_silent_mode -- retries on call-rejected, exits on other
# ==================================================================

class TestEnsureSilentMode:
    def test_success_first_try(self):
        bridge = _make_bridge()
        bridge._dte = MagicMock()
        settings = MagicMock()
        bridge._dte.GetObject.return_value = settings

        bridge._ensure_silent_mode()

        assert settings.SilentMode is True
        assert bridge._dte.GetObject.call_count == 1

    def test_retries_on_call_rejected_then_succeeds(self):
        """Must retry when call-rejected, then succeed."""
        bridge = _make_bridge()
        bridge._dte = MagicMock()
        settings = MagicMock()
        bridge._dte.GetObject.side_effect = [
            _call_rejected(),
            _call_rejected(),
            settings,
        ]

        bridge._ensure_silent_mode()

        assert bridge._dte.GetObject.call_count == 3
        assert settings.SilentMode is True

    def test_gives_up_after_6_retries(self):
        """Must not loop forever."""
        bridge = _make_bridge()
        bridge._dte = MagicMock()
        bridge._dte.GetObject.side_effect = _call_rejected()

        bridge._ensure_silent_mode()

        assert bridge._dte.GetObject.call_count == 6

    def test_no_retry_on_non_retryable_error(self):
        """Non-retryable error (e.g. SilentMode not available) -> exit immediately."""
        bridge = _make_bridge()
        bridge._dte = MagicMock()
        bridge._dte.GetObject.side_effect = _generic_com_error(
            "TcAutomationSettings not found"
        )

        bridge._ensure_silent_mode()

        assert bridge._dte.GetObject.call_count == 1, (
            "Must exit after first non-retryable error, not retry"
        )

    def test_no_dte_does_nothing(self):
        bridge = _make_bridge()
        bridge._dte = None
        bridge._ensure_silent_mode()


# ==================================================================
# _restore_from_registry -- busy entry not killed
# ==================================================================

class TestRestoreFromRegistry:
    def test_busy_entry_restored(self):
        """call-rejected on health check -> restore anyway, don't kill."""
        bridge = _make_bridge()
        fake_dte = MagicMock()
        type(fake_dte.MainWindow).Caption = PropertyMock(
            side_effect=_call_rejected()
        )

        sln_key = r"c:\test\test.sln"
        bridge._instances[sln_key] = {
            "dte": fake_dte,
            "sys_man": MagicMock(),
            "plc_proj_item": MagicMock(),
            "created_new": False,
            "we_opened_solution": False,
            "sln_path": sln_key,
            "plcproj_file_path": None,
            "prog_id": "TcXaeShell.DTE.17.0",
            "pid": 12345,
        }

        with patch.object(bridge, "_ensure_silent_mode"):
            result = bridge._restore_from_registry(sln_key)

        assert result is True, (
            "Busy (call-rejected) entry must be restored, not killed"
        )
        assert bridge._dte is fake_dte
        assert sln_key in bridge._instances

    def test_stale_entry_removed(self):
        """Generic COM error -> stale, remove entry."""
        bridge = _make_bridge()
        fake_dte = MagicMock()
        type(fake_dte.MainWindow).Caption = PropertyMock(
            side_effect=_generic_com_error()
        )

        sln_key = r"c:\test\test.sln"
        bridge._instances[sln_key] = {
            "dte": fake_dte,
            "sys_man": MagicMock(),
            "plc_proj_item": MagicMock(),
            "created_new": False,
            "we_opened_solution": False,
            "sln_path": sln_key,
            "plcproj_file_path": None,
            "prog_id": "TcXaeShell.DTE.17.0",
            "pid": None,
        }

        with patch.object(bridge, "_is_pid_alive", return_value=False):
            result = bridge._restore_from_registry(sln_key)

        assert result is False
        assert sln_key not in bridge._instances


# ==================================================================
# _prune_stale_instances -- skip busy, prune dead
# ==================================================================

class TestPruneStaleInstances:
    def test_busy_not_pruned(self):
        """Call-rejected instance must NOT be pruned."""
        bridge = _make_bridge()
        fake_dte = MagicMock()
        type(fake_dte.MainWindow).Caption = PropertyMock(
            side_effect=_call_rejected()
        )

        sln_key = r"c:\test\busy.sln"
        bridge._instances[sln_key] = {
            "dte": fake_dte,
            "sys_man": MagicMock(),
            "plc_proj_item": MagicMock(),
            "created_new": False,
            "we_opened_solution": False,
            "sln_path": sln_key,
            "pid": None,
        }

        bridge._prune_stale_instances()

        assert sln_key in bridge._instances, (
            "Busy (call-rejected) instance must not be pruned"
        )

    def test_dead_pruned(self):
        """Generic COM error instance MUST be pruned."""
        bridge = _make_bridge()
        fake_dte = MagicMock()
        type(fake_dte.MainWindow).Caption = PropertyMock(
            side_effect=_generic_com_error()
        )

        sln_key = r"c:\test\dead.sln"
        bridge._instances[sln_key] = {
            "dte": fake_dte,
            "sys_man": MagicMock(),
            "plc_proj_item": MagicMock(),
            "created_new": False,
            "we_opened_solution": False,
            "sln_path": sln_key,
            "pid": None,
        }

        bridge._prune_stale_instances()

        assert sln_key not in bridge._instances

    def test_dead_pid_pruned(self):
        """Instance with dead PID must be pruned."""
        bridge = _make_bridge()
        sln_key = r"c:\test\pid_dead.sln"
        bridge._instances[sln_key] = {
            "dte": MagicMock(),
            "sys_man": MagicMock(),
            "plc_proj_item": MagicMock(),
            "created_new": False,
            "we_opened_solution": False,
            "sln_path": sln_key,
            "pid": 99999,
        }

        with patch.object(bridge, "_is_pid_alive", return_value=False):
            bridge._prune_stale_instances()

        assert sln_key not in bridge._instances


# ==================================================================
# _try_get_active_dte -- busy DTE returned, not dropped
# ==================================================================

class TestTryGetActiveDte:
    def test_busy_dte_returned(self):
        """GetActiveObject OK + Caption rejected -> return DTE anyway."""
        bridge = _make_bridge()
        fake_dte = MagicMock()
        type(fake_dte.MainWindow).Caption = PropertyMock(
            side_effect=_call_rejected()
        )

        with patch("twincat_automation_interface._discover_registered_prog_ids",
                    return_value=["TcXaeShell.DTE.17.0"]):
            with patch("twincat_automation_interface.win32com.client.GetActiveObject",
                       return_value=fake_dte):
                result = bridge._try_get_active_dte()

        assert result is fake_dte, (
            "Must return DTE even when Caption is call-rejected"
        )

    def test_dead_dte_not_returned(self):
        """GetActiveObject OK + Caption generic error -> return None."""
        bridge = _make_bridge()
        fake_dte = MagicMock()
        type(fake_dte.MainWindow).Caption = PropertyMock(
            side_effect=_generic_com_error()
        )

        with patch("twincat_automation_interface._discover_registered_prog_ids",
                    return_value=["TcXaeShell.DTE.17.0"]):
            with patch("twincat_automation_interface.win32com.client.GetActiveObject",
                       return_value=fake_dte):
                result = bridge._try_get_active_dte()

        assert result is None

    def test_healthy_dte_returned(self):
        """Normal case: GetActiveObject + Caption both OK."""
        bridge = _make_bridge()
        fake_dte = MagicMock()
        fake_dte.MainWindow.Caption = "TcXaeShell"

        with patch("twincat_automation_interface._discover_registered_prog_ids",
                    return_value=["TcXaeShell.DTE.17.0"]):
            with patch("twincat_automation_interface.win32com.client.GetActiveObject",
                       return_value=fake_dte):
                result = bridge._try_get_active_dte()

        assert result is fake_dte


# ==================================================================
# _retry_com budget verification
# ==================================================================

class TestRetryComBudget:
    def test_default_budget(self):
        """Default: 5 retries, 2s delay."""
        bridge = _make_bridge()
        calls = []

        def failing_func():
            calls.append(time.time())
            raise _call_rejected()

        with pytest.raises(Exception):
            bridge._retry_com(failing_func)

        assert len(calls) == 5

    def test_extended_budget(self):
        """Extended: 10 retries as used by CheckAllObjects."""
        bridge = _make_bridge()
        calls = []

        def failing_func():
            calls.append(1)
            raise _call_rejected()

        with pytest.raises(Exception):
            bridge._retry_com(failing_func, max_retries=10, delay_s=0)

        assert len(calls) == 10

    def test_success_after_retries(self):
        """Succeeds after transient failures."""
        bridge = _make_bridge()
        attempts = [0]

        def sometimes_fails():
            attempts[0] += 1
            if attempts[0] < 4:
                raise _call_rejected()
            return "OK"

        result = bridge._retry_com(sometimes_fails, max_retries=10, delay_s=0)

        assert result == "OK"
        assert attempts[0] == 4


# ==================================================================
# Integration: Full open_solution flow with busy DTE (mocked STA)
# ==================================================================

class TestOpenSolutionBusyDte:
    """Test that _impl_open_solution handles a busy DTE correctly
    instead of dropping it and creating a second XAE instance."""

    def test_busy_dte_not_dropped_on_solution_check(self):
        """Step 2 of _impl_open_solution: Solution.IsOpen rejects
        but DTE should not be dropped."""
        bridge = _make_bridge()
        fake_dte = MagicMock()

        reject_count = [0]
        def _is_open_side_effect():
            reject_count[0] += 1
            if reject_count[0] <= 2:
                raise _call_rejected()
            return True

        type(fake_dte.Solution).IsOpen = PropertyMock(
            side_effect=_is_open_side_effect
        )
        type(fake_dte.Solution).FullName = PropertyMock(
            return_value=r"C:\test\test.sln"
        )

        bridge._dte = fake_dte
        bridge._created_new = False

        sln = r"C:\test\test.sln"

        with patch("twincat_automation_interface._canonical_path",
                   side_effect=lambda p: p.lower()):
            with patch("twincat_automation_interface.os.path.isfile",
                       return_value=True):
                with patch.object(bridge, "_prune_stale_instances"):
                    with patch.object(bridge, "_get_system_manager",
                                      return_value=MagicMock()):
                        with patch.object(bridge, "_find_plc_project_with_retry",
                                          return_value=MagicMock(Name="TestPLC")):
                            with patch.object(bridge, "_save_active_to_registry"):
                                with patch.object(bridge, "_detect_plcproj_path",
                                                  return_value=None):
                                    result = bridge._impl_open_solution(
                                        sln, None, None, 60,
                                    )

        assert result.success is True, f"Expected success, got: {result.message}"
        assert bridge._dte is not None, "DTE should not have been dropped"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
