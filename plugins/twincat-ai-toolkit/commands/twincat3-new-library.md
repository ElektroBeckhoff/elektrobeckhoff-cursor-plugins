---
name: twincat3-new-library
description: Create a new TwinCAT3 PLC library from scratch with complete folder structure, version GVL, param GVL, main FB, data struct, and .plcproj.
---

# New Library

Create a new TwinCAT3 library: Tc3_[LIBNAME]

Purpose: [DESCRIPTION]
Required libraries: [e.g. Tc2_Standard, Tc3_IotBase, Tc2_ModbusSrv]

## Required Context

**Rules:** `twincat3-naming`, `twincat3-versioning`, `twincat3-xml-tcpou`, `twincat3-xml-tcdut`, `twincat3-xml-tcgvl`, `twincat3-plcproj`
**Skills:** `twincat3-new-library` (follow completely)

## Instructions

Generate complete folder structure with all required files: version GVL, param GVL, main FB, data struct, .plcproj. Generate GUIDs with `[guid]::NewGuid()`. Version: 0.0.0.1.
