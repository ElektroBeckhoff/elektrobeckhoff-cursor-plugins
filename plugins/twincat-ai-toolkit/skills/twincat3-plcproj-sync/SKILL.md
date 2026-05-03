---
name: twincat3-plcproj-sync
description: >-
  TwinCAT 3 PlcProject file operations using the twincat_plcproj_verify and
  twincat_plcproj_sync MCP tools. Covers verifying plcproj-to-disk consistency,
  syncing Compile/Folder ItemGroups from disk, and optional GUID repair.
  Use when adding/removing TcPOU/TcDUT/TcGVL files, when the plcproj is out of
  sync, or when object GUIDs need repair.
---

# Sync TwinCAT 3 PlcProject File

## When to Use

- User added or removed .TcPOU / .TcDUT / .TcGVL / .TcIO files on disk
- User asks to sync, update, or fix the .plcproj file
- User asks to verify whether the .plcproj matches the project on disk
- User asks to repair object GUIDs in TwinCAT source files
- After creating new POUs/DUTs/GVLs that need to be registered in the project

## Quick Start

```
Task Progress:
- [ ] Step 1: Verify (check current state)
- [ ] Step 2: Sync dry-run (preview changes)
- [ ] Step 3: Sync (write changes)
- [ ] Step 4: Reload + validate (if XAE is open)
```

## Step 1: Verify (check current state)

```
twincat_plcproj_verify(input="<path to project root or .plcproj>")
```

Read the output. Check:
- Whether plcproj matches disk (success=true means no drift)
- Missing Compile entries (files on disk not in plcproj)
- Extra Compile entries (in plcproj but not on disk)
- Missing/extra Folder entries

If success=true, no sync needed.

## Step 2: Sync dry-run (preview changes)

```
twincat_plcproj_sync(input="<path>", force=true, dry_run=true)
```

This previews what would change without writing anything.

**Why force=true?** Without force, sync only writes when verify passes (rare).
After adding/removing files, force is needed to skip the verify gate and
rebuild from disk.

## Step 3: Sync (write changes)

**Default mode (with backup):**
```
twincat_plcproj_sync(input="<path>", force=true)
```
Creates a timestamped .plcproj.bak backup, then writes the updated plcproj.

**With GUID repair:**
```
twincat_plcproj_sync(input="<path>", force=true, ensure_object_guids=true)
```
Also fixes missing/duplicate/invalid Id attributes in Tc* source files.

**Without backup (only if user explicitly requests):**
```
twincat_plcproj_sync(input="<path>", force=true, backup=false)
```

## Step 4: Reload + validate

> **CRITICAL:** The .plcproj is a structural file. After modifying it,
> XAE must reload the solution before compiling.

If XAE is open:
```
twincat_reload()
twincat_check_all_objects()
```

If XAE is not open, the user will see the changes when they next open the
solution in TwinCAT XAE.

## Troubleshooting

- **"Could not find Compile ItemGroup block"**: The .plcproj has an
  unexpected structure. Check for manual edits or corruption.
- **"Multiple .plcproj"**: Specify the exact .plcproj path instead of
  the project root directory.
- **Verify fails after sync**: Files may have been added/removed between
  verify and sync. Rerun with force=true.
