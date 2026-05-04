---
name: twincat3-register-plcproj
description: Register TcPOU, TcDUT, or TcGVL files in a .plcproj project file.
---

# Register Files in .plcproj

Register the following files in [PROJECT_NAME].plcproj:

Files:
  [relative/path/to/file.TcPOU]
  [relative/path/to/file.TcDUT]

## Required Context

**Rules:** `twincat3-plcproj`

For automated sync (adding many files, fixing drift), use the `twincat3-plcproj-sync` command with `twincat_plcproj_sync` instead.

## Instructions

Check if files are already registered before adding. Add `<Compile Include="..."><SubType>Code</SubType></Compile>` entries. Add `<Folder Include="..." />` for new folders.
