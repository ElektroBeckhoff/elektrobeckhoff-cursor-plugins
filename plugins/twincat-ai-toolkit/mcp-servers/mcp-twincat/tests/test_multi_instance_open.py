"""
Tests for multi-instance ROT solution matching and XAE version selection.

Covers:
  - Finding the correct solution among multiple running XAE instances
  - Not starting a new instance when the solution is already open
  - xae_version / ProgID normalisation (4024 / 4026)
  - Preferring an already-running shell version when creating new
"""

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

_fake_win32com = MagicMock()
_fake_win32com_client = MagicMock()
_fake_win32com.client = _fake_win32com_client

sys.modules.setdefault("pythoncom", _fake_pythoncom)
sys.modules.setdefault("pywintypes", MagicMock())
sys.modules.setdefault("win32com", _fake_win32com)
sys.modules.setdefault("win32com.client", _fake_win32com_client)
sys.modules.setdefault("win32gui", MagicMock())
sys.modules.setdefault("win32con", MagicMock())

from twincat_automation_interface import (
    TcAutomationInterface,
    _normalize_xae_version,
    _tc_version_label,
    _PROG_ID_PREFIX,
)


PROG_4026 = f"{_PROG_ID_PREFIX}17.0"
PROG_4024 = f"{_PROG_ID_PREFIX}15.0"

REGISTERED = [PROG_4026, PROG_4024]


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
    bridge._prog_id = None
    bridge._instances = {}
    bridge._dismissed_dialogs = []
    return bridge


def _fake_dte(sln_path: str = "", is_open: bool = True):
    dte = MagicMock()
    type(dte.Solution).IsOpen = PropertyMock(return_value=is_open)
    type(dte.Solution).FullName = PropertyMock(return_value=sln_path)
    dte.MainWindow.Caption = "TcXaeShell"
    return dte


# ==================================================================
# Version normalisation
# ==================================================================

class TestNormalizeXaeVersion:
    def test_4026_alias(self):
        with patch("twincat_automation_interface._discover_registered_prog_ids",
                    return_value=REGISTERED):
            assert _normalize_xae_version("4026") == PROG_4026

    def test_4024_alias(self):
        with patch("twincat_automation_interface._discover_registered_prog_ids",
                    return_value=REGISTERED):
            assert _normalize_xae_version("4024") == PROG_4024

    def test_vs_suffix(self):
        with patch("twincat_automation_interface._discover_registered_prog_ids",
                    return_value=REGISTERED):
            assert _normalize_xae_version("17.0") == PROG_4026
            assert _normalize_xae_version("15.0") == PROG_4024

    def test_full_prog_id(self):
        with patch("twincat_automation_interface._discover_registered_prog_ids",
                    return_value=REGISTERED):
            assert _normalize_xae_version(PROG_4024) == PROG_4024

    def test_empty_returns_none(self):
        assert _normalize_xae_version("") is None
        assert _normalize_xae_version(None) is None
        assert _normalize_xae_version("  ") is None

    def test_unknown_raises(self):
        with patch("twincat_automation_interface._discover_registered_prog_ids",
                    return_value=REGISTERED):
            with pytest.raises(ValueError, match="Unknown XAE version"):
                _normalize_xae_version("9999")

    def test_tc_version_label(self):
        assert _tc_version_label(PROG_4026) == "4026"
        assert _tc_version_label(PROG_4024) == "4024"
        assert _tc_version_label(None) == ""


# ==================================================================
# ROT find by solution
# ==================================================================

