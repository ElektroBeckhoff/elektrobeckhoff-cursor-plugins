---
name: twincat3-cfc-migrate
description: >-
  TwinCAT 3 CFC to Structured Text migration using the twincat_cfc_migrate
  MCP tool. Covers analysis, dry-run preview, and migration execution with
  backup/swap/force modes. Use when converting CFC (Continuous Function Chart)
  to text-based programming or analyzing CFC complexity.
---

# Migrate TwinCAT 3 CFC to Structured Text

## When to Use

- User asks to convert CFC to Structured Text
- User asks to migrate a TwinCAT project from graphical CFC to text-based programming
- User wants to analyze CFC complexity before migration
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
twincat_cfc_migrate(input="<path>", analyze_only=true)
```

Read the output. Check:
- How many files have CFC implementation
- How many elements per file
- Whether actions exist

If the input is a folder, add `recursive=true`.

## Step 2: Preview (verify quality)

```
twincat_cfc_migrate(input="<path>", dry_run=true)
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
twincat_cfc_migrate(input="<path>")
```
Original files untouched. Generated files in `*_st_generated` or `*_st_generated_<ts>/`.

**Swap migration (backup + overwrite original path):**
```
twincat_cfc_migrate(input="<path>", swap=true)
```
Swap mode: backup created, ST written to original path.

**Force in-place overwrite (only if user explicitly requests):**
```
twincat_cfc_migrate(input="<path>", force=true)
```
Requires explicit user confirmation. Never use `backup=false` with this.

## Step 4: Post-Migration Verification

After any non-dry-run migration, recommend:
1. Open the TwinCAT project in XAE (`twincat_open`)
2. Run `twincat_check_all_objects`
3. Review compiler errors (included in `twincat_check_all_objects` response)
4. Search for `TODO [CFC Migration]` markers in generated code
5. Verify execution order matches the original CFC behavior
6. Test runtime behavior against original CFC version

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

- All IEC 61131-3 operators (AND, OR, NOT, XOR, EQ, NE, GT, LT, GE, LE, ADD, SUB, MUL, DIV, MOD)
- Selection: SEL, MUX, LIMIT, MAX, MIN
- Bitshift: SHL, SHR, ROL, ROR
- Math: ABS, SQRT, LN, LOG, EXP, EXPT, SIN, COS, TAN, ASIN, ACOS, ATAN, TRUNC
- Type conversions: INT_TO_REAL, BOOL_TO_INT, UDINT_TO_TIME, etc.
- Function Block calls with named parameters
- Operator inlining (nested expressions like `(a EQ b) AND (c EQ d)`)
- Pin negation (NOT on individual inputs)
- CFCInputElement, CFCOutputElement, CFCBoxElement parsing
- CFCInOutPin (VAR_IN_OUT) handling
- Execution order from XML serialization order
- Auto-generated warning header in ST output

## What the Tool Does NOT Handle

- NWL/FBD (Function Block Diagram) -- skipped, use `twincat_fup_migrate` instead
- SFC (Sequential Function Chart) -- skipped with warning
- IL (Instruction List) -- skipped with warning
- Set/Reset pin semantics (not encountered in fixtures, marked as TODO)
- Complex feedback loops with implicit FB output access (e.g. `SR.Q1` without connection)
- Runtime behavior validation (requires TwinCAT build + test)

## Error Handling

- If the tool reports errors for a file, that file was NOT modified
- If swap mode write fails, the original is restored from backup automatically
- If `strict=true` and TODOs exist, migration is aborted for that file
- Binary/corrupted files are detected and skipped gracefully

## CFC-Specific Notes

- CFC has no network concept; all statements are placed in a single network
- Execution order is derived from XML serialization order (reliable for standard and explicit modes)
- Operators (AND, OR, EQ, etc.) are inlined as nested ST expressions, not separate statements
- Function Blocks produce standalone call statements with named parameters
- The generated ST code includes an `AUTO-GENERATED from CFC` warning header
