"""Regression: critical MCP tools must stay registered on FastMCP."""
from __future__ import annotations

import unittest


REQUIRED_TOOLS = {
    "twincat_format_code",
    "twincat_format_progress",
    "twincat_format_cancel",
    "twincat_export_library",
    "twincat_export_progress",
    "twincat_export_check_artifacts",
    "twincat_dismiss_safe_dialogs",
    "twincat_status",
}


class TestMcpToolRegistration(unittest.TestCase):
    def test_required_tools_registered(self):
        import server as srv

        names = set()
        # FastMCP stores tools in _tool_manager._tools (name -> Tool)
        mgr = getattr(srv.mcp, "_tool_manager", None)
        if mgr is not None:
            tools = getattr(mgr, "_tools", None) or {}
            names.update(tools.keys())
        # Fallback: public attribute used by some versions
        if not names and hasattr(srv.mcp, "_tools"):
            names.update(getattr(srv.mcp, "_tools", {}).keys())
        missing = REQUIRED_TOOLS - names
        self.assertFalse(
            missing,
            f"MCP tools not registered: {sorted(missing)}; have={sorted(names)}",
        )


if __name__ == "__main__":
    unittest.main()
