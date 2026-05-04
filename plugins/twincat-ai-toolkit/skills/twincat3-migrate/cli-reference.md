# CLI Reference: Unified Migrator

The unified migrator can also be called directly from the command line. It auto-detects FBD and CFC per file.

## Synopsis

```bash
python twincat_unified_migrator.py --input <PATH> [OPTIONS]
```

## Commands by Use Case

### Analyze project structure (read-only)

```bash
python twincat_unified_migrator.py --input "C:\Project\POUs" --recursive --analyze-only
```

### Preview migration (read-only)

```bash
python twincat_unified_migrator.py --input "C:\Project\POUs" --recursive --dry-run
```

### Migrate single file (safe output, default)

```bash
python twincat_unified_migrator.py --input "C:\Project\POUs\MyProg.TcPOU"
```

### Migrate single file (swap mode)

```bash
python twincat_unified_migrator.py --input "C:\Project\POUs\MyProg.TcPOU" --swap
```

### Migrate folder recursively (safe output)

```bash
python twincat_unified_migrator.py --input "C:\Project\POUs" --recursive
```

### Force in-place overwrite (destructive)

```bash
python twincat_unified_migrator.py --input "C:\Project\POUs" --recursive --force
```

### Strict mode (safety-critical)

```bash
python twincat_unified_migrator.py --input "C:\Project\POUs" --recursive --strict
```

### Force without backup (dangerous, requires explicit intent)

```bash
python twincat_unified_migrator.py --input "C:\Project\POUs" --recursive --force --no-backup
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All files processed successfully |
| 1 | At least one file failed, or no supported files found |

## Output Files

| File | Created when | Content |
|------|-------------|---------|
| `*_st_generated.TcPOU` | Default mode (single file) | Generated ST file |
| `*_st_generated_<ts>/` | Default mode (folder) | Mirror directory with ST files |
| `*_backup_<ts>.TcPOU` | Swap/force mode (single file) | Backup of original FBD/CFC file |
| `*_backup_<ts>/` | Swap/force mode (folder) | Shared backup with original FBD/CFC files |
| `*_migration_log_*.txt` | Unless `--no-log` | Detailed migration log |
| `*_migration_report_*.txt` | Unless `--no-report` | Per-file summary with FBD/CFC/skip counts |

## Output Summary

The final output line shows the type breakdown:

```
Migration complete. FBD: 26, CFC: 8, Skipped: 24, Failed: 0, Accuracy: 100.00 %
```

## Parameter Priority

```
--dry-run > --analyze-only > --force > --swap > default
```
