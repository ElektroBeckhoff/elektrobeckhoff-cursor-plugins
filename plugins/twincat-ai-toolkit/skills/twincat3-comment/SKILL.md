---
name: twincat3-comment
description: >-
  Comment pass for one TwinCAT object using (* *) only: FB/FUNCTION/PROGRAM,
  STRUCT DUT, or ENUM DUT. Density from twincat3-comments pseudocode.
  Use for /twincat3-cmd-comment.
---

# Comment Object (FB / DUT)

Repeatable **comment pass** for **one** object. Density target is the inline
pseudocode in `rules/twincat3-comments.mdc` and
`skills/twincat3-code-style/references/comment-rules.md` — not denser, not bare.

| Kind | File | What to comment |
|------|------|-----------------|
| FB / FUNCTION / PROGRAM | `.TcPOU` | Header, I/O, VAR groups, body phases, methods |
| STRUCT | `.TcDUT` | TYPE header, section headers, every member EOL |
| ENUM | `.TcDUT` | TYPE purpose (optional), every enumerator EOL |

Do **not** open external library repos for style examples.

## Hard rules

- **One object** per invocation (ask which if several paths given)
- Comment-only — **no** behavior / logic / GUID / attribute changes (keep existing `{attribute …}`)
- English `(* *)` only — never `//` in ST CDATA
- Adapt rule pseudocode — do not invent a new comment system
- Do not commit unless the user runs `/twincat3-cmd-commit` or asks

## Flow

```
Task Progress:
- [ ] Step 1: Resolve one target path — ask if unclear
- [ ] Step 2: Detect kind (POU / STRUCT / ENUM)
- [ ] Step 3: Read twincat3-comments.mdc — density for that kind
- [ ] Step 4: Diff against checklist for that kind
- [ ] Step 5: Apply comment-only edits
- [ ] Step 6: Optional STweep format of that object only
- [ ] Step 7: Report what was added/changed; ask before commit
```

## Density by kind

**ST examples SoT:** `skills/twincat3-code-style/references/comment-rules.md`
(§ FB header, VAR_INPUT/OUTPUT, STRUCT DUT, ENUM DUT). **Read** that file before
editing; do not paste duplicates here.

### POU (FB / FUNCTION / PROGRAM)

- Header above declaration
- Every `VAR_INPUT` / `VAR_OUTPUT` EOL
- `VAR`: section headers; selective private EOL
- Body: prose before phases
- Methods: header when contract/OC/order matters

### STRUCT DUT

- Multi-line purpose above `TYPE` when the struct is non-trivial
- Large structs: `(* --- Section --- *)` headers between groups
- **Every** member has EOL `(* *)` (units, TRUE-meaning, zero-if-empty notes)
- Nested STRUCT / ARRAY members: same rule

### ENUM DUT

- Keep existing attributes unchanged
- **Every** enumerator has EOL `(* *)` — short meaning, not the numeric value alone
- Optional one-line purpose above `TYPE` if the enum is non-obvious

## Checklist

### All kinds

- [ ] No `//` in CDATA
- [ ] No obvious narration / identifier echo
- [ ] Density matches rule pseudocode for that kind

### POU

- [ ] Header above `FUNCTION_BLOCK` / `FUNCTION` / `PROGRAM`
- [ ] Every `VAR_INPUT` / `VAR_OUTPUT` inline
- [ ] `VAR` section headers when large; selective private EOL
- [ ] Non-trivial methods have headers
- [ ] Body phase/invariant blocks where useful

### STRUCT

- [ ] Purpose header above `TYPE` (multi-line if complex)
- [ ] Section headers when large (`(* --- … --- *)`)
- [ ] Every STRUCT member has inline `(* *)`

### ENUM

- [ ] Every enumerator has inline `(* *)`
- [ ] Attributes left intact

## Distilled rules

1. Syntax: only `(* *)`
2. Public members / I/O / enumerators: always commented
3. VAR (private): section headers; selective EOL
4. STRUCT sections: dash headers OK for large grouped structs
5. Body (POU): prose before phases — not `bDone := TRUE` narration
6. Avoid: whole-library silent rewrite; changing logic/GUIDs/attributes

Report-only gaps: agent `twincat-comment-auditor`.
