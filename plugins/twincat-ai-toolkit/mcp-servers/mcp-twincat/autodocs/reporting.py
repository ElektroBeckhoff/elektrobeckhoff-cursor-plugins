"""Autodocs logging (console + in-memory buffer)."""
from __future__ import annotations

from datetime import datetime


class AutodocsLogger:
    """Print log lines and collect them for autodocs.log / MCP JSON."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.lines: list[str] = []

    def log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        if self.verbose:
            print(line)
        self.lines.append(line)
