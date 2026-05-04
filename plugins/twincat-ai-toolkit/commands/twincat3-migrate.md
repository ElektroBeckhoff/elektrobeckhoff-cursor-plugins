---
name: twincat3-migrate
description: Auto-detect FBD/CFC implementations and migrate to Structured Text in one pass.
---

# Migrate FBD/CFC to Structured Text

Convert TwinCAT 3 FBD/FUP and CFC .TcPOU implementations to functionally identical Structured Text code. Automatically detects the implementation type per file.

## Required Context

**Rules:** `twincat3-migration-safety`
**Skills:** `twincat3-migrate` (follow completely)

## Mandatory Workflow

1. **Analyze:** `twincat_migrate(input="<path>", analyze_only=true, recursive=true)`
2. **Preview:** `twincat_migrate(input="<path>", dry_run=true, recursive=true)` -- verify 0 errors
3. **Migrate:** `twincat_migrate(input="<path>", recursive=true)` -- user chooses mode
4. **Verify:** `twincat_check_all_objects` + search for `TODO [FBD Migration]` / `TODO [CFC Migration]`

Do NOT skip steps 1 and 2 unless the user explicitly requests it.
