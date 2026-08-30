"""Unit tests for runtime message classification."""
from __future__ import annotations

import os
import sys
import unittest

_AI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "automation_interface",
)
if _AI not in sys.path:
    sys.path.insert(0, _AI)

from runtime_messages import (
    classify_runtime_text,
    looks_like_activate_canceled,
    text_since_baseline,
)


class TestClassifyRuntimeText(unittest.TestCase):
    def test_page_fault_and_license(self):
        text = (
            "08.08.2026 | TwinCAT System: page fault in PLC task\n"
            "Error: >> license not found << checking TwinCAT Licenses!\n"
            "SAFEOP AdsError: 1823 (0x71f)\n"
        )
        findings = classify_runtime_text(text)
        ids = {f["id"] for f in findings}
        self.assertIn("page_fault", ids)
        self.assertIn("license", ids)
        self.assertIn("safeop_aborted", ids)

    def test_empty(self):
        self.assertEqual(classify_runtime_text(""), [])

    def test_activate_canceled(self):
        self.assertTrue(looks_like_activate_canceled(
            "activating configuration canceled"
        ))

    def test_since_baseline(self):
        self.assertEqual(text_since_baseline("abcdef", 3), "def")


if __name__ == "__main__":
    unittest.main()
