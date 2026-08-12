---
name: twincat3-cmd-logging
description: Add structured logging with F_IoT_Utilities_MessageLog (levels, edge detect, FormatString).
---

# Structured Logging

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `rules/twincat3-logging.mdc`
2. `skills/twincat3-logging/SKILL.md`
3. `skills/twincat3-logging/logging-patterns.md`
4. `rules/twincat3-naming.mdc`
5. `rules/twincat3-core.mdc`

## Do

1. Follow logging skill + patterns (level filter via Param GVL, edge-detected state logs).
2. Ensure `Tc3_IoT_Utilities` placeholder/reference exists when adding new usage.
3. Prefer DRY helpers over copy-pasted FormatString blocks.
