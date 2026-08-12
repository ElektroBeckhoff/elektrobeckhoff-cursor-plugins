---
name: twincat3-umrt-systemtest
description: >-
  End-to-end TwinCAT Usermode Runtime (TC170x) system test via MCP: start UmRT,
  open solution, disable I/O, activate/start, diagnose runtime messages
  (pagefault/license/SAFEOP), PLC RUN, ADS symbol list and batch read/write
  verification. Use when the user asks for UmRT systemtest, runtime E2E,
  ADS smoke, /twincat3-cmd-online-test, or to verify activate + ADS R/W.
  For interactive live ADS after ready_for_ads, use twincat3-live-diagnostics.
---

# TwinCAT Usermode Runtime System Test

Full chain on **Usermode Runtime** (not the real-time IPC target unless the user says so).

## Quick Start

**Prefer one call** when available:

```
twincat_umrt_e2e(sln_path="<path.sln>", xae_version="4026", confirm=true)
```

Or walk steps manually:

```
Task Progress:
- [ ] 0. Prerequisites / ask user (licenses) if unknown
- [ ] 1. UmRT status + start (window_mode=hidden)
- [ ] 2. twincat_open (.sln, xae_version=4026 if Build 4026) — check pin_honored
- [ ] 3. twincat_io_set_disabled(all_devices=true)
- [ ] 4. twincat_set_target(UmRT NetId)
- [ ] 5. twincat_activate → twincat_start — require activate_ok / boot_ok
- [ ] 6. twincat_runtime_messages(since_last_activate=true)
- [ ] 7. twincat_runtime_state — require ready_for_ads (plc_start if needed)
- [ ] 8. twincat_ads_symbols + twincat_ads_read_list + write smoke
- [ ] 9. Report PASS/FAIL checklist
```

Discover tools via `GetMcpTools` on **one** server
(`user-mcp-twincat-local` for local MCP dev, else
`plugin-twincat-ai-toolkit-mcp-twincat`). Do not call both in one turn.

Optional CLI helper (same steps, no agent):

```
python mcp-servers/mcp-twincat/systemtest/umrt_chain.py --sln "<path.sln>" --xae-version 4026
```

## Prerequisites

| Need | Notes |
|------|--------|
| TwinCAT **4026** + TC170x UmRT | Engineering on 4024/4022 with UmRT is unsupported |
| 7-day trial / runtime licenses on UmRT | **Manual** in XAE (SYSTEM→License). AI cannot enter the security code. Ask in Step 0 if unknown. Blocking `user_action_required` appears only when `licenses_ok=false` / license findings — not on every UmRT start |
| Sample or app `.sln` | Prefer full path to `.sln` |

Read also: `rules/twincat3-mcp-runtime.mdc`.

### Library export during online-test (time saver)

If the live diagnose needs a fresh library export/install before activate,
export **only** `.library` — skip `.compiled-library` to save time:

```
twincat_export_library(library=true, compiled_library=false, wait=false, timeout_seconds=1800)
# poll twincat_export_progress until running=false
```

This shortcut applies **only** to `/twincat3-cmd-online-test` / this skill.
For `/twincat3-cmd-new-version`, `/twincat3-cmd-release`, or any library update,
always export **both** `.library` and `.compiled-library` (skills
`twincat3-new-version` / `twincat3-release`, rule `twincat3-mcp-build`).

### Timing on UmRT (TON / TOF / TIME) — by design

InfoSys TC170x **Limitations** (`tc170x_tc3_usermode_runtime/1033/11319889035.html`, DE: `…/1031/…` **Limitierungen**):

- No guaranteed deterministic execution; Windows may interrupt UmRT at any time.
- Min. task base time 1 ms; execution times / jitter can affect function.
- Some functions need a constant real-time tick (unlike IPC RT).

→ Timers (`TON`, `TOF`, `TIME`, cycle waits) often appear **slower or less precise** in wall-clock time than on a real-time target. **This is intentional UmRT behaviour.**  
In verification: wait longer / poll `Q`/`bDone` via ADS; do **not** FAIL only because elapsed wall time exceeds the configured `PT` compared to IPC.

## Step 0 — Ask user if licenses unknown

If UmRT was never licensed on this PC/instance, ask:

> Please activate 7-day trial licenses on the UmRT target (SYSTEM→License → 7 Days Trial License) for TC3 PLC and any TF* used. Confirm when done.

Do not spin activate/start retries on license errors.

## Step 1 — Usermode Runtime

```
twincat_umrt_status()
twincat_umrt_start(confirm=true, window_mode="hidden")
```

- Record `ams_net_id` / instance name from the response.
- Prefer `window_mode="hidden"` for MCP (no console). Run mode via COM/`twincat_start`, not key `r`.
- I/O may appear as non-blocking prerequisite. Ask user only when `ask_user=true`
  (e.g. real license failure later, or non-UmRT target).

## Step 2 — Open solution

