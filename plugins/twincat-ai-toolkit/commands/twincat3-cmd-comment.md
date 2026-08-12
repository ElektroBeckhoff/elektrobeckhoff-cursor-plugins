---
name: twincat3-cmd-comment
description: >-
  Comment pass for one TwinCAT object (* *): FB/FUNCTION/PROGRAM, STRUCT DUT,
  or ENUM DUT. Density from twincat3-comments inline pseudocode.
---

# Comment Object (FB / DUT)

One object per run (`.TcPOU` or `.TcDUT`). Not a whole-library rewrite.

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-comment/SKILL.md`
2. `rules/twincat3-comments.mdc`
3. `skills/twincat3-code-style/references/comment-rules.md` (optional detail)

Optional:

4. `skills/twincat3-stweep-format/SKILL.md` — if formatting after comments

## Do

1. Follow `twincat3-comment` end-to-end.
2. Resolve **one** target path — ask if unclear. Detect kind: POU vs STRUCT vs ENUM.
3. Use **inline pseudocode** in the comment rule as density target — then
   comment-only edits (English `(* *)` only).
4. Optional: STweep format that object only; optional PF-audit report-only (POU).
5. Report changes; do not commit unless asked (`/twincat3-cmd-commit`).
