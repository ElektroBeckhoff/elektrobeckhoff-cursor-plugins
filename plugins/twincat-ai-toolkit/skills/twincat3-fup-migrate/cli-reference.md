# CLI Reference: FBD/FUP Migrator

The migrator can also be called directly from the command line.

## Synopsis

```bash
python twincat_fbd_to_st_migrator.py --input <PATH> [OPTIONS]
```

## Commands by Use Case

### Analyze FBD structure (read-only)

```bash
python twincat_fbd_to_st_migrator.py --input "C:\Project\POUs\MyProg.TcPOU" --analyze-only
```

### Preview migration (read-only)

```bash
python twincat_fbd_to_st_migrator.py --input "C:\Project\POUs\MyProg.TcPOU" --dry-run
```

### Migrate single file (safe output, default)

```bash
python twincat_fbd_to_st_migrator.py --input "C:\Project\POUs\MyProg.TcPOU"
```

### Migrate single file (swap mode)

```bash
python twincat_fbd_to_st_migrator.py --input "C:\Project\POUs\MyProg.TcPOU" --swap
```

### Migrate folder recursively (safe output)

```bash
python twincat_fbd_to_st_migrator.py --input "C:\Project\POUs" --recursive
```

### Force in-place overwrite (destructive)

```bash
python twincat_fbd_to_st_migrator.py --input "C:\Project\POUs\MyProg.TcPOU" --force
```

### Strict mode (safety-critical)

```bash
python twincat_fbd_to_st_migrator.py --input "C:\Project\POUs" --recursive --strict
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
| `*_backup_<ts>.TcPOU` | Swap/force mode (single file) | Backup of original FBD file |
| `*_backup_<ts>/` | Swap/force mode (folder) | Backup directory with original FBD files |
| `*_migration_log_*.txt` | Unless `--no-log` | Detailed migration log |
| `*_migration_report_*.txt` | Unless `--no-report` | Per-file summary and checklist |

## Parameter Priority

```
--dry-run > --analyze-only > --force > --swap > default
```
