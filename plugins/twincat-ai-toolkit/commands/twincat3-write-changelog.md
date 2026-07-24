---
name: twincat3-write-changelog
description: Write or update a Versions/ changelog for the current TwinCAT3 library release. Does not commit or push.
---

# Write Changelog

Create or update user-facing release notes for the TwinCAT3 PLC library.

## Required Context

**Skills:** `twincat3-changelog` (follow completely)
**Rules:** `twincat3-versioning`

## Instructions

1. Determine the target version: ask the user, or read `.plcproj` `<ProjectVersion>` / `Global_Version.TcGVL`.
2. Follow the `twincat3-changelog` skill completely (git log since previous release → user-facing sections).
3. Write `Versions/<version>/changelog-<version>.md` (create the version folder if needed).
4. Do **not** commit the changelog in this command (avoids mixing with feature diffs). If the user wants a commit afterward, tell them to run `/twincat3-commit`.
5. **NEVER** run `git push` or any remote update. The user always pushes manually.