class TestFindDteBySolution:
    def test_finds_matching_among_multiple(self):
        """GetActiveObject would see wrong instance; ROT finds the right one."""
        bridge = _make_bridge()
        wrong = _fake_dte(r"C:\proj\Wrong.sln")
        right = _fake_dte(r"C:\proj\Target.sln")

        rot_entries = [
            (PROG_4026, f"!{PROG_4026}:111", wrong),
            (PROG_4024, f"!{PROG_4024}:222", right),
        ]

        with patch.object(bridge, "_enumerate_rot_dtes",
                          return_value=rot_entries):
            with patch("twincat_automation_interface._canonical_path",
                       side_effect=lambda p: p.lower()):
                prog_id, dte = bridge._find_dte_by_solution(
                    r"c:\proj\target.sln",
                )

        assert dte is right
        assert prog_id == PROG_4024

    def test_filter_by_prog_id(self):
        bridge = _make_bridge()
        dte_4026 = _fake_dte(r"C:\proj\A.sln")
        dte_4024 = _fake_dte(r"C:\proj\A.sln")
        rot_entries = [
            (PROG_4026, f"!{PROG_4026}:1", dte_4026),
            (PROG_4024, f"!{PROG_4024}:2", dte_4024),
        ]

        def _enum(filt=None):
            for e in rot_entries:
                if filt is None or e[0] == filt:
                    yield e

        with patch.object(bridge, "_enumerate_rot_dtes", side_effect=_enum):
            with patch("twincat_automation_interface._canonical_path",
                       side_effect=lambda p: p.lower()):
                prog_id, dte = bridge._find_dte_by_solution(
                    r"c:\proj\a.sln", PROG_4024,
                )

        assert dte is dte_4024
        assert prog_id == PROG_4024

    def test_empty_instance_found(self):
        bridge = _make_bridge()
        busy = _fake_dte(r"C:\proj\Busy.sln")
        empty = _fake_dte("", is_open=False)
        rot_entries = [
            (PROG_4026, f"!{PROG_4026}:1", busy),
            (PROG_4024, f"!{PROG_4024}:2", empty),
        ]

        with patch.object(bridge, "_enumerate_rot_dtes",
                          return_value=rot_entries):
            prog_id, dte = bridge._find_empty_dte(PROG_4024)

        assert dte is empty
        assert prog_id == PROG_4024


# ==================================================================
# Prefer running version for new instance
# ==================================================================

class TestPreferRunningProgId:
    def test_prefers_running_4024_over_newest_registered(self):
        """Only 4024 running -> new instance must use 4024, not 4026."""
        bridge = _make_bridge()
        dte = _fake_dte(r"C:\other\Other.sln")

        with patch.object(bridge, "_enumerate_rot_dtes",
                          return_value=[(PROG_4024, f"!{PROG_4024}:1", dte)]):
            with patch("twincat_automation_interface._discover_registered_prog_ids",
                       return_value=REGISTERED):
                result = bridge._prefer_running_prog_id()

        assert result == PROG_4024

    def test_explicit_preferred_wins(self):
        bridge = _make_bridge()
        assert bridge._prefer_running_prog_id(PROG_4026) == PROG_4026

    def test_none_when_nothing_running(self):
        bridge = _make_bridge()
        with patch.object(bridge, "_enumerate_rot_dtes", return_value=[]):
            assert bridge._prefer_running_prog_id() is None


# ==================================================================
# open_solution: attach to matching ROT instance instead of creating
# ==================================================================

