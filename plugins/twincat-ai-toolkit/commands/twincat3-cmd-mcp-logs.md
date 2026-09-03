---
name: twincat3-cmd-mcp-logs
description: >-
  Inspect and diagnose TwinCAT MCP server logs (mcp-twincat.log) — check active
  version, COM automation timeouts, modal dialog blockades, and server crashes.
---

# TwinCAT MCP Server Log Inspection

Diagnose MCP server health, trace tool execution history, identify server version, and investigate COM/XAE timeouts.

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-mcp-logs/SKILL.md`
2. `rules/twincat3-mcp-logs.mdc`

## Do

1. Locate the active log file via `twincat_status()` (field `log_file`) or `%LOCALAPPDATA%\ElektroBeckhoff\logs\mcp-twincat.log`.
2. Inspect the startup session banner to confirm the active `version` and `pid`.
3. Filter recent log entries for `[ERROR]`, `[WARNING]`, `[CRITICAL]`, and timeout markers.
4. Diagnose the root cause using the signatures in `skills/twincat3-mcp-logs/SKILL.md`:
   - Modal dialog blocking COM STA thread
   - XAE in Online mode causing solution reload timeout
   - Visual Studio COM busy (`RPC_E_CALL_REJECTED`)
   - Unhandled exception traceback
5. Report the diagnosis and recommend specific resolution steps.
