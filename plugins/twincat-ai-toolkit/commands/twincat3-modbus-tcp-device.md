---
name: twincat3-modbus-tcp-device
description: Create a new Modbus TCP device integration with data struct, control struct, helper functions, device FB with state machine, and .plcproj registration.
---

# New Modbus TCP Device

Create a Modbus TCP integration for: [DEVICE_NAME]

Register map (from datasheet):
[ADDR] x[COUNT] [TYPE] = [DESCRIPTION]
[ADDR] x[COUNT] [TYPE] = [DESCRIPTION]
...

IP: [192.168.1.x], Unit ID: [1], Read Interval: [T#5S]

## Required Context

**Rules:** `twincat3-modbus`, `twincat3-naming`, `twincat3-xml-tcpou`, `twincat3-xml-tcdut`, `twincat3-comments`, `twincat3-formatting`
**Skills:** `twincat3-modbus` (SKILL.md + modbus-tcp-patterns.md)

## Deliverables

1. `ST_[Device]_Data.TcDUT` -- parsed process data
2. `ST_[Device]_Control.TcDUT` -- write control (if write registers exist)
3. `F_[Device]_*.TcPOU` -- type conversion helpers (WORD-based)
4. `FB_[Device].TcPOU` -- device FB with dual state machine
5. Register all files in `.plcproj`
6. Generate GUIDs with `[guid]::NewGuid()`
