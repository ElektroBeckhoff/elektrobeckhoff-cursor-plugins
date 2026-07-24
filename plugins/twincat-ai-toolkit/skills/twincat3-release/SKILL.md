---
name: twincat3-release
description: >-
  Full library release workflow for TwinCAT3 PLC projects. Covers version bump,
  validation, library export, and changelog creation using MCP build automation.
  Use when releasing a new version, exporting a library, or preparing a release.
---

# Release TwinCAT3 Library

> **Prerequisites:** See `twincat3-versioning` rule for version format, `twincat3-changelog` for changelogs, and `twincat3-git-commit` for thematic local commits (never push).

## Quick Start

```
Task Progress:
- [ ] Step 1: Determine new version number
- [ ] Step 2: Bump version in .plcproj and Global_Version.TcGVL
- [ ] Step 3: Reload (only because `.plcproj` version was bumped)
- [ ] Step 4: Validate (0 errors required)
- [ ] Step 5: Export library files
- [ ] Step 6: Create changelog
- [ ] Step 7: Local commits if requested (never push)
```

## Step 1: Determine Version Number

Read current version:

```
twincat_plcproj_info(plcproj_path="<path>")
```

Increment according to change scope:

| Change Type | Increment | Example |
|-------------|-----------|---------|
| Breaking API change | MAJOR | `0.9.0.0` → `1.0.0.0` |
| New feature, backwards-compatible | MINOR | `1.0.0.0` → `1.1.0.0` |
| Bug fix | BUILD | `1.1.0.0` → `1.1.1.0` |
| Internal/patch | REVISION | `1.1.1.0` → `1.1.1.1` |

## Step 2: Bump Version

Update **two** files with the new version:

### 2a. `.plcproj`

Find and update `<ProjectVersion>`:

```xml
<ProjectVersion>1.1.0.0</ProjectVersion>
```

### 2b. `Global_Version.TcGVL`

Update the `ST_LibVersion` constant:

```iecst
{attribute 'TcGenerated'}
VAR_GLOBAL CONSTANT
    stLibVersion : ST_LibVersion := (
        iMajor    := 1,
        iMinor    := 1,
        iBuild    := 0,
        iRevision := 0,
        sVersion  := '1.1.0.0'
    );
END_VAR
```

Both must match exactly.

## Step 3: Reload Solution (because `.plcproj` changed)

Version bump edits `.plcproj` — that is the **only** reason to reload. Do not reload for source-only edits.

```
twincat_open(path="<path to .sln preferred, or .plcproj / folder>")
twincat_reload()
```

Optional `xae_version="4024"` / `"4026"` only if the user requires a specific shell. If the solution is already open, ROT attach is used (no duplicate window).

## Step 4: Validate

The project must compile with **0 errors** before export:

```
twincat_check_all_objects()
```

Require `error_count: 0`. The response includes errors, warnings, and infos. Do NOT proceed to export with errors. Warnings are acceptable but should be reviewed.

## Step 5: Export Library

Requires an open XAE session (`twincat_open` already done). Title/version are read from `.plcproj`.
`twincat_export_library` runs CheckAllObjects again and fails if any errors remain.

```
twincat_export_library()
```

Optional: `plcproj_path="<path>"` if auto-detect fails; `output_dir` defaults to `<git_repo>/Versions/<ProjectVersion>/`.

Defaults: export both `.library` and `.compiled-library`; install only `.library` into the local TwinCAT repo (`install_compiled_library=false`). Optional flags: `library`, `compiled_library`, `install_library`, `install_compiled_library`.

Verify the response shows both files with non-zero sizes.

## Step 6: Create Changelog

Create `Versions/<version>/changelog-<version>.md` following the `twincat3-changelog` skill.

Key points:
- Prefer primary template: `# Changelog — <LibName> X.X.X.X` with Highlights → All Changes (Added/Changed/Fixed/Style) → Migration
- Slim bug-fix header only for tiny internal patches
- Breaking changes: `> [!CAUTION]` with **BREAKING CHANGE:** plus Migration steps
- English only, user-facing tone (WHAT/WHY)

## Step 7: Local Commits (optional)

If the user wants the release artifacts committed:

1. Follow `twincat3-git-commit` / `/twincat3-commit`
2. Typical split: `release:` (version + libraries) and `docs:` (changelog alone)
3. **NEVER** `git push` — the user always pushes manually

## Session Handling

Do **not** call `twincat_close()` after a release. Leave the XAE session open — the next `twincat_open` re-attaches via ROT by solution path (safe with multiple XAE windows). Only use `twincat_close()` if XAE is unresponsive or the user explicitly asks to close it.

## Release Checklist

Before finishing the release:

- [ ] Version bumped in `.plcproj` AND `Global_Version.TcGVL`
- [ ] Both versions match
- [ ] `twincat_check_all_objects` reports 0 errors
- [ ] `.library` and `.compiled-library` exported to `Versions/<version>/`
- [ ] Changelog created in `Versions/<version>/changelog-<version>.md`
- [ ] Breaking changes documented with `[!CAUTION]` blocks
- [ ] If committing: thematic local commits only (`release:` / `docs:`) via `twincat3-git-commit`
- [ ] **No push** — user pushes manually
