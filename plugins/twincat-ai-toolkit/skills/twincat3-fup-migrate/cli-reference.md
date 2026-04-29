# CLI Reference: FBD/FUP Migrator

The migrator can also be called directly from the command line.

## Synopsis

```bash
python twincat_fup_to_st_migrator.py --input <PATH> [OPTIONS]
```

## Commands by Use Case

### Analyze FBD structure (read-only)

```bash
python twincat_fup_to_st_migrator.py --input "C:\Project\POUs\MyProg.TcPOU" --analyze-only
```

### Preview migration (read-only)

```bash
python twincat_fup_to_st_migrator.py --input "C:\Project\POUs\MyProg.TcPOU" --dry-run
```

### Migrate single file (swap mode, default)

```bash
python twincat_fup_to_st_migrator.py --input "C:\Project\POUs\MyProg.TcPOU"
```

### Migrate single file (safe, no-swap)

```bash
python twincat_fup_to_st_migrator.py --input "C:\Project\POUs\MyProg.TcPOU" --no-swap
```

### Migrate folder recursively (swap mode)

```bash
python twincat_fup_to_st_migrator.py --input "C:\Project\POUs" --recursive
```

### Replace in-place (destructive)

```bash
python twincat_fup_to_st_migrator.py --input "C:\Project\POUs\MyProg.TcPOU" --replace
```

### Strict mode (safety-critical)

```bash
python twincat_fup_to_st_migrator.py --input "C:\Project\POUs" --recursive --strict
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All files processed successfully |
| 1 | At least one file failed, or no supported files found |

## Output Files

| File | Created when | Content |
|------|-------------|---------|
| `*_fup_backup_*.TcPOU` | Swap mode (single file) | Original FBD file |
| `*_FUP_Backup_*.TcPOU` | Replace mode | Original FBD file |
| `*_ST_Generated.TcPOU` | No-swap mode (single file) | Generated ST file |
| `*_fup_backup_<ts>/` | Swap mode (folder) | Mirror directory with originals |
| `*_st_generated_<ts>/` | No-swap mode (folder) | Mirror directory with ST files |
| `*_migration_log_*.txt` | Unless `--no-log` | Detailed migration log |
| `*_migration_report_*.txt` | Unless `--no-report` | Per-file summary and checklist |

## Parameter Priority

```
--dry-run > --analyze-only > --replace > --swap > --no-swap
```
