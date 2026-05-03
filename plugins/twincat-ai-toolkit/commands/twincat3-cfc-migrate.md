---
name: twincat3-cfc-migrate
description: Migrate TwinCAT CFC implementations to Structured Text.
---

# Migrate CFC to Structured Text

Convert TwinCAT 3 CFC (Continuous Function Chart) .TcPOU implementations to functionally equivalent Structured Text code.

## Instructions

Follow the `twincat3-cfc-migrate` skill completely. Always analyze first, then preview with dry-run, then migrate.

The `twincat_cfc_migrate` MCP tool handles single files and recursive folder processing with backup, swap, force, dry-run, and analyze-only modes.

After migration, validate the project with `twincat_check_all_objects` and review any `TODO [CFC Migration]` markers in the generated code. Pay special attention to execution order -- verify it matches the original CFC behavior.
