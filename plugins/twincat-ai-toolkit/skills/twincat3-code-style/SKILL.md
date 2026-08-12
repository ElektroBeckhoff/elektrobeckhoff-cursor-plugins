---
name: twincat3-code-style
description: TwinCAT3 ST formatting + comment quick reference. Points to rule principles and references/ for full examples.
---

# TwinCAT3 Code Style

The authoritative rules are:
- `rules/twincat3-formatting.mdc` — indentation, alignment, control flow, declarations
- `rules/twincat3-comments.mdc` — I/O comments, headers, prose phase blocks (inline pseudocode)

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
| Comment syntax | **Only** `(* *)` — never `//` |
| VAR_INPUT / VAR_OUTPUT comments | Every variable: `(* [unit] Purpose *)` |
| STRUCT member comments | Every member: `(* [unit] Purpose *)` |
| FB header | `(* … *)` purpose above FUNCTION_BLOCK |
| VAR group sections (>=5 vars) | `(* section name *)` header; selective private EOL |
| Code logical sections | Prose `(* … *)` phase/invariant blocks; dash banners only if file already uses them |
| STRUCT indentation | 4 spaces inside STRUCT |
| Single-line IF | Never — body always on next line |
| Comment density | Match short pseudocode in `rules/twincat3-comments.mdc` / `references/comment-rules.md` |

### Unit Bracket Format

```
(* [A] … *)    (* [V] … *)    (* [W] … *)
(* [kWh] … *)  (* [%] … *)    (* [ms] … *)
```

## Reference Files

For complete specifications with all examples, read:
- [references/formatting-rules.md](references/formatting-rules.md)
- [references/comment-rules.md](references/comment-rules.md)

Per-object comment pass: skill `twincat3-comment` / `/twincat3-cmd-comment`.
