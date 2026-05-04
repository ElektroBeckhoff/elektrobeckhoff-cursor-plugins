---
name: twincat3-modbus-add-write
description: Add write functionality to an existing Modbus device FB with control struct, change detection, write state machine, and bWriteEnable.
---

# Add Write to Existing Modbus FB

Add write functionality to FB_[DEVICE_NAME].

Write registers:
[ADDR] [TYPE] = [DESCRIPTION]

## Required Context

**Rules:** `twincat3-modbus` (dual state machine, write change detection, signed write values)

## Instructions

Add: control struct, change detection via memory struct, write state machine with `_nWriteStep`, `bWriteEnable` input. Follow the step-pair pattern for write operations.