```
twincat_open(path="<sln>", xae_version="4026")
```

Prefer `.sln`. Check `success`, `pin_honored`, `attached_xae_version`,
`created_new_instance`, `plc_project_name`.

## Step 3 — Disable physical I/O

UmRT has no EtherCAT; active I/O → SAFEOP / AdsError 1823.

```
twincat_io_list()
twincat_io_set_disabled(all_devices=true, disabled=true, confirm=true)
```

## Step 4 — Target = UmRT

```
twincat_set_target(net_id="<umrt ams_net_id>", confirm=true)
twincat_get_target()  # must match UmRT
```

Do **not** leave the Beckhoff IPC (e.g. C6015) as target unless the user explicitly wants that.

## Step 5 — Activate + Start

```
twincat_activate(confirm=true)
twincat_start(confirm=true)
```

Require `activate_ok` / `boot_ok` (and `status=success`). Do **not** parse
Output-log tails (“erfolgreich”). Inspect `runtime_findings` /
`has_blocking_runtime_error` / `licenses_ok`.

## Step 6 — Runtime messages / diagnose

```
twincat_runtime_messages(since_last_activate=true)
```

| Finding id | Action |
|------------|--------|
| `license` | Ask user for trial licenses; stop (`licenses_ok=false`) |
| `page_fault` / `fatal` / `exception` | FAIL — report matched lines; do not continue ADS |
| `safeop_aborted` | Ensure I/O disabled; re-activate; if persists, FAIL |
| none | Continue |

Also useful: `twincat_status` for dialogs / `prereqs` / `sys_manager_errors`.

## Step 7 — System + PLC ADS state

```
twincat_runtime_state()                    # expect ready_for_ads=true
twincat_plc_start(confirm=true, port=851)  # if ready_for_ads false / PLC not RUN
twincat_runtime_state()
```

`ready_for_ads` requires system **and** PLC AdsState RUN. System RUN alone is
not enough. After activate, PLC port 851 may stay **INVALID** until
`twincat_plc_start`.

## Step 8 — ADS symbols + R/W verify

```
twincat_ads_symbols(prefix="<PROG>.", max_symbols=50)
```

Pick concrete scalar paths (BOOL/INT/UINT/REAL). Avoid whole-FB/ENUM reads without type (pyads `NoneType`).

**Batch read (preferred for many vars):**

```
twincat_ads_read_list(symbols='["PROG.fbX._bFlag", "PROG.stControl.bOn"]')
```

**Write smoke + verify** (use a non-critical private/config scalar if possible):

```
twincat_ads_read(symbol="…")
twincat_ads_write(symbol="…", value="…", confirm=true)
twincat_ads_read(symbol="…")   # expect new value (or document cyclic overwrite)
```

Or batch:

```
twincat_ads_write_list(values='{"path": value}', confirm=true)
twincat_ads_read_list(symbols='["path"]')
```

### Path rules (short)

- Full instance path; nested/private `_` OK even if missing from `twincat_ads_symbols`
- `{attribute 'hide'}` on **entire FB type**: members still R/W via derived instance path
- `{attribute 'hide'}` on **single** var/PROPERTY/VAR_STAT: not found (1808)

## Step 9 — Report

Return a compact checklist:

```
UmRT systemtest
- UmRT start:     PASS/FAIL  (net_id=…, window=hidden)
- Open solution:  PASS/FAIL
- I/O disabled:   PASS/FAIL
- Target UmRT:    PASS/FAIL
- Activate/Start: PASS/FAIL
- Runtime msgs:   PASS/FAIL  (findings=…)
- Sys RUN:        PASS/FAIL
- PLC RUN:        PASS/FAIL
- ADS read_list:  PASS/FAIL  (n=…)
- ADS write:      PASS/FAIL  (path=…, note=cyclic overwrite?)
```

Overall **PASS** only if all required steps PASS (write may PASS with note if PLC overwrites within 1 cycle but t+0 read showed the write).

## Fail-fast

- License / page_fault / fatal → stop, ask user or report; no ADS spam
- Missing UmRT install → tell user to install TC170x workload
- Do not switch back to IPC target unless asked
- Do not `twincat_close` unless user asks or XAE is stuck
- If any activate/start/plc_*/set_runtime_mode result has
  `target_is_mcp_umrt: false` / `non_umrt_target_control` → **stop**, tell the
  user you would control a real/external target, and only continue if they
  explicitly want that (not a silent UmRT test)
- Timer/TON wall-clock slower than on IPC → **not** a fail (UmRT Limitations)

## Related

- Rule: `twincat3-mcp-runtime`
- Command: `/twincat3-cmd-online-test`
- After `ready_for_ads`: interactive ADS / timed Python →
  `/twincat3-cmd-live-diagnostics` (skill `twincat3-live-diagnostics`)
- Helper: `mcp-servers/mcp-twincat/systemtest/umrt_chain.py`
