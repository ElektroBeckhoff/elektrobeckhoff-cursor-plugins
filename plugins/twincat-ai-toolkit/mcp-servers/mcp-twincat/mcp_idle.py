"""Cursor MCP idle-timeout helpers.

Cursor often kills sync tool calls around 120s idle (-32001) even when the
server is still working. Long format/export jobs must use async + progress
polling; sync is only for short tests.
"""

# Stay below Cursor's typical ~120s idle kill window.
MCP_SYNC_MAX_S = 90


def should_coerce_wait_to_async(wait: bool, timeout_s: int) -> bool:
    """True when wait=true would likely hit Cursor idle timeout."""
    return bool(wait) and int(timeout_s) > MCP_SYNC_MAX_S


def async_coerced_message(progress_tool: str) -> str:
    return (
        f"wait=true coerced to async "
        f"(timeout_seconds>{MCP_SYNC_MAX_S}) to avoid Cursor MCP idle -32001; "
        f"poll {progress_tool} until running=false."
    )
