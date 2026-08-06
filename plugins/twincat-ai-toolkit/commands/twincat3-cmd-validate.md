---
name: twincat3-cmd-validate
description: Validate a TwinCAT3 PLC project via MCP CheckAllObjects and report errors.
---

# Validate Project

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-validate/SKILL.md`
2. `rules/twincat3-mcp-build.mdc`

## Do

1. Follow the validate skill end-to-end.
2. Prefer `.sln` when known; else `.plcproj`.
3. `twincat_open` â†’ `twincat_check_all_objects` â†’ report errors with path + line.
4. Success = `error_count: 0` (still surface `warnings[]`).
5. Optional `xae_version` only if the user requires a specific shell.
6. If errors found, offer to fix.
