---
name: twincat3-infosys-mshc-lookup
description: Look up a Beckhoff TwinCAT type, attribute, or topic from the local offline InfoSys documentation (.mshc).
---

# InfoSys MSHC Lookup

Search and read the local Beckhoff TwinCAT offline documentation for any type, attribute pragma, or topic.

## Required Context

**Skills:** `twincat3-infosys-mshc` (follow completely)

## Instructions

Ask the user what they want to look up (FB, STRUCT, ENUM, attribute, or topic). Then call `twincat_infosys_mshc_search` with `auto_read=true`. Present the structured result: syntax block, inputs/outputs, methods, requirements, and description. Use `language="de"` if the user asks in German or explicitly requests German documentation.
