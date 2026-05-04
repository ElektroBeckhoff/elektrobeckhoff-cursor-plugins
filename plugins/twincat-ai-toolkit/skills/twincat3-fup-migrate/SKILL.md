---
name: twincat3-fup-migrate
description: >-
  TwinCAT 3 FBD/FUP to Structured Text migration using the twincat_fup_migrate
  MCP tool. Covers analysis, dry-run preview, and migration execution with
  backup/swap/force modes. Use when converting FBD/FUP to text-based
  programming or analyzing FBD complexity.
---

# Migrate TwinCAT 3 FBD/FUP to Structured Text

## When to Use

- User asks to convert FBD/FUP to Structured Text
- User asks to migrate a TwinCAT project from graphical to text-based programming
- User wants to analyze FBD complexity before migration
- User wants to preview migration results before writing files
- User wants to process a folder of .TcPOU files recursively

## Quick Start

```
Task Progress:
- [ ] Step 1: Analyze (understand scope)
- [ ] Step 2: Preview (verify quality)
- [ ] Step 3: Migrate (write files)
- [ ] Step 4: Post-migration verification
```

## Step 1: Analyze (understand scope)

```
twincat_fup_migrate(input="<path>", analyze_only=true)
```

Read the output. Check:
- How many files have NWL (FBD) implementation
- How many networks per file
- Whether actions exist

If the input is a folder, add `recursive=true`.

## Step 2: Preview (verify quality)

```
twincat_fup_migrate(input="<path>", dry_run=true)
```

Read the output. Check:
- Generated ST preview (first 50 lines per file)
- TODO count (0 = clean migration, >0 = manual review needed)
- Warning count
- Error count (must be 0 before proceeding)

If errors > 0, report them to the user. Do not proceed.

## Step 3: Migrate (write files)

Choose the appropriate mode based on user intent:

**Safe output (default):**
```
twincat_fup_migrate(input="<path>")
```
Original files untouched. Generated files in `*_st_generated` or `*_st_generated_<ts>/`.

**Swap migration (backup + overwrite original path):**
```
twincat_fup_migrate(input="<path>", swap=true)
```
Swap mode: backup created, ST written to original path.

**Force in-place overwrite (only if user explicitly requests):**
```
twincat_fup_migrate(input="<path>", force=true)
```
Requires explicit user confirmation. Never use `backup=false` with this.

## Step 4: Post-Migration Verification

After any non-dry-run migration, recommend:
1. Open the TwinCAT project in XAE (`twincat_open`)
2. Run `twincat_check_all_objects`
3. Review compiler errors (included in `twincat_check_all_objects` response)
4. Search for `TODO [FBD Migration]` markers in generated code
5. Verify I/O mapping and task assignment
6. Test runtime behavior against original FBD version

## Parameter Quick Reference

| Intent | Parameters |
|--------|------------|
| Read-only analysis | `analyze_only=true` |
| Read-only preview | `dry_run=true` |
| Safe generation | (default, no extra flags) |
| Swap to original path | `swap=true` |
| Folder recursive | `recursive=true` |
| Force in-place overwrite | `force=true` (requires confirmation) |
| Strict mode | `strict=true` (aborts on any TODO) |

## What the Tool Handles

- All IEC 61131-3 FBD operators (AND, OR, NOT, XOR, EQ, NE, GT, LT, GE, LE, ADD, SUB, MUL, DIV, MOD)
- Selection: SEL, MUX, LIMIT, MAX, MIN
- Bitshift: SHL, SHR, ROL, ROR
- Math: ABS, SQRT, LN, LOG, EXP, EXPT, SIN, COS, TAN, ASIN, ACOS, ATAN, TRUNC
- Address: ADR, SIZEOF, BITADR, INDEXOF
- Type conversions: INT_TO_REAL, BOOL_TO_INT, etc.
- Function Block calls with parameter alignment
- Function calls (inline expressions)
- Action calls, EXECUTE blocks (embedded ST snippets)
- RETURN (conditional and unconditional)
- R_TRIG / F_TRIG from InputFlags (auto-generated VAR declarations)
- Demux signal branching (merged into FB calls)
- Multi-output mapping, output negation, type mismatch detection
- OutCommented networks

## What the Tool Does NOT Handle

- CFC (Continuous Function Chart) -- skipped with warning
- SFC (Sequential Function Chart) -- skipped with warning
- IL (Instruction List) -- skipped with warning
- JMP targets -- marked as TODO, requires manual IF/ELSE conversion
- Complex RETAIN/PERSISTENT behavior verification
- Runtime behavior validation (requires TwinCAT build + test)

## Error Handling

- If the tool reports errors for a file, that file was NOT modified
- If swap mode write fails, the original is restored from backup automatically
- If `strict=true` and TODOs exist, migration is aborted for that file
- Binary/corrupted files are detected and skipped gracefully
