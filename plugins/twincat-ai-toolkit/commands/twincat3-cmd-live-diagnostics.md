---
name: twincat3-cmd-live-diagnostics
description: >-
  Live TwinCAT ADS diagnostics — MCP symbols/read/write/batch; escalate to
  Python pyads for timed multi-step debug. PLC must already be online.
---

# Live Diagnostics (ADS)

Interactive online diagnose when the PLC is **already** RUN / `ready_for_ads`.
For UmRT bring-up + activate E2E use `/twincat3-cmd-online-test` first.

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-live-diagnostics/SKILL.md`
2. `rules/twincat3-mcp-live-diagnostics.mdc`
3. `rules/twincat3-mcp-runtime.mdc`
4. Timed Python only if needed: `skills/twincat3-live-diagnostics/pyads-patterns.md`

## Do

1. Follow `twincat3-live-diagnostics` end-to-end.
2. Discover tools via `GetMcpTools` on **one** server:
   `user-mcp-twincat-local` or `plugin-twincat-ai-toolkit-mcp-twincat`.
3. Gate on `twincat_runtime_state` → `ready_for_ads`.
4. Default path — MCP:
   - `twincat_ads_symbols` (discover)
   - `twincat_ads_read` / `twincat_ads_read_list`
   - `twincat_ads_write` / `twincat_ads_write_list` with `confirm=true`
5. **Escalate to Python + pyads** only for timed polls, multi-step scenarios,
   runtime watchdog, or markdown suite reports — **Read** `pyads-patterns.md`
   (inline patterns; no external sample-repo requirement).
6. Warn before writes on a real IPC. Stop on page_fault / PLC left RUN and ask.
7. Finish with the skill report template.
