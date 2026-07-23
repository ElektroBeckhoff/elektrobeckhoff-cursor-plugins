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
- [ ] Step 4: Inform user about XAE reload (optional compile only if asked)
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

**Why force=true?** Without `force`, sync **aborts** when verify finds drift
(it will not rewrite an out-of-sync plcproj). After adding/removing files,
`force=true` skips that gate and rebuilds Compile/Folder ItemGroups from disk.

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

## Step 4: After `.plcproj` write — inform, do not auto-compile

Because `.plcproj` changed, XAE needs a **reload** before the next compile. Tell the user that; they can reload in TwinCAT themselves.

Do **not** call `twincat_open` / `twincat_reload` / `twincat_check_all_objects` unless the user **explicitly** asks to validate / compile thoroughly. Only then:
```
twincat_open(path="<.sln preferred, or .plcproj>")
twincat_reload()
twincat_check_all_objects()
```

Never reload for `.TcPOU` / `.TcDUT` / `.TcGVL` content edits alone.

## Troubleshooting

- **"Could not find Compile ItemGroup block"**: The .plcproj has an
  unexpected structure. Check for manual edits or corruption.
- **"Multiple .plcproj"**: Specify the exact .plcproj path instead of
  the project root directory.
- **Verify fails after sync**: Files may have been added/removed between
  verify and sync. Rerun with force=true.
