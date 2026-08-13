---
name: twincat3-cmd-format
description: >-
  Format TwinCAT Structured Text with STweep via MCP (install + license check,
  then Format code for file/folder; project only with confirm).
---

# Format code (STweep)

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-stweep-format/SKILL.md`
2. `rules/twincat3-mcp-stweep.mdc`

## Do

1. Follow the STweep format skill end-to-end.
2. Prefer `.sln` for `twincat_open`; set `xae_version` if 4024 and 4026 are both open.
3. Run `twincat_stweep_status` — require `installed`, `commands_loaded`, `ready=true` (no license UI).
4. Format **file or folder** with `twincat_format_code(path=...)`.
5. Whole **project** only if the user explicitly confirms → `confirm=true`.
6. Default `wait=false`; raise `timeout_seconds`; poll `twincat_format_progress` until `running=false`.
7. On stall / reload popups: `twincat_status` → `twincat_dismiss_safe_dialogs` (rule `twincat3-mcp-build`) — do not narrate manual XAE clicks.
8. To abort: `twincat_format_cancel` (stops between files).
9. Expect per-file OpenFile + editor Formatcode (not UI folder Formatcode) — SE `Select` is broken in automation.
10. License: fail-fast on first Formatcode error — abort remaining files; do not open the License wizard unless the user asks (`probe_license=true`).
11. Never use STweep.CLI. Never print license activation keys.
12. On unlicensed / not installed: stop and report — do not retry-loop format.
