---
name: twincat3-modbus
description: Create Modbus device integrations for both TCP (Tc2_ModbusSrv) and RTU (Tc3_ModbusRtuEB). Shared state machine architecture with protocol-specific patterns for WORD/BYTE buffers, type conversion, and communication FBs. Use when adding any Modbus device (energy meters, inverters, chargers, sensors) over TCP or serial RTU.
---

# Create Modbus Device Integration

**Read first**

1. `rules/twincat3-modbus.mdc` — unified state machine, step-pair, error/timing rules
2. Protocol ST templates (do not duplicate here):
   - **TCP** → [modbus-tcp-patterns.md](modbus-tcp-patterns.md)
   - **RTU** → [modbus-rtu-patterns.md](modbus-rtu-patterns.md)

## Quick Start

```
Task Progress:
- [ ] Step 1: Define register map from device datasheet
- [ ] Step 2: Create data struct (ST_[Device]_Data) and control struct (ST_[Device]_Control)
- [ ] Step 3: Create helper functions (WORD-based for TCP, BYTE-based for RTU)
- [ ] Step 4: Create device FB with dual state machine (read + write)
- [ ] Step 5: Wire up MAIN program
- [ ] Step 6: Register all POUs/DUTs in .plcproj
```

## Step 1: Register Map

From the device datasheet, extract for each register group:

| Field | Description |
|-------|-------------|
| Register address | Modbus start address (decimal) |
| Register count | Number of 16-bit registers |
| Data type | U16, S16, U32, S32, FLOAT32/IEEE754, String |
| Function code | FC03 = Holding Registers, FC04 = Input Registers, FC06 = Write Single |
| Byte order | Big-Endian / Little-Endian / Word-swapped |

**Critical:** Identify register gaps — addresses that don't exist MUST be split into separate read operations.

## Step 2: Data Structs

One `ST_[Device]_Data` (rule 9). Document unit, gain, and register address in comments.

- TCP REAL/LREAL + gain example → [modbus-tcp-patterns.md](modbus-tcp-patterns.md) § Data struct
- RTU REAL/DINT example → [modbus-rtu-patterns.md](modbus-rtu-patterns.md) § Data struct

## Step 3: Helper Functions

| Function | Purpose | TCP Signature | RTU Signature |
|---|---|---|---|
| `F_[Device]_Uint16` | U16 with sentinel check | `(in : WORD)` | `(b1, b2 : BYTE)` |
| `F_[Device]_int16` | S16 with sentinel check | `(in : WORD)` | `(b1, b2 : BYTE)` |
| `F_[Device]_Uint32` | U32 big-endian | `(in1, in2 : WORD)` | `(b1, b2, b3, b4 : BYTE)` |
| `F_[Device]_int32` | S32 big-endian | `(in1, in2 : WORD)` | `(b1, b2, b3, b4 : BYTE)` |
| `F_[Device]_Real` | IEEE 754 FLOAT32 | `(in1, in2 : WORD)` | `(b1, b2, b3, b4 : BYTE)` |

Full ST: TCP → [modbus-tcp-patterns.md](modbus-tcp-patterns.md); RTU → [modbus-rtu-patterns.md](modbus-rtu-patterns.md).

## Step 4: FB Structure

Shared inputs: `bReadEnable`, `bWriteEnable`, `tReadInterval`, `stControl`.

| | TCP | RTU |
|---|-----|-----|
| Libraries | `Tc2_ModbusSrv` | `Tc3_ModbusRtuEB`, `Tc2_ModbusRTU`, `Tc2_Standard`, `Tc2_System` |
| Extra inputs | `sIPAddr`, `nUnitID`, `nTCPPort`, `tTimeout` | `nUnitID`, `tReadDelay`; `VAR_IN_OUT stModbusComBuffer` |
| Buffer | `ARRAY[0..N] OF WORD` (≥ `nQuantity`, max 125 regs) | `ARRAY[1..N] OF BYTE` (≥ `nQuantity*2`, ~20 regs/read) |
| Com FBs | `FB_MBReadInputRegs` / `FB_MBReadRegs`, `FB_MBWriteSingleReg` | `FB_ModbusRtu` (+ shadow busy/error) |
| Busy/error | Read from `_fbMB*.bBusy` / `.bError` | Use shadow `_bReadError` / `bReadBusy` |

ST for VAR blocks, FB calls after CASE, busy/error even-steps, hardware/FC tables → pattern file for the transport.

## Step 5: MAIN Program Wiring

- TCP multi-device IP wiring → [modbus-tcp-patterns.md](modbus-tcp-patterns.md) § MAIN
- RTU FIFO + Com-FB-first wiring → [modbus-rtu-patterns.md](modbus-rtu-patterns.md) § MAIN / FIFO

## Type Conversion & Advanced Patterns

- **TCP** → IEEE 754, DWORD buffer, SunSpec, multi-chunk (>125 regs)
- **RTU** → BYTE helpers, FIFO config, multi-block reads, `FB_ModbusRtu` internals
