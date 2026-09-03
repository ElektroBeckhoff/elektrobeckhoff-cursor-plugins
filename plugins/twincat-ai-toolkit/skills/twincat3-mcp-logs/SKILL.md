---
name: twincat3-mcp-logs
description: >-
  Find, inspect, and analyze persistent TwinCAT MCP server logs (mcp-twincat.log).
  Identify MCP server version, diagnose COM/XAE timeouts, modal dialog blockades,
  DTE busy states, and unhandled crashes. Use when MCP tools time out, fail
  unexpectedly, or for /twincat3-cmd-mcp-logs.
---

# TwinCAT MCP Server Log Analysis & Diagnostics

Inspect persistent execution logs to diagnose MCP server behavior, COM automation state, modal dialog interlocks, and tool errors.

```text
Log Path Resolution
  → Check twincat_status() ["log_file"] or %LOCALAPPDATA%\ElektroBeckhoff\logs\mcp-twincat.log
  → Read tail / filter by timestamp, level (ERROR/WARNING), or thread
  → Identify MCP Server Version (version=X.Y.Z) and Python PID
  → Correlate error signature with known root causes
  → Prescribe remediation
```

## Quick Start

```
Task Progress:
- [ ] Step 1: Locate active log file
- [ ] Step 2: Read recent entries / server session header
- [ ] Step 3: Identify MCP Server Version and running PID
- [ ] Step 4: Scan for ERROR, WARNING, and Timeout entries
- [ ] Step 5: Diagnose signature (Dialog, Timeout, COM Busy, Crash)
- [ ] Step 6: Provide concrete remediation steps
```

---

## Step 1: Locate Active Log File

The MCP server maintains persistent rotating logs across executions. Locate the file in order of priority:

1. **Via MCP Tool (Preferred):**
   Call `twincat_status()` and read the returned `log_file` and `mcp_server_version` fields.
2. **Standard Persistent Path:**
   `%LOCALAPPDATA%\ElektroBeckhoff\logs\mcp-twincat.log`  
   (e.g., `C:\Users\<User>\AppData\Local\ElektroBeckhoff\logs\mcp-twincat.log`)
3. **Fallback Paths:**
   - `<plugin-cache>/mcp-servers/mcp-twincat/mcp-twincat.log`
   - `%TEMP%\mcp-twincat.log`

---

## Step 2 & 3: Read Session Header & Version

Each MCP server startup writes a session banner:

```text
2026-09-03 12:13:16.891 [INFO   ] [twincat-mcp:MainThread] TwinCAT MCP logging initialized | version=1.0.0 | log_file='C:\Users\...\mcp-twincat.log' | level=INFO | pid=4368 | python=3.12.6
```

Verify:
- **`version`**: Confirms the loaded MCP code version (e.g. `1.0.0`).
- **`pid`**: Process ID of the running Python MCP server instance.
- **`log_file`**: Confirms active write destination.

---

## Step 4 & 5: Error Signatures & Diagnostic Guide

### 1. Modal Dialog Blockade / Auto-Dismiss

* **Log entries:**
  ```text
  [WARNING] [twincat-mcp:MainThread] dismiss_safe_dialogs: hwnd=42 pattern='file has been changed outside' text='file has been changed outside the environment'
  [WARNING] [twincat-mcp:Dialog-Watcher] Auto-dismissed TcXaeShell dialog (hwnd=12345, pattern='bibliotheksreferenz', text='Die Bibliotheksreferenz wurde geändert...')
  ```
* **Diagnostic:** The `Dialog-Watcher` automatically confirms known safe reload prompts (`IDYES` / `IDOK`).
* **Problem indicator:** If a dialog text is logged that is *not* auto-dismissable (unknown title or custom message box), the STA thread will wait until timeout.
* **Fix:** Check the visible TcXaeShell window and confirm/close the modal dialog manually, or add the new pattern to `_SAFE_DIALOG_PATTERNS`.

### 2. COM STA Call Timeout (`limit=50s`)

* **Log entries:**
  ```text
  [ERROR  ] [twincat-mcp:MainThread] COM STA call 'open_solution' timed out after 50.0s (limit=50s). TcXaeShell / Visual Studio DTE is unresponsive
  ```
* **Diagnostic:** TcXaeShell did not return within the 50s guard limit.
* **Root causes:**
  1. TcXaeShell is currently **Online** with the PLC.
  2. A blocking modal Windows MessageBox is holding the UI thread.
  3. Visual Studio is frozen or busy compiling in background.
* **Fix:** Switch TcXaeShell to Offline mode (F5/Logout), dismiss any modal prompts, or restart the XAE instance.

### 3. RPC Call Rejected (`RPC_E_CALL_REJECTED` / 0x80010001)

* **Log entries:**
  ```text
  [INFO   ] [twincat-mcp:MainThread] Retryable COM error (attempt 1/5): Aufruf wurde durch Aufgerufenen abgelehnt.
  [WARNING] [twincat-mcp:MainThread] SilentMode COM still busy after 6 attempts
  ```
* **Diagnostic:** Visual Studio COM server is temporarily rejecting calls while processing internal UI events.
* **Behavior:** The MCP server automatically retries with exponential backoff up to 6 times. If persistent, TcXaeShell is stuck in a modal loop.

### 4. Multi-Instance / ROT Moniker Mismatch

* **Log entries:**
  ```text
  [INFO   ] [twincat-mcp:MainThread] ROT match: !TcXaeShell.DTE.17.0:23572 has solution 'c:\proj\sample.sln'
  [INFO   ] [twincat-mcp:MainThread] Active session solution mismatch -- searching ROT
  [INFO   ] [twincat-mcp:MainThread] Saved instance to registry: 'C:\proj\Sample.sln' (pid=23572, created_new=False)
  ```
* **Diagnostic:** Multiple TcXaeShell instances are open. The MCP server attaches to the matching solution's PID via the Running Object Table (ROT).

### 5. Top-Level Crash / Unhandled Exception

* **Log entries:**
  ```text
  [CRITICAL] [twincat-mcp.crash:MainThread] Unhandled top-level exception: ...
  [CRITICAL] [twincat-mcp.thread-crash:Thread-X] Unhandled exception in thread '...': ...
  ```
* **Diagnostic:** Top-level exception caught by `sys.excepthook` or `threading.excepthook`. Full traceback is preserved in the log.

---

## Step 6: Log Inspection PowerShell / Python One-Liners

Read the last 40 lines of the active log:
```powershell
python -c "import os; p=os.path.expandvars(r'%LOCALAPPDATA%\ElektroBeckhoff\logs\mcp-twincat.log'); print(open(p, 'r', encoding='utf-8', errors='replace').read()[-4000:] if os.path.exists(p) else 'No log file found')"
```

Filter for warnings and errors only:
```powershell
python -c "import os; p=os.path.expandvars(r'%LOCALAPPDATA%\ElektroBeckhoff\logs\mcp-twincat.log'); lines=[l for l in open(p, 'r', encoding='utf-8', errors='replace') if any(k in l for k in ('[WARNING]', '[ERROR  ]', '[CRITICAL]'))][-30:]; print(''.join(lines))"
```
