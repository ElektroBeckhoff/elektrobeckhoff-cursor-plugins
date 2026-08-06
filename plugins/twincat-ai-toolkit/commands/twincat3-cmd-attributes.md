---
name: twincat3-cmd-attributes
description: Apply or explain TwinCAT3 IEC 61131-3 attribute pragmas ({attribute '...'}).
---

# Attributes / Pragmas

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-attributes/SKILL.md`
2. `skills/twincat3-attributes/references/attributes-reference.md` (when SKILL quick table is not enough)
3. `rules/twincat3-xml.mdc` (if editing TcPOU/TcDUT Declaration CDATA)

## Do

1. Place `{attribute '...'}` on the line **above** the target declaration (ST rules in skill).
2. Prefer documented Beckhoff attributes; verify unknown ones via `/twincat3-cmd-infosys`.
3. Edit only CDATA when changing existing TwinCAT XML files.
