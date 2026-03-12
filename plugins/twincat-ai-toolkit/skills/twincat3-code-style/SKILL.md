# Skill: twincat3-code-style

## Trigger

Use this skill when:
- Writing or reviewing TwinCAT3 ST code formatting
- Unsure about indentation, alignment, or blank line rules
- Writing comments, headers, or section separators
- Generating DUTs, GVLs, FBs, Functions
- User asks "how should this look" / "is this formatted correctly"

## Quick Reference

### Indentation
| Context | Spaces |
|---|---|
| Inside FUNCTION_BLOCK / FUNCTION body | 4 |
| Inside IF / FOR / WHILE / CASE body | +4 |
| Inside STRUCT members | 8 (TYPE → STRUCT → member) |
| Continuation lines | +4 from statement start |
| CASE body (multi-statement) | align under first statement |

### THEN / DO placement
| Keyword | Placement |
|---|---|
| `THEN` | **Same line** as IF / ELSIF |
| `ELSIF` | col 0 |
| `ELSE` | col 0 |
| `DO` (FOR loop) | **Same line** as FOR |
| `DO` (WHILE loop) | **Same line** as WHILE |

### Function call param count rule
| Params | Format |
|---|---|
| ≤4 | Single line |
| >4 | Multiline, break after `(`, `:=` / `=>` aligned |

### Wrap limits
| Item | Threshold |
|---|---|
| Function call params | >3 → wrap |
| Array initializer elements | >30 → wrap |
| Enum members inline | >5 → wrap |
| Line length | 200 chars |
| Binary operator wrap position | After operator (not before) |

### Mandatory comments
| Location | Comment required |
|---|---|
| VAR_INPUT / VAR_OUTPUT each variable | `// [unit] Purpose` |
| STRUCT members | `// [unit] Purpose` |
| FB / Function header | `//` one-line purpose before declaration |
| VAR group sections (≥5 vars) | `(* section name *)` header |
| Code logical sections (≥3 related lines) | `(* --- purpose --- *)` separator |

### Unit bracket format
```
// [A]    amperes
// [V]    volts
// [W]    watts
// [kWh]  kilowatt-hours
// [%]    percent
// [°C]   celsius
// [ms]   milliseconds
// [s]    seconds
```

## Reference Files

- `references/formatting-rules.md` — complete formatting spec with all examples
- `references/comment-rules.md` — complete comment spec with all examples

Read them when generating any non-trivial TwinCAT3 code.
