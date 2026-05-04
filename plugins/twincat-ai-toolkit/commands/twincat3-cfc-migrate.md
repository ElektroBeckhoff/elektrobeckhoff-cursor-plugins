---
name: twincat3-cfc-migrate
description: Migrate TwinCAT CFC implementations to Structured Text.
---

# Migrate CFC to Structured Text

Convert TwinCAT 3 CFC (Continuous Function Chart) .TcPOU implementations to functionally equivalent Structured Text code.

## Required Context

**Rules:** `twincat3-migration-safety`, `twincat3-cfc-safety`
**Skills:** `twincat3-cfc-migrate` (follow completely)

## Mandatory Workflow

1. **Analyze:** `twincat_cfc_migrate(input="<path>", analyze_only=true)`
2. **Preview:** `twincat_cfc_migrate(input="<path>", dry_run=true)` -- verify 0 errors
3. **Migrate:** `twincat_cfc_migrate(input="<path>")` -- user chooses mode
4. **Verify:** `twincat_check_all_objects` + search for `TODO [CFC Migration]`, verify execution order

For mixed FBD/CFC projects, use the `twincat3-migrate` command instead.
