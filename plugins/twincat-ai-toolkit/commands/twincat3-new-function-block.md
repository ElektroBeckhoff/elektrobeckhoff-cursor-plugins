---
name: twincat3-new-function-block
description: Create a new TwinCAT3 function block as valid TcPOU XML with GUID.
---

# New Function Block

Create a function block: FB_[NAME]

Purpose: [DESCRIPTION]
Inputs: [LIST]
Outputs: [LIST]

## Required Context

Read and follow these before generating code:

**Rules:** `twincat3-core`, `twincat3-naming`, `twincat3-xml-tcpou`, `twincat3-comments`, `twincat3-formatting`

## Instructions

1. Generate FB as valid TcPOU XML with GUID (`[guid]::NewGuid()`)
2. XML `Name` attribute must match the FUNCTION_BLOCK name in CDATA
3. All VAR_INPUT/VAR_OUTPUT must have inline comments
4. Register the file in `.plcproj`
