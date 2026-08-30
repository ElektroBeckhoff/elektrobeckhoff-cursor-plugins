---
name: twincat3-cmd-check-syntax
description: Run fast headless TwinCAT3 syntax and semantic checks via MCP twincat_check_syntax.
---

# Fast Syntax & Semantic Check

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-check-syntax/SKILL.md`
2. `rules/twincat3-mcp-syntax.mdc`

## Do

1. Run `twincat_check_syntax(path="<file | folder | .sln | empty>")`.
2. Review `error_count`, `warning_count`, and `diagnostics[]`.
3. If errors are found, fix them in code and re-check.
4. Report a concise summary of the validation results.
