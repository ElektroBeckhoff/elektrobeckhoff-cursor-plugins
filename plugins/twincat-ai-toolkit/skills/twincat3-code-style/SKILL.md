---
name: twincat3-code-style
description: TwinCAT3 ST code formatting and style rules quick reference. Delegates to detailed references for complete specs.
---

# TwinCAT3 Code Style

The authoritative rules are:
- `twincat3-formatting.mdc` — indentation, alignment, control flow, declarations
- `twincat3-comments.mdc` — I/O comments, headers, section separators

## Quick Decision Table

| Question | Answer |
|---|---|
| Indentation | 4 spaces, never tabs |
| THEN / DO placement | Same line as IF / FOR / WHILE |
| ELSIF / ELSE placement | Column 0 |
| Wrap function calls | >4 params → multiline with aligned `:=` / `=>` |
| Max line length | 200 characters |
| Binary operator wrap | After operator, not before |
| Array initializer wrap | >30 elements → multiline |
| Enum inline wrap | >5 members → multiline |
| VAR_INPUT / VAR_OUTPUT comments | Every variable: `// [unit] Purpose` |
| STRUCT member comments | Every member: `// [unit] Purpose` |
| FB header | `//` one-line purpose before FUNCTION_BLOCK |
| VAR group sections (>=5 vars) | `(* section name *)` header |
| Code logical sections (>=3 related lines) | `(* --- purpose --- *)` separator |
| STRUCT indentation | 4 spaces inside STRUCT |
| Single-line IF | Never — body always on next line |

### Unit Bracket Format

```
// [A] amperes    // [V] volts      // [W] watts
// [kWh] kWh      // [%] percent    // [ms] milliseconds
```

## Reference Files

For complete specifications with all examples, read:
- [references/formatting-rules.md](references/formatting-rules.md)
- [references/comment-rules.md](references/comment-rules.md)