class TestOpenSolutionMultiInstance:
    def test_attaches_to_matching_rot_not_create_new(self):
        bridge = _make_bridge()
        wrong = _fake_dte(r"C:\proj\Wrong.sln")
        right = _fake_dte(r"C:\proj\Target.sln")
        target = r"C:\proj\Target.sln"

        plc = MagicMock(Name="TargetPLC")

        def _enum(filt=None):
            entries = [
                (PROG_4026, f"!{PROG_4026}:1", wrong),
                (PROG_4024, f"!{PROG_4024}:2", right),
            ]
            for e in entries:
                if filt is None or e[0] == filt:
                    yield e

        with patch("twincat_automation_interface._canonical_path",
                   side_effect=lambda p: p.lower()):
            with patch("twincat_automation_interface.os.path.isfile",
                       return_value=True):
                with patch.object(bridge, "_prune_stale_instances"):
                    with patch.object(bridge, "_enumerate_rot_dtes",
                                      side_effect=_enum):
                        with patch.object(bridge, "_restore_from_registry",
                                          return_value=False):
                            with patch.object(bridge, "_try_get_active_dte",
                                              return_value=wrong):
                                with patch.object(
                                    bridge, "_create_new_dte",
                                ) as create_new:
                                    with patch.object(
                                        bridge, "_get_system_manager",
                                        return_value=MagicMock(),
                                    ):
                                        with patch.object(
                                            bridge,
                                            "_find_plc_project_with_retry",
                                            return_value=plc,
                                        ):
                                            with patch.object(
                                                bridge,
                                                "_save_active_to_registry",
                                            ):
                                                with patch.object(
                                                    bridge,
                                                    "_detect_plcproj_path",
                                                    return_value=None,
                                                ):
                                                    with patch.object(
                                                        bridge,
                                                        "_ensure_silent_mode",
                                                    ):
                                                        result = (
                                                            bridge._impl_open_solution(
                                                                target, None,
                                                                None, 60,
                                                            )
                                                        )

        assert result.success is True
        assert bridge._dte is right
        assert bridge._prog_id == PROG_4024
        assert result.xae_version == "4024"
        assert result.created_new_instance is False
        create_new.assert_not_called()

    def test_unknown_version_returns_error(self):
        bridge = _make_bridge()
        with patch("twincat_automation_interface._discover_registered_prog_ids",
                    return_value=REGISTERED):
            result = bridge._impl_open_solution(
                r"C:\proj\A.sln", None, None, 60, xae_version="9999",
            )
        assert result.success is False
        assert "Unknown XAE version" in result.message

    def test_create_uses_running_version(self):
        """No matching solution; only 4024 running -> create 4024, not 4026."""
        bridge = _make_bridge()
        other = _fake_dte(r"C:\proj\Other.sln")
        target = r"C:\proj\Target.sln"
        new_dte = _fake_dte(target)
        plc = MagicMock(Name="TargetPLC")

        def _enum(filt=None):
            entries = [(PROG_4024, f"!{PROG_4024}:1", other)]
            for e in entries:
                if filt is None or e[0] == filt:
                    yield e

        with patch("twincat_automation_interface._canonical_path",
                   side_effect=lambda p: p.lower()):
            with patch("twincat_automation_interface.os.path.isfile",
                       return_value=True):
                with patch("twincat_automation_interface._discover_registered_prog_ids",
                           return_value=REGISTERED):
                    with patch.object(bridge, "_prune_stale_instances"):
                        with patch.object(bridge, "_enumerate_rot_dtes",
                                          side_effect=_enum):
                            with patch.object(bridge, "_restore_from_registry",
                                              return_value=False):
                                with patch.object(bridge, "_try_get_active_dte",
                                                  return_value=other):
                                    with patch.object(
                                        bridge, "_create_new_dte",
                                        return_value=new_dte,
                                    ) as create_new:
                                        with patch.object(
                                            bridge, "_get_system_manager",
                                            return_value=MagicMock(),
                                        ):
                                            with patch.object(
                                                bridge,
                                                "_find_plc_project_with_retry",
                                                return_value=plc,
                                            ):
                                                with patch.object(
                                                    bridge,
                                                    "_save_active_to_registry",
                                                ):
                                                    with patch.object(
                                                        bridge,
                                                        "_detect_plcproj_path",
                                                        return_value=None,
                                                    ):
                                                        # After create, _dte is set by create mock side
                                                        def _create(sln, t, prog_id=None):
                                                            bridge._dte = new_dte
                                                            bridge._prog_id = prog_id
                                                            bridge._created_new = True
                                                            return new_dte
                                                        create_new.side_effect = _create

                                                        result = bridge._impl_open_solution(
                                                            target, None, None, 60,
                                                        )

        assert result.success is True
        create_new.assert_called_once()
        assert create_new.call_args.kwargs.get("prog_id") == PROG_4024
        assert result.xae_version == "4024"

    def test_explicit_4026_passed_to_create(self):
        bridge = _make_bridge()
        target = r"C:\proj\Target.sln"
        new_dte = _fake_dte(target)
        plc = MagicMock(Name="P")

        with patch("twincat_automation_interface._canonical_path",
                   side_effect=lambda p: p.lower()):
            with patch("twincat_automation_interface.os.path.isfile",
                       return_value=True):
                with patch("twincat_automation_interface._discover_registered_prog_ids",
                           return_value=REGISTERED):
                    with patch.object(bridge, "_prune_stale_instances"):
                        with patch.object(bridge, "_enumerate_rot_dtes",
                                          return_value=[]):
                            with patch.object(bridge, "_restore_from_registry",
                                              return_value=False):
                                with patch.object(bridge, "_try_get_active_dte",
                                                  return_value=None):
                                    with patch.object(
                                        bridge, "_create_new_dte",
                                    ) as create_new:
                                        def _create(sln, t, prog_id=None):
                                            bridge._dte = new_dte
                                            bridge._prog_id = prog_id
                                            bridge._created_new = True
                                            return new_dte
                                        create_new.side_effect = _create
                                        with patch.object(
                                            bridge, "_get_system_manager",
                                            return_value=MagicMock(),
                                        ):
                                            with patch.object(
                                                bridge,
                                                "_find_plc_project_with_retry",
                                                return_value=plc,
                                            ):
                                                with patch.object(
                                                    bridge,
                                                    "_save_active_to_registry",
                                                ):
                                                    with patch.object(
                                                        bridge,
                                                        "_detect_plcproj_path",
                                                        return_value=None,
                                                    ):
                                                        result = bridge._impl_open_solution(
                                                            target, None, None, 60,
                                                            xae_version="4026",
                                                        )

        assert result.success is True
        assert create_new.call_args.kwargs.get("prog_id") == PROG_4026

    def test_switch_with_xae_version_preserves_registry_prog_id(self):
        """Solution switch with xae_version must not pollute registry prog_id.

        Regression: early _ensure_prog_id(preferred) overwrote self._prog_id
        before saving the active session, so re-attach without xae_version
        reported the wrong shell version.
        """
        bridge = _make_bridge()
        ba_sln = r"C:\proj\BA.sln"
        sample_sln = r"C:\proj\Sample.sln"
        ba_dte = _fake_dte(ba_sln)
        sample_dte = _fake_dte(sample_sln)
        ba_plc = MagicMock(Name="BA")
        sample_plc = MagicMock(Name="SamplePLC")

        # Active session: BA on 4024
        bridge._dte = ba_dte
        bridge._prog_id = PROG_4024
        bridge._sln_path = ba_sln
        bridge._sys_man = MagicMock()
        bridge._plc_proj_item = ba_plc
        bridge._created_new = False

        def _enum(filt=None):
            entries = [
                (PROG_4024, f"!{PROG_4024}:1", ba_dte),
                (PROG_4026, f"!{PROG_4026}:2", sample_dte),
            ]
            for e in entries:
                if filt is None or e[0] == filt:
                    yield e

        with patch("twincat_automation_interface._canonical_path",
                   side_effect=lambda p: p.lower()):
            with patch("twincat_automation_interface.os.path.isfile",
                       return_value=True):
                with patch("twincat_automation_interface._discover_registered_prog_ids",
                           return_value=REGISTERED):
                    with patch.object(bridge, "_prune_stale_instances"):
                        with patch.object(bridge, "_enumerate_rot_dtes",
                                          side_effect=_enum):
                            with patch.object(
                                bridge, "_get_system_manager",
                                return_value=MagicMock(),
                            ):
                                with patch.object(
                                    bridge, "_find_plc_project_with_retry",
                                    return_value=sample_plc,
                                ):
                                    with patch.object(
                                        bridge, "_detect_plcproj_path",
                                        return_value=None,
                                    ):
                                        with patch.object(
                                            bridge, "_ensure_silent_mode",
                                        ):
                                            with patch.object(
                                                bridge, "_create_new_dte",
                                            ) as create_new:
                                                result = bridge._impl_open_solution(
                                                    sample_sln, None, None, 60,
                                                    xae_version="4026",
                                                )

        assert result.success is True
        assert bridge._prog_id == PROG_4026
        assert result.xae_version == "4026"
        create_new.assert_not_called()

        # BA must have been saved with its real shell (4024), not preferred 4026
        ba_key = ba_sln.lower()
        assert ba_key in bridge._instances
        assert bridge._instances[ba_key]["prog_id"] == PROG_4024

        # Re-attach to BA without xae_version → report 4024, not 4026
        with patch("twincat_automation_interface._canonical_path",
                   side_effect=lambda p: p.lower()):
            with patch("twincat_automation_interface.os.path.isfile",
                       return_value=True):
                with patch.object(bridge, "_prune_stale_instances"):
                    with patch.object(
                        bridge, "_get_system_manager",
                        return_value=MagicMock(),
                    ):
                        with patch.object(
                            bridge, "_find_plc_project_with_retry",
                            return_value=ba_plc,
                        ):
                            with patch.object(
                                bridge, "_detect_plcproj_path",
                                return_value=None,
                            ):
                                with patch.object(
                                    bridge, "_ensure_silent_mode",
                                ):
                                    result2 = bridge._impl_open_solution(
                                        ba_sln, None, None, 60,
                                    )

        assert result2.success is True
        assert bridge._prog_id == PROG_4024
        assert result2.xae_version == "4024"
        assert result2.xae_prog_id == PROG_4024


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
