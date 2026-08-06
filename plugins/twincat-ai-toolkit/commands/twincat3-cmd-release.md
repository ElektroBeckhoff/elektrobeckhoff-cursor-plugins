---
name: twincat3-cmd-release
description: Full TwinCAT3 library release â€” version bump, validate, export library, changelog. Never pushes.
---

# Release Library

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-release/SKILL.md`
2. `skills/twincat3-changelog/SKILL.md`
3. `rules/twincat3-versioning.mdc`
4. `rules/twincat3-mcp-build.mdc`

Optional (only if user asks to commit afterward):

5. `skills/twincat3-git-commit/SKILL.md`

## Do

1. Follow the release skill: version in `.plcproj` + `Global_Version.TcGVL` → validate 0 errors → export → changelog.
2. Open / validate with **`xae_version="4024"`** by default (`twincat_open(..., xae_version="4024")`). Use **`4026` only if the user explicitly requests it**.
3. Confirm version with the user if unclear.
4. Never push. Commits only on request via `/twincat3-cmd-commit` (`release:` / `docs:` split).
