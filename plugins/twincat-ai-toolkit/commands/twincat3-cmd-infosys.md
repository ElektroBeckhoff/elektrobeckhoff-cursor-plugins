---
name: twincat3-cmd-infosys
description: Look up Beckhoff TwinCAT3 types/attributes â€” offline MSHC first, web InfoSys only as fallback.
---

# InfoSys Lookup

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-infosys-mshc/SKILL.md`
2. `rules/twincat3-mcp-infosys-mshc.mdc`

If offline search returns **0 results**, then Read and use:

3. `skills/twincat3-infosys-lookup/SKILL.md`

For attribute/pragma questions, also Read:

4. `skills/twincat3-attributes/SKILL.md` (and `references/attributes-reference.md` if needed)

## Do

1. Offline MSHC search/read first (`twincat_infosys_mshc_search` / `_read`).
2. Web fallback only after 0 offline results.
3. Return signature, library requirement, and key parameters â€” cite source path/URL.
