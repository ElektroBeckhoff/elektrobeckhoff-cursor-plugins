"""Tests for central persistent MCP logging module."""
import logging
import os
import tempfile
import unittest

from mcp_logging import resolve_log_path, setup_mcp_logging, get_log_path, get_recent_log_entries, get_mcp_server_version
from mcp_version import MCP_SERVER_VERSION


class TestMcpLogging(unittest.TestCase):
    def test_mcp_version(self):
        self.assertEqual(get_mcp_server_version(), MCP_SERVER_VERSION)
        self.assertEqual(MCP_SERVER_VERSION, "1.0.0")

    def test_resolve_and_setup_logging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_log = os.path.join(tmpdir, "test-mcp.log")
            
            # Setup logging
            active_path = setup_mcp_logging(level=logging.DEBUG)
            self.assertTrue(os.path.isabs(active_path))
            
            # Log messages
            log = logging.getLogger("twincat-mcp.test")
            log.info("Test info message for unit testing")
            log.warning("Test warning message for unit testing")
            
            # Ensure log file exists and contains entries including version and PID
            entries = get_recent_log_entries(max_lines=10)
            self.assertTrue(any("Test info message" in e or "TwinCAT MCP logging initialized" in e for e in entries))
            self.assertTrue(any(f"version={MCP_SERVER_VERSION}" in e for e in entries))
            self.assertTrue(any(f"PID:{os.getpid()}" in e for e in entries))

    def test_get_log_path_consistent(self):
        p1 = get_log_path()
        p2 = resolve_log_path()
        self.assertEqual(p1, p2)
        self.assertTrue(p1.endswith("mcp-twincat.log"))
