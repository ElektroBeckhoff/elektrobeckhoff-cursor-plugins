---
name: twincat3-release
description: >-
  Full library release workflow for TwinCAT3 PLC projects. Covers applying a
  user-chosen version, validation, library export, and changelog creation using
  MCP build automation. Use when releasing a new version, exporting a library,
  or preparing a release. Never invent or auto-increment the library version.
---

# Release TwinCAT3 Library

> **Prerequisites:** See `twincat3-versioning` rule for version format, `twincat3-changelog` for changelogs, and `twincat3-git-commit` for thematic local commits (never push).
>
> **Full ship gate** (plcproj sync → comment → format → PF-audit →
> re-format if needed → validate → auto version → …): skill
> `twincat3-new-version` / `/twincat3-cmd-new-version`. This skill is the
> version-apply + validate + export + changelog **core** only.

## Hard rule — version is user-owned (this skill)

**Never auto-update / invent / guess the library version** when invoked via
`/twincat3-cmd-release` or this skill alone.

- Do **not** pick MAJOR/MINOR/BUILD/REVISION yourself.
- Do **not** bump `.plcproj` / `Global_Version.TcGVL` until the user states the
  exact target version (e.g. `1.4.3.0`).
- You may show the **current** version via `twincat_plcproj_info` and ask:
  > Current version is X.X.X.X — which version should this release use?
- Format / bump table: rule `twincat3-versioning`.
- Exception: when called **from** `twincat3-new-version`, that skill already
  chose the version via the bump table — apply the version it supplies.

## Quick Start

```
Task Progress:
- [ ] Step 1: Resolve target version (user ask, or value from twincat3-new-version)
- [ ] Step 2: Apply that version in .plcproj and Global_Version.TcGVL
- [ ] Step 3: Reload (only because `.plcproj` version changed)
- [ ] Step 4: Validate (0 errors required)
- [ ] Step 5: Export library files
- [ ] Step 6: Create changelog
- [ ] Step 7: Local commits if requested (never push)
```

## Step 1: Target Version

Read current version (informational only):

```
twincat_plcproj_info(plcproj_path="<path>")
```

When invoked via `/twincat3-cmd-release` or this skill alone: **stop and ask**
if the user has not given an explicit `MAJOR.MINOR.BUILD.REVISION`.
When called from `twincat3-new-version`: use the version that skill already
chose (bump table / user override) — do not ask again.
Do not proceed to Step 2 without a concrete target version.

## Step 2: Apply Version

Update **two** files with the **resolved** target version:

1. `.plcproj` → `<ProjectVersion>`
2. `GVLs/Global_Version.TcGVL` → `stLibVersion` (`ST_LibVersion` from `Tc2_System`)

Both must match exactly. XML/ST samples → `rules/examples/twincat3-versioning.md`
(+ bump ownership in rule `twincat3-versioning`).

## Step 3: Reload Solution (because `.plcproj` changed)

Editing `.plcproj` for the version is the **only** reason to reload. Do not reload for source-only edits.

```
twincat_open(path="<path to .sln preferred, or .plcproj / folder>", xae_version="4024")
twincat_reload()
```

**Default shell: `xae_version="4024"`.** Use `xae_version="4026"` only if the user explicitly requests 4026. If the solution is already open, ROT attach is used (no duplicate window).

## Step 4: Validate

The project must compile with **0 errors** before export:

```
twincat_check_all_objects()
```

Require `error_count: 0`. The response includes errors, warnings, and infos. Do NOT proceed to export with errors. Warnings are acceptable but should be reviewed.

## Step 5: Export Library

Requires an open XAE session (`twincat_open` already done). Title/version are read from `.plcproj`.
`twincat_export_library` runs CheckAllObjects again and fails if any errors remain.

### Always export both artifacts (release / library update)

For `/twincat3-cmd-release`, `/twincat3-cmd-new-version`, and any library
update (after the target version is applied), **always** export **both**:

| Artifact | Flag | Required for release |
|----------|------|----------------------|
| `.library` | `library=true` | **yes** |
| `.compiled-library` | `compiled_library=true` | **yes** |

Install into the local TwinCAT repo: `install_library=true` (default).
`install_compiled_library` stays `false` unless the user asks.

**Exception (time saver):** only `/twincat3-cmd-online-test` / UmRT live
diagnose may export **`.library` alone** (`compiled_library=false`) — see
skill `twincat3-umrt-systemtest`. Never use that shortcut for a release.

**Prefer async** (Cursor MCP idle-timeouts long blocking exports with `-32001`
even when XAE finishes):

```
twincat_export_library(
  library=true,
  compiled_library=true,
  wait=false,
  timeout_seconds=1800
)
# poll until running=false:
twincat_export_progress()
```

When `method=async_started`, use `result{}` from the final progress snapshot
(not the start response) for paths/sizes. `wait=true` only for tiny/fast libs.

Optional: `plcproj_path="<path>"` if auto-detect fails; `output_dir` defaults to `<git_repo>/Versions/<ProjectVersion>/`.

Verify the final progress `result` shows **both** `.library` and
`.compiled-library` with non-zero size. If Cursor already timed out on an old
blocking export, check `Versions/<version>/` on disk before retrying.

## Step 6: Create Changelog

Create `Versions/<version>/changelog-<version>.md` following the `twincat3-changelog` skill.

Key points:
- Prefer primary template: `# Changelog — <LibName> X.X.X.X` with Highlights → All Changes (Added/Changed/Fixed/Style) → Migration
- Slim bug-fix header only for tiny internal patches
- Breaking changes: `> [!CAUTION]` with **BREAKING CHANGE:** plus Migration steps
- English only, user-facing tone (WHAT/WHY)

### Do not touch CI-managed release files

Do **not** edit the `README.md` download section (between auto-generated markers) or `Versions/release_dates.txt` during release. These are updated by GitHub Actions after the user pushes (bot commits such as `Update README with new version and release_dates.txt` are expected — do not recreate them manually).

## Step 7: Local Commits (optional)

If the user wants the release artifacts committed:

1. Follow `twincat3-git-commit` / `/twincat3-cmd-commit`
2. Typical split: `release:` (version + libraries) and `docs:` (changelog alone)
3. **NEVER** `git push` — the user always pushes manually

## Session Handling

Do **not** call `twincat_close()` after a release. Leave the XAE session open — the next `twincat_open` re-attaches via ROT by solution path (safe with multiple XAE windows). Only use `twincat_close()` if XAE is unresponsive or the user explicitly asks to close it.

## Release Checklist

Before finishing the release:

- [ ] Target version from user (`/twincat3-cmd-release`) or from
      `twincat3-new-version` bump table (no inventing outside that carve-out)
- [ ] That version applied in `.plcproj` AND `Global_Version.TcGVL`
- [ ] Both files match the user-stated version
- [ ] `twincat_check_all_objects` reports 0 errors
- [ ] Both `.library` **and** `.compiled-library` exported to `Versions/<version>/`
- [ ] Changelog created in `Versions/<version>/changelog-<version>.md`
- [ ] Breaking changes documented with `[!CAUTION]` blocks
- [ ] Did **not** edit `README.md` download section or `Versions/release_dates.txt` (GitHub Actions)
- [ ] If committing: thematic local commits only (`release:` / `docs:`) via `twincat3-git-commit`
- [ ] **No push** — user pushes manually
