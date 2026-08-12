---
name: twincat3-live-diagnostics
description: >-
  Live TwinCAT diagnostics via MCP ADS (symbols, read/write, batch) and, for
  deeper timed debug, Python pyads script patterns. Use when PLC is already
  online. For /twincat3-cmd-live-diagnostics.
---

# Live Diagnostics (ADS)

Interactive online diagnose **after** the PLC is ready. Does **not** replace
`/twincat3-cmd-online-test` (UmRT bring-up / activate E2E).

```text
Prereq ready_for_ads
  → MCP: symbols / read / write / batch
  → (optional) Python pyads script for timed multi-step debug
  → Report findings
```

## Read first

1. `rules/twincat3-mcp-live-diagnostics.mdc`
2. `rules/twincat3-mcp-runtime.mdc` (UmRT / confirm / NetId defaults)
3. Discover ADS tools: `GetMcpTools` on **one** MCP server
4. Timed / multi-step Python: [pyads-patterns.md](pyads-patterns.md)

## Quick Start

```
Task Progress:
- [ ] Step 0: Scope (NetId, port, program prefix, question)
- [ ] Step 1: Confirm ready_for_ads
- [ ] Step 2: Discover symbols (if paths unknown)
- [ ] Step 3: MCP read / write (batch preferred)
- [ ] Step 4: Escalate to Python only if timed / multi-step needed
- [ ] Step 5: Report
```

## Step 0: Scope

Ask or infer:

- AMS NetId (default: MCP UmRT from `twincat_umrt_status`) + ADS port (usually `851`)
- Program / instance prefix (e.g. `P_Sample.` / `MAIN.`)
- What to prove (read-only inspect vs stimulate with writes)
- IPC vs UmRT — warn before writes on a real IPC

## Step 1: Ready gate

```
twincat_runtime_state()
→ require ready_for_ads == true
```

If not ready: `twincat_plc_start(confirm=true)` or hand off to
`/twincat3-cmd-online-test` for activate/boot. Do not invent NetIds.

Optional: `twincat_runtime_messages(since_last_activate=true)` if the PLC just
booted or behaviour looks dead (license / page_fault / SAFEOP).

## Step 2: Symbol discovery

```
twincat_ads_symbols(prefix="P_Sample.", max_symbols=500)
twincat_ads_symbols(name_contains="fbController", type_contains="FB_")
```

Top-level list often **omits** nested/`_` members — those are still R/W via
full path once you know the instance tree.

## Step 3: MCP read / write (default path)

### Read one

```
twincat_ads_read(symbol="P_Sample.fbDevice._bFlag")
```

### Read many (prefer)

```
twincat_ads_read_list(symbols='["P_Sample.bEnable","P_Sample.fbDevice._nStep"]')
```

### Write one / many

```
twincat_ads_write(symbol="P_Sample.bEnable", value="true", confirm=true)
twincat_ads_write_list(values='{"P_Sample.bEnable":true,"P_Sample._nCmd":1}', confirm=true)
```

`value` is a string for single write (tool parses BOOL/INT/REAL/…). Always
`confirm=true` on writes. Refusal → `error_code=confirm_required`.

### Typical live loop

1. Read baseline (list)
2. Write stimulus (`confirm=true`)
3. Wait briefly if needed (or escalate to Python for precise waits)
4. Read again → compare
5. Restore safe defaults if you changed outputs

## Step 4: Python pyads deep-dive (extended debug)

Use a **local** Python script (`pip install pyads`) when MCP round-trips are too
coarse. **Read** [pyads-patterns.md](pyads-patterns.md) for connect/R/W,
`wait_until`, suite skeleton, RuntimeGuard, and tips.

### When to escalate

| Need | MCP | Python |
|------|-----|--------|
| Spot-check 1–20 symbols | yes | optional |
| Poll until condition / timeout | awkward | **yes** |
| Mid-fade / timed samples | awkward | **yes** |
| Multi-step scenario + markdown report | limited | **yes** |
| Abort if PLC leaves RUN (pagefault) | messages tool | **RuntimeGuard** |

## Step 5: Report

```text
Live diagnostics
- Target: <NetId>:<port> (UmRT|IPC)
- ready_for_ads: yes
- Symbols used: …
- Reads: … (baseline → after)
- Writes: … (confirm=true) | none
- Python script: skipped | <path> (timed waits / suite)
- Findings: …
- Runtime messages: clean | <summary>
```

## Hard stops

- Writes without `confirm=true`
- Continuing after page_fault / PLC left RUN without user decision
- Assuming nested symbols appear in `twincat_ads_symbols` (use full paths)
- Pointing agents at an external library sample repo as required reading —
  patterns live in [pyads-patterns.md](pyads-patterns.md)

## Out of scope

| Topic | Use instead |
|-------|-------------|
| UmRT start / activate / first boot | `/twincat3-cmd-online-test` |
| Static pagefault code audit | `/twincat3-cmd-pagefault-audit` |
| Library release export | `/twincat3-cmd-new-version` / release |
