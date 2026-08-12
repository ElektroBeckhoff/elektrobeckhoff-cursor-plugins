---
name: twincat3-cmd-release
description: >-
  TwinCAT3 library release core — apply user-chosen version, validate, export
  both library artifacts, changelog. Never pushes. Never auto-bumps version.
  For full ship gate (plcproj sync, comment, format, PF-audit, auto version)
  use /twincat3-cmd-new-version.
---

# Release Library

> **Full ship gate** (plcproj sync → comment → format → PF-audit →
> re-format if needed → validate → rule-based version → changelog → export →
> commits): use `/twincat3-cmd-new-version` instead.
> This command is the **bump + validate + export + changelog** core with a
> **user-stated** version only.

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-release/SKILL.md`
2. `skills/twincat3-changelog/SKILL.md`
3. `rules/twincat3-versioning.mdc`
4. `rules/examples/twincat3-versioning.md` (plcproj / Global_Version samples)
5. `rules/twincat3-mcp-build.mdc`

Optional (only if user asks to commit afterward):

6. `skills/twincat3-git-commit/SKILL.md`

## Do

1. **Version — user only:** Do **not** invent or auto-increment the library
   version. Show current via `twincat_plcproj_info` if helpful, then **ask** for
   the exact target `MAJOR.MINOR.BUILD.REVISION`. Stop until the user answers.
   (Auto-bump is only for `/twincat3-cmd-new-version`.)
2. Apply that version in `.plcproj` + `Global_Version.TcGVL` → validate 0 errors
   → export → changelog (follow the release skill).
3. Open / validate with **`xae_version="4024"`** by default
   (`twincat_open(..., xae_version="4024")`). Use **`4026` only if the user
   explicitly requests it**.
4. Export **both** artifacts — always for release / library update
   (`library=true`, `compiled_library=true`, prefer `wait=false` + poll
   `twincat_export_progress`). Call shape: skill `twincat3-release` /
   rule `twincat3-mcp-build`. Verify both files in `Versions/<version>/`.
   **Do not** skip `.compiled-library` on release (that shortcut is only for
   `/twincat3-cmd-online-test`).
5. Never push. Commits only on request via `/twincat3-cmd-commit` (`release:` / `docs:` split).
