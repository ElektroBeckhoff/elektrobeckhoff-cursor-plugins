---
name: twincat3-migrate
description: >-
  Unified TwinCAT 3 FBD/CFC to Structured Text migration using the
  twincat_migrate MCP tool. Auto-detects implementation type per file and
  delegates to the appropriate converter. Use when migrating mixed projects
  or when the user does not specify FBD vs CFC.
---

# Migrate TwinCAT 3 FBD/CFC to Structured Text

## When to Use

- User asks to convert/migrate a TwinCAT project to Structured Text (without specifying FBD or CFC)
- User wants to process a folder that contains both FBD and CFC files
- User says "migrate everything" or "convert all graphical code"
- User points to a folder and wants automatic type detection

If the user explicitly asks for FBD-only or CFC-only, use the dedicated skills `twincat3-fup-migrate` or `twincat3-cfc-migrate` instead.

## Quick Start

```
Task Progress:
- [ ] Step 1: Analyze (understand scope and type mix)
- [ ] Step 2: Preview (verify quality)
- [ ] Step 3: Migrate (write files)
- [ ] Step 4: Post-migration verification
```

## Step 1: Analyze (understand scope)

```
twincat_migrate(input="<path>", analyze_only=true, recursive=true)
```

Read the output. Check:
- Total file count
- FBD (NWL) vs CFC split
- How many files are already ST (skipped)
- Whether any files fail to parse

## Step 2: Preview (verify quality)

```
twincat_migrate(input="<path>", dry_run=true, recursive=true)
```

Read the output. Check:
- Generated ST preview per file
- TODO count (0 = clean migration, >0 = manual review needed)
- Warning count per file
- Error count (must be 0 before proceeding)
- Overall accuracy percentage

If errors > 0, report them to the user. Do not proceed.

## Step 3: Migrate (write files)

Choose the appropriate mode based on user intent:

**Safe output (default):**
```
twincat_migrate(input="<path>", recursive=true)
```
Original files untouched. Generated files in `*_st_generated` or `*_st_generated_<ts>/`.

**Swap migration (backup + overwrite original path):**
```
twincat_migrate(input="<path>", swap=true, recursive=true)
```
Swap mode: backup created, ST written to original path.

**Force in-place overwrite (only if user explicitly requests):**
```
twincat_migrate(input="<path>", force=true, recursive=true)
```
Requires explicit user confirmation. Creates a shared backup folder for all files.

## Step 4: Post-Migration Verification

After any non-dry-run migration, recommend:
1. Open the TwinCAT project in XAE (`twincat_open`)
2. Run `twincat_check_all_objects`
3. Review compiler errors (included in `twincat_check_all_objects` response)
4. Search for `TODO [FBD Migration]` and `TODO [CFC Migration]` markers
5. Verify I/O mapping, execution order, and task assignment
6. Test runtime behavior against original implementations

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
| Skip backup (dangerous) | `backup=false` (requires explicit confirmation) |

## Type Detection

The unified migrator detects each file's implementation type automatically:

| Implementation | Detection | Converter |
|----------------|-----------|-----------|
| NWL (FBD/FUP) | `<NWL>` tag in XML | `twincat_fbd_to_st_migrator` |
| CFC | `<CFC>` tag in XML | `twincat_cfc_to_st_migrator` |
| ST | `<ST>` tag in XML | Skipped (already Structured Text) |
| GVL / DUT | No implementation block | Skipped |
| Broken XML | Parse failure | Reported as error, does not abort batch |

## Shared Backup

When using `force=true` or `swap=true`, a single shared backup folder is created for the entire batch (e.g. `POUs_backup_2026_05_04_084605/`). The folder structure mirrors the original layout.

## Error Isolation

If one file fails to convert, the error is logged and the migrator continues with the remaining files. Failed files are not modified. The final report lists all files with their status.

## Error Handling

- If the tool reports errors for a file, that file was NOT modified
- If swap mode write fails, the original is restored from backup automatically
- If `strict=true` and TODOs exist, migration is aborted for that file
- Binary/corrupted files are detected and skipped gracefully
- A single failed file does not abort the entire batch
