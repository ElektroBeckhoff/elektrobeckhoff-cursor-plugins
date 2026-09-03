"""Central persistent logging infrastructure for TwinCAT MCP Server.

Configures rotating file logging into local app data and/or plugin cache,
capturing tool executions, COM STA calls, modal dialogs, and errors with
timestamps and tracebacks.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
from typing import Optional

from mcp_version import MCP_SERVER_VERSION, __version__

_LOG_FILENAME = "mcp-twincat.log"
_ACTIVE_LOG_PATH: Optional[str] = None


def resolve_log_path() -> str:
    """Determine the optimal persistent log file path."""
    global _ACTIVE_LOG_PATH
    if _ACTIVE_LOG_PATH:
        return _ACTIVE_LOG_PATH

    # Priority 1: LOCALAPPDATA / ElektroBeckhoff / logs
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        app_log_dir = os.path.join(local_appdata, "ElektroBeckhoff", "logs")
        try:
            os.makedirs(app_log_dir, exist_ok=True)
            test_file = os.path.join(app_log_dir, ".write_test")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(test_file)
            _ACTIVE_LOG_PATH = os.path.join(app_log_dir, _LOG_FILENAME)
            return _ACTIVE_LOG_PATH
        except Exception:
            pass

    # Priority 2: Server directory
    server_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        os.makedirs(server_dir, exist_ok=True)
        _ACTIVE_LOG_PATH = os.path.join(server_dir, _LOG_FILENAME)
        return _ACTIVE_LOG_PATH
    except Exception:
        pass

    # Priority 3: Temp dir fallback
    import tempfile
    _ACTIVE_LOG_PATH = os.path.join(tempfile.gettempdir(), _LOG_FILENAME)
    return _ACTIVE_LOG_PATH


class SafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler resilient against Windows file lock contention between multiple Cursor instances."""

    def doRollover(self):
        try:
            super().doRollover()
        except (PermissionError, OSError):
            # Another Cursor MCP process has the file open on Windows.
            # Continue writing to current file safely.
            pass


def setup_mcp_logging(level: Optional[int] = None) -> str:
    """Initialize logging with stderr stream and persistent RotatingFileHandler.

    Returns the absolute path to the active log file.
    """
    log_path = resolve_log_path()

    log_level_name = os.environ.get("TWINCAT_MCP_LOG_LEVEL", "INFO").upper()
    default_level = getattr(logging, log_level_name, logging.INFO)
    active_level = level if level is not None else default_level

    root_logger = logging.getLogger()
    root_logger.setLevel(active_level)

    # Format with explicit PID on every line for multi-window / multi-tab discrimination
    fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(levelname)-7s] [PID:%(process)-5d] [%(name)s:%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Stderr handler for MCP console (if not already added)
    has_stream = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root_logger.handlers
    )
    if not has_stream:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(fmt)
        stream_handler.setLevel(active_level)
        root_logger.addHandler(stream_handler)

    # Rotating file handler (10 MB per file, max 5 backups)
    has_file = any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        and getattr(h, "baseFilename", "") == os.path.abspath(log_path)
        for h in root_logger.handlers
    )
    if not has_file:
        try:
            file_handler = SafeRotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
                delay=False,
            )
            file_handler.setFormatter(fmt)
            file_handler.setLevel(active_level)
            root_logger.addHandler(file_handler)
        except Exception as exc:
            sys.stderr.write(f"Warning: Could not initialize log file at {log_path}: {exc}\n")

    # Install unhandled exception hook
    def _handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger("twincat-mcp.crash").critical(
            "Unhandled top-level exception:",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = _handle_unhandled_exception

    # Install threading exception hook if available (Python 3.8+)
    if hasattr(threading, "excepthook"):
        def _handle_thread_exception(args):
            logging.getLogger("twincat-mcp.thread-crash").critical(
                f"Unhandled exception in thread '{args.thread.name}':",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        threading.excepthook = _handle_thread_exception

    log = logging.getLogger("twincat-mcp")
    log.info(
        "TwinCAT MCP logging initialized | version=%s | log_file='%s' | level=%s | pid=%d | python=%s",
        MCP_SERVER_VERSION,
        log_path,
        logging.getLevelName(active_level),
        os.getpid(),
        sys.version.split()[0],
    )

    return log_path


def get_mcp_server_version() -> str:
    """Return the MCP server version string."""
    return MCP_SERVER_VERSION


def get_log_path() -> str:
    """Return the active log file path."""
    return resolve_log_path()


def get_recent_log_entries(max_lines: int = 50) -> list[str]:
    """Read the tail of the current log file."""
    path = get_log_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip("\r\n") for l in lines[-max_lines:]]
    except Exception:
        return []
