"""Unit tests for UmRT systemtest chain (mocked backends — no TwinCAT)."""
from __future__ import annotations

import unittest

from umrt_chain import (
    BLOCKING_FINDING_IDS,
    SystemtestBackends,
    SystemtestConfig,
    run_umrt_systemtest,
)


def _ok(**extra):
    d = {"success": True, "message": "ok"}
    d.update(extra)
    return d


def _fail(msg="fail", **extra):
    d = {"success": False, "error": msg, "message": msg}
    d.update(extra)
    return d


class FakeBackends:
    """Mutable fake wired into SystemtestBackends."""

    def __init__(self):
        self.net_id = "199.5.42.250.1.1"
        self.plc_ads = "ADSSTATE_INVALID"
        self.sys_ads = "ADSSTATE_RUN"
        self.messages_findings: list = []
        self.activate_findings: list = []
        self.values = {
            "P_Sample.fbX._bFlag": True,
            "P_Sample.stControl.bOn": False,
        }
        self.write_store: dict = {}
        self.calls: list[str] = []

    def backends(self) -> SystemtestBackends:
        f = self

        def umrt_status():
            f.calls.append("umrt_status")
            return _ok(mcp_ams_net_id=f.net_id)

        def umrt_start(confirm=False, window_mode="hidden"):
            f.calls.append("umrt_start")
            assert confirm is True
            return _ok(ams_net_id=f.net_id, window_mode=window_mode)

        def open_solution(sln_path="", xae_version=None, **_kw):
            f.calls.append("open")
            return _ok(solution_path=sln_path, plc_project_name="Sample", xae_version=xae_version)

        def io_set_disabled(all_devices=True, disabled=True, confirm=False, **_kw):
            f.calls.append("io")
            assert confirm and all_devices and disabled
            return _ok(updated=["TIID^Device 1"])

        def set_target(net_id="", confirm=False):
            f.calls.append("set_target")
            assert confirm and net_id == f.net_id
            return _ok(net_id=net_id)

        def get_target():
            return _ok(net_id=f.net_id)

        def activate(confirm=False):
            f.calls.append("activate")
            assert confirm
            r = _ok()
            if f.activate_findings:
                r["runtime_findings"] = f.activate_findings
                r["has_blocking_runtime_error"] = True
                r["success"] = False
            return r

        def start_twincat(confirm=False):
            f.calls.append("start")
            assert confirm
            return _ok()

        def runtime_messages(max_chars=12000):
            f.calls.append("messages")
            findings = list(f.messages_findings)
            return {
                "success": True,
                "findings": findings,
                "has_blocking_error": bool(
                    BLOCKING_FINDING_IDS.intersection(
                        {x.get("id") for x in findings if isinstance(x, dict)}
                    )
                ),
            }

        def runtime_state(net_id="", port=10000):
            f.calls.append(f"state:{port}")
            if port == 10000:
                return _ok(ads_state=f.sys_ads, net_id=net_id, port=port)
            return _ok(ads_state=f.plc_ads, net_id=net_id, port=port)

        def plc_start(net_id="", port=851, confirm=False):
            f.calls.append("plc_start")
            assert confirm
            f.plc_ads = "ADSSTATE_RUN"
            return _ok(ads_state="ADSSTATE_RUN", net_id=net_id, port=port)

        def ads_symbols(net_id="", port=851, prefix="", max_symbols=50, **_kw):
            f.calls.append("symbols")
            return _ok(symbols=[
                {"name": "P_Sample.fbX", "type": "FB_X"},
                {"name": "P_Sample.stControl", "type": "ST_Ctrl"},
            ])

        def ads_read_list(symbols=None, net_id="", port=851, **_kw):
            f.calls.append("read_list")
            vals = {s: f.values.get(s, 0) for s in (symbols or [])}
            return _ok(values=vals)

        def ads_write(symbol="", value="", plc_type="", net_id="", port=851, confirm=False):
            f.calls.append("write")
            assert confirm
            f.write_store[symbol] = value
            f.values[symbol] = value in ("true", "True", "1") if isinstance(value, str) else value
            return _ok(symbol=symbol, value=value)

        def ads_read(symbol="", net_id="", port=851):
            f.calls.append("read")
            return _ok(symbol=symbol, value=f.values.get(symbol))

        def check_licenses(instance=None, net_id=""):
            f.calls.append("check_licenses")
            if hasattr(f, "licenses_result"):
                return f.licenses_result
            return _ok(licenses_ok=True)

        return SystemtestBackends(
            umrt_status=umrt_status,
            umrt_start=umrt_start,
            open_solution=open_solution,
            io_set_disabled=io_set_disabled,
            set_target=set_target,
            get_target=get_target,
            activate=activate,
            start_twincat=start_twincat,
            runtime_messages=runtime_messages,
            runtime_state=runtime_state,
            plc_start=plc_start,
            ads_symbols=ads_symbols,
            ads_read_list=ads_read_list,
            ads_write=ads_write,
            ads_read=ads_read,
            check_licenses=check_licenses,
        )


