---
name: twincat3-cmd-new-version
description: >-
  Ship gate: plcproj sync, comment pass, format, pagefault audit, validate
  (4024), version auto from twincat3-versioning, changelog, export
  .library+.compiled-library, thematic local commits. Never pushes.
---

# New Version (Ship Gate)

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-new-version/SKILL.md`
2. `rules/twincat3-versioning.mdc`
3. `skills/twincat3-plcproj-sync/SKILL.md`
4. `skills/twincat3-comment/SKILL.md`
5. `skills/twincat3-format/SKILL.md`
   (STweep alternative: `skills/twincat3-stweep-format/SKILL.md`)
6. `skills/twincat3-pagefault-audit/SKILL.md`
7. `skills/twincat3-pagefault-audit/checklist.md`
8. `skills/twincat3-validate/SKILL.md`
9. `skills/twincat3-release/SKILL.md`
10. `skills/twincat3-changelog/SKILL.md`
11. `skills/twincat3-git-commit/SKILL.md`

## Do

1. Follow `twincat3-new-version` end-to-end (do not duplicate skill bodies).
2. Pipeline: **PlcProj sync → Comment (scoped) → Format → PF-Audit →
   (re-Format only if code changed) → Validate → Version → Changelog →
   Export both → Commits → Report**.
3. PlcProj: verify; sync with backup if drift. Comment: each changed object in
   scope via `twincat3-comment` (skip only if user asks).
4. Version: classify changes → auto next MAJOR/MINOR/BUILD/REVISION per
   versioning rule; announce `current → proposed`; ask only if ambiguous;
   honor explicit user override. Mode `reexport` = no bump.
5. Default `xae_version="4024"`. Export always `.library` + `.compiled-library`
   with async + progress poll.
6. Never push.
