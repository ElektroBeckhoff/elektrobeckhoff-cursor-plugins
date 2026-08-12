---
name: twincat3-new-version
description: >-
  Ship gate for TwinCAT3 libraries: plcproj sync, comment pass, format,
  pagefault audit, validate (4024), version auto from twincat3-versioning,
  changelog, export both library artifacts, thematic local commits. Never
  pushes. Use for /twincat3-cmd-new-version.
---

# New Version (Ship Gate)

Orchestrates atomic skills. **Read** each skill when executing that step — do not
duplicate their bodies here.

> Full ship gate. For bump+export+changelog with a **user-stated** version only,
> use skill `twincat3-release` / `/twincat3-cmd-release`.

## Pipeline (strict order)

```text
Scope → PlcProj sync → Comment (scoped objects) → Format → PF-Audit
  → (fix?) → Format again ONLY if code changed
  → Validate(4024) → Version (auto / reexport) → Changelog → Export both
  → Thematic local commits → Report
```

| Mode | When | Version |
|------|------|---------|
| **`new-version`** (default) | Feature/fix ready, new library | Auto from `twincat3-versioning` bump table |
| **`reexport`** | Same version again | No bump; Validate + Export (+ optional changelog skip) |

## Defaults

| Setting | Default |
|---------|---------|
| XAE | **4024** (`4026` only if user says so) |
| Version | Auto classify → bump (honor exact user override) |
| Format / PF / comment scope | Changed `.TcPOU`/`.TcDUT`/`.TcGVL` (or user filter) |
| PlcProj sync | **On** — verify; sync if drift (with backup) |
| Comment pass | **On** for each changed object in scope (one object per skill run) |
| Export | **`.library` + `.compiled-library`** (async + poll) |
| Commit | Yes, thematic — unless user says no / filter |
| Push | **Never** |
| Online-Test | Opt-in only (`/twincat3-cmd-online-test`) |

Skip plcproj sync or comment only if the user explicitly says so.

## Read first (when running this skill)

Resolve plugin root (`skills/` + `rules/`). Then Read as needed:

1. `rules/twincat3-versioning.mdc` — bump table + carve-out
   (+ `rules/examples/twincat3-versioning.md` when applying plcproj/GVL)
2. `skills/twincat3-plcproj-sync/SKILL.md` (+ `rules/twincat3-plcproj-safety.mdc`)
3. `skills/twincat3-comment/SKILL.md` + `rules/twincat3-comments.mdc`
4. `skills/twincat3-stweep-format/SKILL.md` + `rules/twincat3-mcp-stweep.mdc`
5. `skills/twincat3-pagefault-audit/SKILL.md` (+ checklist, infosys-evidence)
6. `skills/twincat3-validate/SKILL.md` + `rules/twincat3-mcp-build.mdc`
7. `skills/twincat3-release/SKILL.md` — apply version / export / reload patterns
8. `skills/twincat3-changelog/SKILL.md`
9. `skills/twincat3-git-commit/SKILL.md`

## Quick Start

```
Task Progress:
- [ ] Step 0: Scope
- [ ] Step 1: PlcProj verify / sync
- [ ] Step 2: Comment pass (scoped objects)
- [ ] Step 3: Format (baseline)
- [ ] Step 4: Pagefault audit (gate)
- [ ] Step 5: Re-Format only if code changed
- [ ] Step 6: Validate (4024, 0 errors)
- [ ] Step 7: Version bump or reexport skip
- [ ] Step 8: Changelog
- [ ] Step 9: Export both artifacts
- [ ] Step 10: Thematic local commits (if requested)
- [ ] Step 11: Final report
```

## Step 0: Scope

Ask or infer:

- Library `.sln` / `.plcproj` path
- Format / audit / comment file set (changed objects, or user filter)
- Mode: `new-version` vs `reexport`
- Commit filter (e.g. “only this FB”, “no samples”)
- Online-Test yes/no (default no)
- Optional exact version override (skips auto-classify)
- Optional skips: `skip_plcproj_sync` / `skip_comment` only if user asks

## Step 1: PlcProj sync

Follow `twincat3-plcproj-sync` / safety rule:

1. `twincat_plcproj_verify(input=<plcproj or project root>)`
2. If drift (missing/extra Compile/Folder entries):
   - dry-run preview: `twincat_plcproj_sync(..., force=true, dry_run=true)`
   - apply with backup: `twincat_plcproj_sync(..., force=true)` (default backup)
3. If already in sync → note and continue.
4. Do **not** invent GUID repairs unless verify/sync reports GUID issues and the
   user allows (see plcproj-sync skill).

