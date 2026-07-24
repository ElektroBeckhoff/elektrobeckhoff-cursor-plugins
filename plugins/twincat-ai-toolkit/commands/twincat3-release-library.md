---
name: twincat3-release-library
description: Release a new version of the TwinCAT3 PLC library with version bump, validation, export, and changelog. Never pushes.
---

# Release Library

Prepare and export a new library release.

## Required Context

**Rules:** `twincat3-versioning`
**Skills:** `twincat3-release` (follow completely), `twincat3-changelog` (for changelog creation), optionally `twincat3-git-commit` if the user wants local commits

## Instructions

1. Ask the user for the new version number (or suggest one based on changes), bump version in `.plcproj` and `Global_Version.TcGVL`, validate with 0 errors, export library files, and create the changelog per `twincat3-release`.
2. If the user wants commits afterward, use `/twincat3-commit` (thematic `release:` / `docs:` split).
3. **NEVER** run `git push` or any remote update. The user always pushes manually.