class TestUmrtSystemtestPass(unittest.TestCase):
    def test_full_chain_pass(self):
        fake = FakeBackends()
        cfg = SystemtestConfig(
            sln_path=r"C:\sample\Sample.sln",
            settle_s=0,
            read_symbols=[
                "P_Sample.fbX._bFlag",
                "P_Sample.stControl.bOn",
            ],
            write_symbol="P_Sample.stControl.bOn",
            write_value="true",
        )
        report = run_umrt_systemtest(cfg, fake.backends())
        self.assertTrue(report.passed, report.format_checklist())
        self.assertEqual(report.net_id, fake.net_id)
        self.assertIn("plc_start", fake.calls)
        self.assertIn("read_list", fake.calls)
        self.assertIn("write", fake.calls)
        checklist = report.format_checklist()
        self.assertIn("Overall: PASS", checklist)

    def test_plc_already_run_skips_plc_start(self):
        fake = FakeBackends()
        fake.plc_ads = "ADSSTATE_RUN"
        cfg = SystemtestConfig(
            sln_path=r"C:\sample\Sample.sln",
            settle_s=0,
            read_symbols=["P_Sample.fbX._bFlag"],
            skip_write=True,
        )
        report = run_umrt_systemtest(cfg, fake.backends())
        self.assertTrue(report.passed, report.format_checklist())
        self.assertNotIn("plc_start", fake.calls)


class TestUmrtSystemtestFailFast(unittest.TestCase):
    def test_missing_license_preflight_blocks_early(self):
        fake = FakeBackends()
        fake.licenses_result = {
            "success": False,
            "licenses_ok": False,
            "missing_trial_license": True,
            "message": "No active license files found in UmRT Target/License folder.",
        }
        cfg = SystemtestConfig(
            sln_path=r"C:\sample\Sample.sln",
            settle_s=0,
            read_symbols=["P_Sample.fbX._bFlag"],
            skip_write=True,
        )
        report = run_umrt_systemtest(cfg, fake.backends())
        self.assertFalse(report.passed)
        self.assertFalse(report.step("license_preflight").passed)
        self.assertIsNone(report.step("open"))
        self.assertTrue(any("trial license" in a.lower() for a in report.ask_user))

    def test_license_blocks_after_messages(self):
        fake = FakeBackends()
        fake.messages_findings = [{
            "id": "license",
            "severity": "error",
            "matched_line": "License not found",
        }]
        cfg = SystemtestConfig(
            sln_path=r"C:\sample\Sample.sln",
            settle_s=0,
            read_symbols=["P_Sample.fbX._bFlag"],
            skip_write=True,
        )
        report = run_umrt_systemtest(cfg, fake.backends())
        self.assertFalse(report.passed)
        self.assertFalse(report.step("runtime_messages").passed)
        self.assertIsNone(report.step("ads_read"))
        self.assertTrue(any("license" in a.lower() or "runtime" in a.lower()
                            for a in report.ask_user))

    def test_umrt_start_fail(self):
        fake = FakeBackends()
        backends = fake.backends()
        backends.umrt_start = lambda **_kw: _fail("not installed")
        cfg = SystemtestConfig(
            sln_path=r"C:\sample\Sample.sln",
            settle_s=0,
            read_symbols=["x"],
            skip_write=True,
        )
        report = run_umrt_systemtest(cfg, backends)
        self.assertFalse(report.passed)
        self.assertFalse(report.step("umrt_start").passed)
        self.assertIsNone(report.step("open"))

    def test_safeop_on_activate(self):
        fake = FakeBackends()
        fake.activate_findings = [{
            "id": "safeop_aborted",
            "severity": "error",
            "matched_line": "AdsError: 1823",
        }]
        cfg = SystemtestConfig(
            sln_path=r"C:\sample\Sample.sln",
            settle_s=0,
            read_symbols=["x"],
            skip_write=True,
        )
        report = run_umrt_systemtest(cfg, fake.backends())
        self.assertFalse(report.passed)
        self.assertFalse(report.step("activate").passed)
        self.assertIsNone(report.step("start"))


if __name__ == "__main__":
    unittest.main()
