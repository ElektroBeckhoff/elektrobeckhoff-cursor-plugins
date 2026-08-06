---
name: twincat3-cmd-code-style
description: Apply TwinCAT3 ST formatting and comment standards (or review style-only fixes).
---

# Code Style

Respect priority stack in `twincat3-core`: never trade safety/function/performance for style.

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-code-style/SKILL.md`
2. `rules/twincat3-formatting.mdc`
3. `rules/twincat3-comments.mdc`
4. `rules/twincat3-naming.mdc`
5. `rules/twincat3-core.mdc`

If references in the skill point deeper, also Read:

- `skills/twincat3-code-style/references/formatting-rules.md`
- `skills/twincat3-code-style/references/comment-rules.md`

## Do

1. Apply formatting + comments + naming consistently.
2. Style-only edits: stay inside CDATA; do not rewrite line endings or encoding.
3. Prefer DRY over duplicated near-identical blocks when refactoring for style.
