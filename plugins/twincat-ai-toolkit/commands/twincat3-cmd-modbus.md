---
name: twincat3-cmd-modbus
description: Create or extend a Modbus TCP or RTU device integration (state machine, DUTs, helpers, plcproj).
---

# Modbus Device Integration

Ask/confirm: **TCP or RTU**, device name, register map, connection params (IP/Unit or serial), read interval, write needs.

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-modbus/SKILL.md`
2. `rules/twincat3-modbus.mdc`
3. `rules/twincat3-naming.mdc`
4. `rules/twincat3-xml.mdc`
5. `rules/twincat3-core.mdc`

Then protocol file:

- **TCP:** `skills/twincat3-modbus/modbus-tcp-patterns.md`
- **RTU:** `skills/twincat3-modbus/modbus-rtu-patterns.md`

If only adding writes to an existing FB: still follow skill + `twincat3-modbus.mdc` (dual state machine, write change detection).

## Do

1. Follow the modbus skill + matching patterns file.
2. Deliverables typically: data/control DUTs, helpers, device FB, `.plcproj` registration.
3. Fresh GUIDs; CDATA-only edits on existing files; preserve line endings/encoding.
