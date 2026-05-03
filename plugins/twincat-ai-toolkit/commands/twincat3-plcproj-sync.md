---
name: twincat3-plcproj-sync
description: Verify and sync TwinCAT .plcproj file against the actual project files on disk.
---

# Sync PlcProject File

Verify that the TwinCAT .plcproj matches the files on disk, and rebuild it if needed.

## Instructions

Follow the `twincat3-plcproj-sync` skill completely. Always verify first, then preview with dry-run, then sync.

The `twincat_plcproj_verify` MCP tool checks for drift (read-only). The `twincat_plcproj_sync` MCP tool rebuilds the Compile and Folder ItemGroups from disk with backup, force, dry-run, and GUID repair options.

After syncing, reload the solution with `twincat_reload` before running `twincat_check_all_objects`.
