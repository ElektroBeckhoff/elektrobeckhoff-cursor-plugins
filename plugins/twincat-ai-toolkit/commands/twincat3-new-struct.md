---
name: twincat3-new-struct
description: Create a new TwinCAT3 struct as valid TcDUT XML with GUID.
---

# New Struct

Create a struct: ST_[NAME]

Fields:
  [fieldname] : [TYPE] // [DESCRIPTION]
  [fieldname] : [TYPE] // [DESCRIPTION]

## Required Context

**Rules:** `twincat3-naming`, `twincat3-xml-tcdut`, `twincat3-comments`

## Instructions

Generate as valid TcDUT XML with GUID (`[guid]::NewGuid()`). Register in `.plcproj`.
