---
name: twincat3-plcproj-sync
description: Verify and sync TwinCAT .plcproj file against the actual project files on disk.
---

# Sync PlcProject File

Verify that the TwinCAT .plcproj matches the files on disk, and rebuild it if needed.

## Required Context

**Rules:** `twincat3-plcproj-safety`
**Skills:** `twincat3-plcproj-sync` (follow completely)

## Mandatory Workflow

1. **Verify:** `twincat_plcproj_verify` -- check current drift
2. **Preview:** `twincat_plcproj_sync(force=true, dry_run=true)` -- preview changes
3. **Sync:** `twincat_plcproj_sync(force=true)` -- write changes
4. **Reload:** `twincat_reload` before `twincat_check_all_objects`
