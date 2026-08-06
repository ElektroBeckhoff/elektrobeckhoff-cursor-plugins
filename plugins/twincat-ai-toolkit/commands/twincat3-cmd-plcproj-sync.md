---
name: twincat3-cmd-plcproj-sync
description: Verify and sync TwinCAT .plcproj against disk (verify-first, backup; optional GUID repair).
---

# PlcProject Sync

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-plcproj-sync/SKILL.md`
2. `rules/twincat3-plcproj-safety.mdc`
3. `rules/twincat3-plcproj.mdc`

## Do

1. Follow the plcproj-sync skill (verify â†’ dry-run â†’ sync).
2. Never skip verify/dry-run unless the user explicitly allows.
3. XAE compile only if the user explicitly asks.
