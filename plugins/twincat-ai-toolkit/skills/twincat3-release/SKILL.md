---
name: twincat3-release
description: >-
  Full library release workflow for TwinCAT3 PLC projects. Covers version bump,
  validation, library export, and changelog creation using MCP build automation.
  Use when releasing a new version, exporting a library, or preparing a release.
---

# Release TwinCAT3 Library

> **Prerequisites:** See `twincat3-versioning` rule for version format and `twincat3-changelog` skill for changelog writing.

## Quick Start

```
Task Progress:
- [ ] Step 1: Determine new version number
- [ ] Step 2: Bump version in .plcproj and Global_Version.TcGVL
- [ ] Step 3: Reload solution (structural change)
- [ ] Step 4: Validate (0 errors required)
- [ ] Step 5: Export library files
- [ ] Step 6: Create changelog
```

## Step 1: Determine Version Number

Read current version:

```
twincat_project_info(plcproj_path="<path>")
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

## Step 3: Reload Solution

The `.plcproj` version change is a structural change — XAE needs a reload:

```
twincat_open(plcproj_path="<path>")
twincat_reload()
```

## Step 4: Validate

The project must compile with **0 errors** before export:

```
twincat_check_all_objects()
twincat_get_errors()
```

If errors exist, fix them and re-check. Do NOT proceed to export with errors.

Warnings are acceptable but should be reviewed.

## Step 5: Export Library

```
twincat_export_library(plcproj_path="<path>")
```

This exports to `Versions/<version>/`:
- `<Title>-<Version>.library` — source library (installable in TwinCAT)
- `<Title>-<Version>.compiled-library` — precompiled library

Verify the response shows both files with non-zero sizes.

## Step 6: Create Changelog

Create `Versions/<version>/changelog-<version>.md` following the `twincat3-changelog` skill.

Key points:
- Major/feature release: Use `# Changelog — <LibName> X.X.X.X` header with Added/Changed/Fixed/Deprecated sections
- Bug fix release: Use `## Version X.X.X.X – Title` header with categorized sections
- Breaking changes: Use `> [!CAUTION]` blocks at the top
- English only, professional tone

## Session Handling

Do **not** call `twincat_close()` after a release. Leave the XAE session open — it will be reused automatically. Only use `twincat_close()` if XAE is unresponsive or the user explicitly asks to close it.

## Release Checklist

Before committing the release:

- [ ] Version bumped in `.plcproj` AND `Global_Version.TcGVL`
- [ ] Both versions match
- [ ] `twincat_check_all_objects` reports 0 errors
- [ ] `.library` and `.compiled-library` exported to `Versions/<version>/`
- [ ] Changelog created in `Versions/<version>/changelog-<version>.md`
- [ ] Breaking changes documented with `[!CAUTION]` blocks
