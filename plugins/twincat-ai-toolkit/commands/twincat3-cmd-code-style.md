---
name: twincat3-cmd-code-style
description: Apply TwinCAT3 ST formatting and comment standards (or review style-only fixes).
---

# Code Style

Respect priority stack in `twincat3-core`: never trade safety/function/performance for style.

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `rules/twincat3-formatting.mdc`
2. `rules/twincat3-comments.mdc`
3. `skills/twincat3-code-style/SKILL.md`
4. `skills/twincat3-code-style/references/formatting-rules.md`
5. `skills/twincat3-code-style/references/comment-rules.md`
6. `rules/twincat3-naming.mdc`
7. `rules/twincat3-core.mdc`

## Do

1. Apply formatting + comments + naming consistently.
2. Style-only edits: stay inside CDATA; do not rewrite line endings or encoding.
3. Prefer DRY over duplicated near-identical blocks when refactoring for style.
