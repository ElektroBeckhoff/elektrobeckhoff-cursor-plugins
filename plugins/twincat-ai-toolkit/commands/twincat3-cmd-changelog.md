---
name: twincat3-cmd-changelog
description: Write Versions/<ver>/changelog-<ver>.md for a TwinCAT3 library release from git history.
---

# Write Changelog

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-changelog/SKILL.md`
2. `rules/twincat3-versioning.mdc`

## Do

1. Follow the changelog skill completely (git log since previous release â†’ user-facing sections).
2. Write `Versions/<ver>/changelog-<ver>.md` only â€” no unrelated edits.
3. Do **not** commit here. If the user wants commits: `/twincat3-cmd-commit`.
4. Never push.
