---
name: twincat3-new-enum
description: Create a new TwinCAT3 enum as valid TcDUT XML with GUID and attribute pragmas.
---

# New Enum

Create an enum: E_[NAME]

Values:
  [VALUE1] = [DESCRIPTION]
  [VALUE2] = [DESCRIPTION]

## Required Context

**Rules:** `twincat3-naming`, `twincat3-xml-tcdut`
**Skills:** `twincat3-attributes` (for `qualified_only` and `strict` pragmas)

## Instructions

Generate as valid TcDUT XML with GUID (`[guid]::NewGuid()`). Always include `{attribute 'qualified_only'}` and `{attribute 'strict'}`. Register in `.plcproj`.
