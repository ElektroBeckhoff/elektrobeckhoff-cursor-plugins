---
name: twincat3-infosys-mshc-lookup
description: Look up a Beckhoff TwinCAT type, attribute, or topic from the local offline InfoSys documentation (.mshc).
---

# InfoSys MSHC Lookup

**Skills:** `twincat3-infosys-mshc` (follow completely)

## Instructions

1. Ask the user what to look up (type name, attribute, or topic)
2. Search with `twincat_infosys_mshc_search` (`auto_read=true` is default)
3. If the name is unknown, use `mode="fulltext"` with descriptive keywords
4. If 0 results, fall back to `twincat3-infosys-lookup` skill (online)
5. Present: syntax block, inputs/outputs, methods, requirements
6. Use `language="de"` if the user requests German documentation
