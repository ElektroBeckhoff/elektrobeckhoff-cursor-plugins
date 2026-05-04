---
name: twincat3-release-library
description: Release a new version of the TwinCAT3 PLC library with version bump, validation, export, and changelog.
---

# Release Library

Prepare and export a new library release.

## Required Context

**Rules:** `twincat3-versioning`
**Skills:** `twincat3-release` (follow completely), `twincat3-changelog` (for changelog creation)

## Instructions

Ask the user for the new version number (or suggest one based on changes), bump version in `.plcproj` and `Global_Version.TcGVL`, validate with 0 errors, export library files, and create the changelog.
