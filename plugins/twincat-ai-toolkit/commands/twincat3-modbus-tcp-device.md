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

## Instructions

Look up all relevant rules and skills for Modbus TCP, naming, formatting, comments, and XML formats. Read and follow them completely before generating code.

Generate all required files: data struct, control struct, helper functions, device FB with state machine, .plcproj registration. Generate GUIDs with `[guid]::NewGuid()`.
