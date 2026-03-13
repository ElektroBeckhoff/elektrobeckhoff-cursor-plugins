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

## Instructions

Look up all relevant rules and skills for Modbus RTU, naming, formatting, comments, and XML formats. Read and follow them completely before generating code.

Generate all required files: data struct, control struct, BYTE helper functions, device FB with state machine + FIFO buffer, MAIN example, .plcproj registration. Generate GUIDs with `[guid]::NewGuid()`.
