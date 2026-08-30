# Column-Anchor Indent Spec

Rules implemented in `formatter/st_indent_anchor.py`.

## Settings (from `IndentConfig`)

| Setting | Config key | Default |
|---------|------------|---------|
| Indent size | `indent.size` | 4 |
| Indent THEN | `indent.indent_then_in_if` | false |
| Indent DO | `indent.indent_do_in_for` | false |
| Indent cases | `indent.indent_cases_in_case` | true |
| Indent statements in case | `indent.indent_statements_in_case` | true |
| Indent ELSE case | `indent.indent_else_case` | false |

## Column-anchor rules

| Construct | Anchor column | Body column | Close column |
|-----------|---------------|-------------|--------------|
| IF / ELSIF | IF/ELSIF line | anchor + 4 | END_IF at **anchor** |
| FOR / WHILE | loop head | anchor + 4 | END_FOR/END_WHILE at **anchor** |
| CASE | CASE line | labels at anchor + 4 | END_CASE at anchor |
| CASE label | label line | statements at label + 4 | — |
| CASE section comment | label col if next line is label | else statement col | — |

## Formatting disable regions

Skip formatting inside marked regions (content preserved verbatim):

| Form | Example |
|------|---------|
| Pragma | `{formatting.disable}` … `{formatting.enable}` |
| Comment | `(* formatting.disable *)` … `(* formatting.enable *)` |
| Legacy pragma | `{stweep.disable}` / `{stweep.enable}` |
| Legacy comment | `(* stweep.disable *)` / `(* stweep.enable *)` |

All forms are case-insensitive and may be intermixed.

## Pipeline integration

1. `reindent=true` runs `apply_column_anchor_indentation` (stack walk).
2. Default mode preserves raw line content; stack carries across disable segments.
3. `fix_end_if_indent_safe` applies END_IF dedent for over-indented lines.
4. Bool-chain continuations (`AND_THEN`, `OR_ELSE`, …) are never reindented.
