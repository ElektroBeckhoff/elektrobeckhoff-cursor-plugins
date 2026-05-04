---
name: twincat3-new-gvl
description: Create a new TwinCAT3 global variable list as valid TcGVL XML with GUID.
---

# New GVL

Create a GVL: [Param_LibName / GVL_Domain]

Variables:
  [name] : [TYPE] := [VALUE]; // [DESCRIPTION]
  [name] : [TYPE] := [VALUE]; // [DESCRIPTION]

## Required Context

**Rules:** `twincat3-naming`, `twincat3-xml-tcgvl`

## Instructions

Generate as valid TcGVL XML with GUID (`[guid]::NewGuid()`). Use `VAR_GLOBAL CONSTANT` for param GVLs, `VAR_GLOBAL` for runtime GVLs. Register in `.plcproj`.
