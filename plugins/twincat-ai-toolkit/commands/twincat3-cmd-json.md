---
name: twincat3-cmd-json
description: Add JSON parse and/or build logic to a TwinCAT3 FB with Tc3_JsonXml and safe __NEW/__DELETE.
---

# JSON Parse / Build

Ask/confirm: **parse**, **build**, or both; target FB path; payload shape.

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-json-strings/SKILL.md`
2. `skills/twincat3-json-strings/dynamic-strings.md`
3. `rules/twincat3-core.mdc`
4. `rules/twincat3-naming.mdc`
5. `rules/twincat3-xml.mdc`

Then as needed:

- **Parse:** `skills/twincat3-json-strings/json-parse-patterns.md`
- **Build:** `skills/twincat3-json-strings/json-write-patterns.md`

## Do

1. Follow the skill; always validate `__NEW`, pair `__DELETE`, no use-after-free.
2. Edit existing TcPOU only inside CDATA unless adding new Method/Property elements.
