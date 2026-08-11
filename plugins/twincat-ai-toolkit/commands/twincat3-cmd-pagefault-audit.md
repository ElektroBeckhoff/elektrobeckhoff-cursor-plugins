---
name: twincat3-cmd-pagefault-audit
description: >-
  InfoSys-only TwinCAT3 page-fault audit (AND vs AND_THEN, POINTER/REFERENCE/
  INTERFACE null checks, __NEW/__DELETE, MEMCPY size, array bounds).
---

# Pagefault Audit (InfoSys-only)

Static review for **MSHC-documented** access-violation / page-fault patterns only.

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-pagefault-audit/SKILL.md`
2. `skills/twincat3-pagefault-audit/checklist.md`
3. `skills/twincat3-pagefault-audit/infosys-evidence.md`
4. `rules/twincat3-pagefault-safety.mdc`

Optional: agent `twincat-pagefault-auditor`.

## Do

1. Follow the skill end-to-end.
2. Resolve scope (ask if needed).
3. Audit **only** kept groups: PF-SC, PF-PTR, PF-REF, PF-IFACE, PF-NEW, PF-MEM, PF-ARR, EX-DIV.
   Include `WHILE`/`REPEAT` conditions (same `AND_THEN` rules; index + `/` guards).
4. Report Check-ID + file:line + InfoSys-tied risk + fix. No invented IDs.
5. Do **not** report out-of-scope items from the checklist.
6. Do **not** modify code unless the user asks after the report.
7. Finish with Coverage + Summary.
