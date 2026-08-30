"""Tests for confirm_refused, readiness, activate cancel phrases, library verify."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AI = os.path.join(_ROOT, "automation_interface")
for p in (_ROOT, _AI):
    if p not in sys.path:
        sys.path.insert(0, p)

from mcp_errors import confirm_refused
from readiness import compose_readiness
from library_verify import verify_library_versions
from runtime_messages import (
    looks_like_activate_canceled,
    text_since_baseline,
    severity_summary,
    infer_build_outcome,
)
from user_actions import umrt_activate_actions, attach_user_actions


class TestConfirmRefused(unittest.TestCase):
    def test_shape(self):
        data = confirm_refused(
            "twincat_activate",
            example_args={"confirm": True},
        )
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "confirm_required")
        self.assertEqual(data["required_args"], ["confirm"])
        self.assertTrue(data["example_next_call"]["confirm"])
        self.assertIn("confirm=true", data["error"].lower())


class TestReadiness(unittest.TestCase):
    def test_ready_when_both_run(self):
        r = compose_readiness(
            system_ads_state="RUN",
            plc_ads_state="RUN",
            plc_port=851,
        )
        self.assertTrue(r["ready_for_ads"])
        self.assertEqual(r["blocking_reasons"], [])

    def test_not_ready_system_only(self):
        r = compose_readiness(
            system_ads_state="RUN",
            plc_ads_state="INVALID",
        )
        self.assertFalse(r["ready_for_ads"])
        self.assertTrue(any("plc" in x for x in r["blocking_reasons"]))


class TestRuntimeMessageHelpers(unittest.TestCase):
    def test_cancel_phrase(self):
        self.assertTrue(looks_like_activate_canceled(
            "activating configuration canceled"
        ))
        self.assertTrue(looks_like_activate_canceled("value out of range"))
        self.assertFalse(looks_like_activate_canceled("ActivateConfiguration OK"))

    def test_baseline_window(self):
        full = "old\n" + ("x" * 10) + "\nnew line"
        win = text_since_baseline(full, len("old\n") + 10)
        self.assertIn("new line", win)
        self.assertNotIn("old", win)

    def test_severity_and_build(self):
        findings = [
            {"id": "page_fault", "severity": "error"},
            {"id": "x", "severity": "warning"},
        ]
        self.assertEqual(severity_summary(findings)["error_count"], 1)
        self.assertEqual(infer_build_outcome("activating configuration canceled"), "failed")


class TestUarPolicy(unittest.TestCase):
    def test_no_trial_without_license_error(self):
        ids = umrt_activate_actions(license_error=False, include_io=True)
        self.assertNotIn("umrt_trial_license", ids)
        self.assertIn("umrt_io_disabled", ids)

    def test_trial_only_on_license_error(self):
        ids = umrt_activate_actions(license_error=True, include_io=False)
        self.assertEqual(ids, ["umrt_trial_license"])

    def test_attach_without_trial_on_clean_umrt(self):
        data = attach_user_actions(
            {"success": True, "message": "OK"},
            *umrt_activate_actions(license_error=False, include_io=False),
        )
        self.assertNotIn("user_action_required", data)


class TestLibraryVerify(unittest.TestCase):
    def test_incomplete_without_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = verify_library_versions(
                expected_version="1.6.1.0",
                library_name="Tc3_ExampleLib",
                search_roots=[tmp],
            )
            self.assertTrue(r["verify_incomplete"])
            self.assertFalse(r["ok"])
            self.assertIn("refresh_references", r["next_actions"])

    def test_match_in_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib = os.path.join(tmp, "_Libraries")
            os.makedirs(lib)
            open(os.path.join(lib, "Tc3_ExampleLib_1.6.1.0.compiled-library"), "wb").close()
            r = verify_library_versions(
                expected_version="1.6.1.0",
                library_name="Tc3_ExampleLib",
                search_roots=[tmp],
            )
            self.assertTrue(r["ok"])
            self.assertIn("1.6.1.0", r["boot_library_versions"])


if __name__ == "__main__":
    unittest.main()
