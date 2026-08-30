# Local Development Tools (`.dev`)

This folder contains helper scripts for local development of the `twincat-ai-toolkit` Cursor plugin and VS Code extension.

## Scripts Overview

| Script | Purpose |
| :--- | :--- |
| **`sync_to_cache.py`** | **All-in-One Synchronizer**: Builds `.vsix`, installs/updates the extension into Cursor, and syncs all Rules, Skills, Agents, Commands, and MCP-Server files to Cursor's plugin cache. |
| **`sync-to-cursor-cache.ps1`** | PowerShell wrapper for `sync_to_cache.py`. |
| **`sync-to-cursor-cache.bat`** | Windows double-click batch file for `sync_to_cache.py`. |
| **`install-extension.ps1`** | **Extension only**: Builds & installs/updates *only* the `twincat-iecst` VS Code extension in Cursor. |
| **`install-extension.bat`** | Windows double-click batch file for `install-extension.ps1`. |

## How to use

### Option 1: Full Plugin + Extension Update (Recommended for Dev)
Runs everything in one go:
```powershell
python plugins/twincat-ai-toolkit/.dev/sync_to_cache.py
```
*(To skip installing the extension, pass `--no-install-ext`).*

### Option 2: Only Update the VS Code Extension
If you only edited syntax highlighting (`iecst.tmLanguage.json`) or extension TypeScript code:
```powershell
.\plugins\twincat-ai-toolkit\.dev\install-extension.ps1
```

---

After running the sync, reload Cursor to apply all changes:
`Ctrl + Shift + P` -> **Developer: Reload Window**
