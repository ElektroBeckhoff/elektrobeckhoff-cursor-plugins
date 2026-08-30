"""Unit tests for MCP user_action_required prompts."""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from user_actions import (
    ACTION_NON_UMRT_TARGET,
    ACTION_TRIAL_LICENSE,
    attach_non_umrt_target_warning,
    attach_user_actions,
    looks_like_license_error,
    umrt_activate_actions,
)


class TestLicenseDetection(unittest.TestCase):
    def test_markers(self):
        self.assertTrue(looks_like_license_error(
            "Error: >> license not found << checking TwinCAT Licenses!"
        ))
        self.assertTrue(looks_like_license_error(
            "License Violation: License 'TC3 PLC' not found"
        ))
        self.assertFalse(looks_like_license_error("ActivateConfiguration OK"))


class TestAttachActions(unittest.TestCase):
    def test_umrt_start_prompts(self):
        data = attach_user_actions(
            {"success": True, "message": "Started UmRT"},
            "umrt_trial_license",
            "umrt_io_disabled",
        )
        ids = [a["id"] for a in data["user_action_required"]]
        self.assertIn("umrt_trial_license", ids)
        self.assertIn("umrt_io_disabled", ids)
        self.assertTrue(data["user_action_required"][0]["ask_user"])
        self.assertIn("USER ACTION REQUIRED", data["message"])

    def test_activate_actions_skip_trial_without_error(self):
        ids = umrt_activate_actions(license_error=False, include_io=True)
        self.assertNotIn(ACTION_TRIAL_LICENSE["id"], ids)

    def test_auto_on_license_error(self):
        data = attach_user_actions(
            {"success": False, "message": "license not found"},
        )
        self.assertTrue(data.get("license_error_detected"))
        self.assertEqual(
            data["user_action_required"][0]["id"],
            ACTION_TRIAL_LICENSE["id"],
        )


class TestNonUmrtTargetWarning(unittest.TestCase):
    def test_warns_on_external_target(self):
        data = attach_non_umrt_target_warning(
            {"success": True, "message": "Started"},
            operation="twincat_start",
            target_net_id="172.16.17.10.1.1",
            mcp_umrt_net_id="199.5.42.250.1.1",
            mcp_umrt_running=True,
            target_is_mcp_umrt=False,
        )
        self.assertFalse(data["target_is_mcp_umrt"])
        self.assertEqual(data["target_net_id"], "172.16.17.10.1.1")
        self.assertTrue(any("SAFETY" in w for w in data["warnings"]))
        self.assertIn("WARNING: non-UmRT target control", data["message"])
        ids = [a["id"] for a in data["user_action_required"]]
        self.assertIn(ACTION_NON_UMRT_TARGET["id"], ids)
        self.assertTrue(data["user_action_required"][0]["ask_user"])

    def test_silent_when_mcp_umrt(self):
        data = attach_non_umrt_target_warning(
            {"success": True, "message": "Started"},
            operation="twincat_start",
            target_net_id="199.5.42.250.1.1",
            mcp_umrt_net_id="199.5.42.250.1.1",
            mcp_umrt_running=True,
            target_is_mcp_umrt=True,
        )
        self.assertTrue(data["target_is_mcp_umrt"])
        self.assertNotIn("warnings", data)
        self.assertNotIn("user_action_required", data)
        self.assertEqual(data["message"], "Started")


if __name__ == "__main__":
    unittest.main()
