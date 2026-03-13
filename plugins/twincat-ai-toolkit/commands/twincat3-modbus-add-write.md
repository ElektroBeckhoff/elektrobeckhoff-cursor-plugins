---
name: twincat3-modbus-add-write
description: Add write functionality to an existing Modbus device FB with control struct, change detection, write state machine, and bWriteEnable.
---

# Add Write to Existing Modbus FB

Add write functionality to FB_[DEVICE_NAME].

Write registers:
[ADDR] [TYPE] = [DESCRIPTION]

## Instructions

Look up the Modbus rules for dual state machine, write change detection, and signed write values. Read and follow them before generating code.

Add: control struct, change detection, write state machine, bWriteEnable.
