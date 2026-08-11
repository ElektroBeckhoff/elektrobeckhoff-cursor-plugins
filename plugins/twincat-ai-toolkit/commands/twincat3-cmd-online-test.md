---
name: twincat3-cmd-online-test
description: >-
  Full TwinCAT online test on Usermode Runtime — UmRT start, activate, runtime
  diagnose, ADS read/write verification (E2E).
---

# Online Test (Usermode Runtime)

Full end-to-end online run on **MCP Usermode Runtime** (not the IPC unless the user explicitly asks).

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-umrt-systemtest/SKILL.md`
2. `rules/twincat3-mcp-runtime.mdc`

## Do

1. Follow the UmRT systemtest skill end-to-end (checklist in the skill).
2. Require a `.sln` path (ask user if unknown). Prefer TwinCAT **4026**.
3. Prefer `twincat_umrt_e2e(sln_path=…, confirm=true)` when available; else
   walk skill steps. Discover via `GetMcpTools` on **one** server:
   `user-mcp-twincat-local` (local MCP dev) or
   `plugin-twincat-ai-toolkit-mcp-twincat` (team). Do not call both in one turn.
   Optional CLI: `python mcp-servers/mcp-twincat/systemtest/umrt_chain.py --sln "<sln>"`.
4. Honour `target_is_mcp_umrt` / `non_umrt_target_control` — stop and ask if
   the target is a real IPC. Use `activate_ok` / `ready_for_ads` (not log tails).
5. On license (`licenses_ok=false`) / page_fault / fatal findings: **stop and ask the user** — do not loop activate.
6. Finish with the PASS/FAIL checklist from the skill.
7. Remember: on UmRT, `TON`/`TOF`/timers often run slower in wall-clock time than
   on a real-time target (InfoSys TC170x Limitations) — do not treat that as a FAIL.