Rationale: new/removed objects must be registered before format/validate/export.

## Step 2: Comment pass (scoped objects)

Follow `twincat3-comment` / `/twincat3-cmd-comment` for **each** changed object
in scope (`.TcPOU` / `.TcDUT` — POU, STRUCT, or ENUM). One object per skill
invocation; loop the set.

- Comment-only — no logic changes
- Skip if user said `skip_comment`, or scope has no commentable files
- Do **not** silently rewrite the whole library

## Step 3: Format (baseline)

Follow `twincat3-stweep-format`. File/folder OK; whole project only with
`confirm=true`. Honor path filter. Prefer `xae_version="4024"` on open.

Rationale: clean baseline **before** audit (also after comment churn).

## Step 4: Pagefault audit (gate)

Follow `/twincat3-cmd-pagefault-audit` / `twincat3-pagefault-audit` for the same
scope as Format.

- Report Errors with Check-ID + file:line.
- **Stop** on errors until the user allows fixes. No silent fixes.
- After fix approval: re-audit until 0 errors.
- Track whether any code was changed in this loop.

## Step 5: Re-Format (conditional)

- If code changed in Step 4 → format that scope again (same skill).
- If audit was clean / no code edits → **skip**.

## Step 6: Validate

```
twincat_open(path=<sln>, xae_version="4024")
twincat_check_all_objects  → error_count = 0
```

Hard stop if errors remain. Follow `twincat3-validate`.
If validate fails with missing-object / project load issues after file adds,
re-check plcproj sync (Step 1) once, then re-validate.

## Step 7: Version (`new-version` only)

Source of truth: rule `twincat3-versioning`.

1. Read current via `twincat_plcproj_info` (and `Global_Version` if needed).
2. Classify release content (git log/diff since last `Versions/<ver>/` / last
   release commit; prefer dominant user-facing change).
3. Compute **proposed** next version from the bump table (with resets).
4. **Announce**: `current → proposed (reason: BUILD/fix | MINOR/feat | …)`.
   - Ambiguous → **ask once**.
   - User already gave exact version → use that (override).
   - Otherwise **apply proposed** without a second confirmation.
5. Write `.plcproj` `<ProjectVersion>` + `Global_Version.TcGVL` (must match).
   Follow apply/reload patterns from `twincat3-release`.
6. `twincat_reload` (because plcproj changed).
7. Validate again → 0 errors.

**`reexport` mode:** skip this step (keep current version).

Note: bare `/twincat3-cmd-release` still asks the user; this skill **prefers
rule-based auto**.

## Step 8: Changelog

Create `Versions/<ver>/changelog-<ver>.md` via `twincat3-changelog`.
Highlights + Added/Changed/Fixed; commit links when available.

## Step 9: Export

Always both artifacts for this gate (not the online-test shortcut):

```
twincat_export_library(
  library=true,
  compiled_library=true,
  wait=false,
  timeout_seconds=1800
)
→ poll twincat_export_progress until running=false
→ verify both files under Versions/<ver>/ (non-zero size)
```

Hard stop if either artifact missing / zero size. Follow `twincat3-release`
export details.

## Step 10: Commits (default yes)

Unless the user declines or filters out:

Order (thematic, local only — `twincat3-git-commit`):

1. `fix:` / `feat:` / `refactor:` — source (+ comment-only if mixed in same files)
2. `chore:` / `fix:` — `.plcproj` sync alone (if separable)
3. `style:` — format-only (optional split)
4. `docs:` — changelog
5. `release:` — version files + `.library` + `.compiled-library`

Honor path filters. **Never push.**

## Step 11: Final report

```text
New version: X.Y.Z.W
- PlcProj sync: in sync | synced (N compile/folder changes)
- Comment: K objects | skipped
- Format (baseline): N files
- PF-Audit: 0 errors (scope …)
- Format (re): skipped | M files
- Validate: 0 errors (4024)
- Export: .library + .compiled-library (paths + sizes)
- Commits: <hashes> — local only, nothing pushed
```

## Hard stops

- PF errors without user fix approval
- Validate `error_count > 0`
- Missing / zero-size export artifact
- Any `git push` / remote update
- Version inventing outside the MAJOR/MINOR/BUILD/REVISION bump table
- PlcProj sync that would delete user data without backup / without clear dry-run

## Out of scope

| Topic | Why |
|-------|-----|
| Feature implementation | Separate turn |
| Online-Test | Opt-in `/twincat3-cmd-online-test` |
| Push / GitHub Release / Tag | Human |
| Whole-library silent comment rewrite | Only **scoped** objects via `/twincat3-cmd-comment` |
