---
name: twincat3-fup-migrate
description: Migrate TwinCAT FBD/FUP implementations to Structured Text.
---

# Migrate FBD/FUP to Structured Text

Convert TwinCAT 3 FBD/FUP (Function Block Diagram) .TcPOU implementations to functionally identical Structured Text code.

## Required Context

**Rules:** `twincat3-migration-safety`, `twincat3-fup-safety`
**Skills:** `twincat3-fup-migrate` (follow completely)

## Mandatory Workflow

1. **Analyze:** `twincat_fup_migrate(input="<path>", analyze_only=true)`
2. **Preview:** `twincat_fup_migrate(input="<path>", dry_run=true)` -- verify 0 errors
3. **Migrate:** `twincat_fup_migrate(input="<path>")` -- user chooses mode
4. **Verify:** Search for `TODO [FBD Migration]`. Do **not** run `twincat_open` / `twincat_check_all_objects` unless the user explicitly asks to compile / validate thoroughly.

For mixed FBD/CFC projects, use the `twincat3-migrate` command instead.
