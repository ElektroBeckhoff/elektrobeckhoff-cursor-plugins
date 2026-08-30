"""Unit tests for TwinCAT Usermode Runtime controller."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import twincat_umrt_controller as umrt
from twincat_umrt_controller import (
    MCP_INSTANCE_PREFIX,
    UmrtController,
    bin_hex_to_ams_net_id,
    parse_ams_net_id_from_registry_xml,
    resolve_session_instance_name,
)


SAMPLE_REGISTRY = """<?xml version="1.0"?>
<TcRegistry>
  <Key Name="HKLM">
    <Key Name="Software">
      <Key Name="Beckhoff">
        <Key Name="TwinCAT3">
          <Key Name="System">
            <Value Name="AmsNetId" Type="BIN">C7042AFA0101</Value>
          </Key>
        </Key>
      </Key>
    </Key>
  </Key>
</TcRegistry>
"""


class TestAmsNetIdParse(unittest.TestCase):
    def test_bin_hex(self):
        self.assertEqual(bin_hex_to_ams_net_id("C7042AFA0101"), "199.4.42.250.1.1")

    def test_from_xml(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "TcRegistry.xml"
            p.write_text(SAMPLE_REGISTRY, encoding="utf-8")
            self.assertEqual(
                parse_ams_net_id_from_registry_xml(str(p)),
                "199.4.42.250.1.1",
            )


class TestPathResolution(unittest.TestCase):
    def test_twincat3dir_wins(self):
        with patch.dict(os.environ, {"TWINCAT3DIR": r"C:\Fake\TwinCAT\3.1\\"}, clear=False):
            with patch.object(umrt.os.path, "isdir", return_value=True):
                root = umrt.resolve_twincat_root()
        self.assertEqual(root, os.path.normpath(r"C:\Fake\TwinCAT\3.1"))


class TestSessionInstanceName(unittest.TestCase):
    def test_env_wins(self):
        with patch.dict(
            os.environ,
            {"TWINCAT_UMRT_INSTANCE": "UmRT_MySession", "TWINCAT_UMRT_SESSION_MODE": "workspace"},
            clear=False,
        ):
            name, src = resolve_session_instance_name()
        self.assertEqual(name, "UmRT_MySession")
        self.assertEqual(src, "env")

    def test_workspace_stable(self):
        env = {
            k: v for k, v in os.environ.items()
            if k not in ("TWINCAT_UMRT_INSTANCE", "TWINCAT_UMRT_SESSION_MODE")
        }
        env["CURSOR_PROJECT_DIR"] = r"C:\Work\ProjectAlpha"
        env["TWINCAT_UMRT_SESSION_MODE"] = "workspace"
        with patch.dict(os.environ, env, clear=True):
            n1, s1 = resolve_session_instance_name()
            n2, s2 = resolve_session_instance_name()
        self.assertEqual(s1, "workspace")
        self.assertEqual(n1, n2)
        self.assertTrue(n1.startswith(MCP_INSTANCE_PREFIX + "_"))
        self.assertIn("projectalpha", n1.lower())

    def test_different_workspaces_differ(self):
        env_base = {
            k: v for k, v in os.environ.items()
            if k not in ("TWINCAT_UMRT_INSTANCE", "CURSOR_PROJECT_DIR")
        }
        env_base["TWINCAT_UMRT_SESSION_MODE"] = "workspace"
        with patch.dict(os.environ, {**env_base, "CURSOR_PROJECT_DIR": r"C:\A"}, clear=True):
            a, _ = resolve_session_instance_name()
        with patch.dict(os.environ, {**env_base, "CURSOR_PROJECT_DIR": r"C:\B"}, clear=True):
            b, _ = resolve_session_instance_name()
        self.assertNotEqual(a, b)

    def test_pid_mode(self):
        env = {
            k: v for k, v in os.environ.items()
            if k != "TWINCAT_UMRT_INSTANCE"
        }
        env["TWINCAT_UMRT_SESSION_MODE"] = "pid"
        with patch.dict(os.environ, env, clear=True):
            name, src = resolve_session_instance_name()
        self.assertEqual(src, "pid")
        self.assertIn(f"p{os.getpid()}", name)

    def test_controller_uses_session_name(self):
        with patch.dict(
            os.environ, {"TWINCAT_UMRT_INSTANCE": "UmRT_CtrlTest"}, clear=False,
        ):
            ctrl = UmrtController()
        self.assertEqual(ctrl.mcp_instance, "UmRT_CtrlTest")
        self.assertEqual(ctrl.mcp_instance_source, "env")


class TestEnsureInstance(unittest.TestCase):
    def test_copies_template(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            template = Path(td) / "UmRT_Template"
            template.mkdir()
            (template / "Start.bat").write_text("@echo off\n", encoding="utf-8")
            (template / "3.1").mkdir()
            (template / "3.1" / "TcRegistry.xml").write_text(
                SAMPLE_REGISTRY, encoding="utf-8",
            )
            inst_root = Path(td) / "Runtimes"
            inst_root.mkdir()
            bin_exe = Path(td) / "bin" / "TcSystemServiceUm.exe"
            bin_exe.parent.mkdir()
            bin_exe.write_bytes(b"MZ")

            ctrl = UmrtController()
            with patch.object(umrt, "resolve_instances_root", return_value=str(inst_root)):
                with patch.object(umrt, "resolve_template_path", return_value=str(template)):
                    with patch.object(umrt, "resolve_umrt_bin", return_value=str(bin_exe)):
                        r = ctrl.ensure_instance("UmRT_CursorMCP")

            self.assertTrue(r.success)
            self.assertTrue(r.created_instance)
            self.assertTrue((inst_root / "UmRT_CursorMCP" / "Start.bat").is_file())
            self.assertEqual(r.ams_net_id, "199.4.42.250.1.1")

            # second call: already exists
            with patch.object(umrt, "resolve_instances_root", return_value=str(inst_root)):
                r2 = ctrl.ensure_instance("UmRT_CursorMCP")
            self.assertTrue(r2.success)
            self.assertFalse(r2.created_instance)


class TestConfirmGuards(unittest.TestCase):
    def test_start_requires_confirm(self):
        r = UmrtController().start(confirm=False)
        self.assertFalse(r.success)
        self.assertIn("confirm", r.message.lower())

    def test_stop_requires_confirm(self):
        r = UmrtController().stop(confirm=False)
        self.assertFalse(r.success)
        self.assertIn("confirm", r.message.lower())


class TestStartStopMocked(unittest.TestCase):
    def test_start_already_running(self):
        ctrl = UmrtController()
        with patch.object(ctrl, "ensure_instance") as ens:
            ens.return_value = umrt.UmrtOpResult(
                success=True, instance="UmRT_CursorMCP",
                ams_net_id="1.2.3.4.1.1",
            )
            with patch.object(umrt, "_match_instance_pid", return_value=4242):
                r = ctrl.start(confirm=True)
        self.assertTrue(r.success)
        self.assertEqual(r.pid, 4242)
        self.assertIn("Already running", r.message)

    def test_stop_terminates(self):
        ctrl = UmrtController()
        with patch.object(umrt, "_match_instance_pid", side_effect=[999, None]):
            with patch.object(umrt, "_terminate_pid", return_value=True) as term:
                r = ctrl.stop(instance="UmRT_CursorMCP", confirm=True)
        self.assertTrue(r.success)
        term.assert_called_once_with(999)


class TestAdsDefaultPrefersUmrt(unittest.TestCase):
    def test_resolve_prefers_running_mcp_umrt(self):
        import server as srv

        mock_umrt = MagicMock()
        mock_umrt.get_mcp_ams_net_id_if_running.return_value = "199.4.42.250.1.1"
        with patch.object(srv, "_get_umrt", return_value=mock_umrt):
            nid = srv._resolve_ads_net_id("")
        self.assertEqual(nid, "199.4.42.250.1.1")

    def test_explicit_wins(self):
        import server as srv

        mock_umrt = MagicMock()
        mock_umrt.get_mcp_ams_net_id_if_running.return_value = "199.4.42.250.1.1"
        with patch.object(srv, "_get_umrt", return_value=mock_umrt):
            nid = srv._resolve_ads_net_id("10.20.30.40.1.1")
        self.assertEqual(nid, "10.20.30.40.1.1")


class TestMcpToolsConfirm(unittest.TestCase):
    def test_umrt_start_confirm(self):
        import server as srv
        out = json.loads(srv.twincat_umrt_start(confirm=False))
        self.assertFalse(out["success"])
        self.assertEqual(out.get("error_code"), "confirm_required")
        self.assertIn("confirm", out.get("error", "").lower())
        # Trial license is NOT attached on confirm refusal (only on license errors)
        ids = [a["id"] for a in out.get("user_action_required", [])]
        self.assertNotIn("umrt_trial_license", ids)

    def test_umrt_stop_confirm(self):
        import server as srv
        out = json.loads(srv.twincat_umrt_stop(confirm=False))
        self.assertFalse(out["success"])
        self.assertEqual(out.get("error_code"), "confirm_required")

    def test_start_hidden_launches_exe(self):
        import tempfile
        ctrl = UmrtController()
        with tempfile.TemporaryDirectory() as td:
            inst = Path(td) / "UmRT_CursorMCP"
            inst.mkdir()
            (inst / "Start.bat").write_text("@echo off\n", encoding="utf-8")
            (inst / "3.1").mkdir()
            (inst / "3.1" / "TcRegistry.xml").write_text(
                SAMPLE_REGISTRY, encoding="utf-8",
            )
            exe = Path(td) / "TcSystemServiceUm.exe"
            exe.write_bytes(b"MZ")
            with patch.object(ctrl, "ensure_instance") as ens:
                ens.return_value = umrt.UmrtOpResult(
                    success=True, instance="UmRT_CursorMCP",
                    ams_net_id="199.4.42.250.1.1",
                )
                with patch.object(umrt, "_match_instance_pid", side_effect=[None, 5555]):
                    with patch.object(umrt, "resolve_instances_root", return_value=str(td)):
                        with patch.object(umrt, "resolve_twincat_root", return_value=str(td)):
                            with patch.object(umrt, "resolve_umrt_bin", return_value=str(exe)):
                                with patch.object(umrt.subprocess, "Popen") as popen:
                                    r = ctrl.start(
                                        instance="UmRT_CursorMCP",
                                        confirm=True,
                                        window_mode="hidden",
                                    )
            self.assertTrue(r.success)
            self.assertEqual(r.window_mode, "hidden")
            args = popen.call_args[0][0]
            self.assertTrue(str(args[0]).endswith("TcSystemServiceUm.exe"))
            self.assertIn("-n", args)

    def test_umrt_status_json(self):
        import server as srv
        mock = MagicMock()
        mock.status.return_value = umrt.UmrtStatusResult(
            success=True, installed=False, message="test",
        )
        with patch.object(srv, "_get_umrt", return_value=mock):
            out = json.loads(srv.twincat_umrt_status())
        self.assertTrue(out["success"])
        self.assertEqual(out["message"], "test")


if __name__ == "__main__":
    unittest.main()
