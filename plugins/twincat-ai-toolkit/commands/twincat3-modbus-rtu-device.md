---
name: twincat3-modbus-rtu-device
description: Create a new Modbus RTU device integration with data struct, control struct, BYTE helper functions, device FB with state machine and FIFO buffer, and .plcproj registration.
---

# New Modbus RTU Device

Create a Modbus RTU integration for: [DEVICE_NAME]

Register map (from datasheet):
[ADDR] x[COUNT] [TYPE] = [DESCRIPTION]
[ADDR] x[COUNT] [TYPE] = [DESCRIPTION]
...

Unit ID: [1], Baud: [9600], Hardware: [KL6x22B / PcCOM]

## Required Context

**Rules:** `twincat3-modbus`, `twincat3-naming`, `twincat3-xml-tcpou`, `twincat3-xml-tcdut`, `twincat3-comments`, `twincat3-formatting`
**Skills:** `twincat3-modbus` (SKILL.md + modbus-rtu-patterns.md)

## Deliverables

1. `ST_[Device]_Data.TcDUT` -- parsed process data
2. `ST_[Device]_Control.TcDUT` -- write control (if write registers exist)
3. `F_[Device]_*.TcPOU` -- type conversion helpers (BYTE-based)
4. `FB_[Device].TcPOU` -- device FB with dual state machine + FIFO buffer
5. MAIN example with `ST_ModbusComBuffer` wiring
6. Register all files in `.plcproj`
7. Generate GUIDs with `[guid]::NewGuid()`
