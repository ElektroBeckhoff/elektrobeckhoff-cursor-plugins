---
name: twincat3-cmd-format
description: >-
  Format TwinCAT Structured Text with the Python formatter via MCP (file-based,
  no XAE). Single file, folder, project, scoped regions, dry-run, validate.
---

# Format code (Python formatter)

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-format/SKILL.md`
2. `rules/twincat3-mcp-format.mdc`

## Do

1. Follow the Python format skill end-to-end.
2. No `twincat_open` required — operates directly on disk files.
3. Format with `twincat_format(path=...)` or `twincat_format(project="<.sln>")`.
4. For large projects: poll `twincat_format_progress` until `status` is `done`.
5. Preview only: `dry_run=true`.
6. Validate only: `twincat_format_validate(path=...)`.
7. Check `errors` in the result — syntax integrity failures mean the file was **not** written.
8. For STweep / XAE formatting instead, use `/twincat3-cmd-stweep-format`.
