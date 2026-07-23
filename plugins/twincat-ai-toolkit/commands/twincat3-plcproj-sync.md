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

1. **Verify:** `twincat_plcproj_verify(input="<path>")` -- check current drift
2. **Preview:** `twincat_plcproj_sync(input="<path>", force=true, dry_run=true)` -- preview changes
3. **Sync:** `twincat_plcproj_sync(input="<path>", force=true)` -- write changes
4. **Inform:** Tell the user XAE must reload after `.plcproj` change. Do **not** run `twincat_open` / `twincat_reload` / `twincat_check_all_objects` unless the user explicitly asks to compile / validate thoroughly.
