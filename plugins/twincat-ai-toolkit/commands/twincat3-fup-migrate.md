---
name: twincat3-fup-migrate
description: Migrate TwinCAT FBD/FUP implementations to Structured Text.
---

# Migrate FBD/FUP to Structured Text

Convert TwinCAT 3 FBD/FUP (Function Block Diagram) .TcPOU implementations to functionally identical Structured Text code.

## Instructions

Follow the `twincat3-fup-migrate` skill completely. Always analyze first, then preview with dry-run, then migrate.

The `twincat_fup_migrate` MCP tool handles single files and recursive folder processing with backup, swap, force, dry-run, and analyze-only modes.

After migration, validate the project with `twincat_check_all_objects` and review any `TODO [FBD Migration]` markers in the generated code.
