---
name: twincat3-modbus
description: Create Modbus device integrations for both TCP (Tc2_ModbusSrv) and RTU (Tc3_ModbusRtuEB). Shared state machine architecture with protocol-specific patterns for WORD/BYTE buffers, type conversion, and communication FBs. Use when adding any Modbus device (energy meters, inverters, chargers, sensors) over TCP or serial RTU.
---

# Create Modbus Device Integration

> **Architecture & shared rules:** See `twincat3-modbus.mdc` for the unified state machine architecture, step-pair pattern, error handling, and timing rules that apply to both TCP and RTU.

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

Follow Rule 2.16: Use a single `ST_[Device]_Data` struct.

### TCP Example (REAL/LREAL with gain factors)

```iecst
TYPE ST_[Device]_Data :
STRUCT
    fVoltageL1    : REAL;  // [V] L1 Phase voltage (Gain 0.1) - Reg 1000
    fCurrentL1    : REAL;  // [A] L1 Phase current (Gain 0.01) - Reg 1001
    fActivePower  : LREAL; // [W] Active power (S32) - Reg 1010-1011
    nFaultState   : UINT;  // 0=OK, 1=Fault - Reg 1020
END_STRUCT
END_TYPE
```

### RTU Example (REAL/DINT from raw bytes)

```iecst
TYPE ST_[Device]_Data :
STRUCT
    fCurrent_A_L1          : REAL; // [A] L1 - Reg. 2
    fVoltage_V_L1_N        : REAL; // [V] L1-N - Reg. 10
    fPower_W_total         : REAL; // [W] total - Reg. 40
    nEnergy_Import_total_Wh : DINT; // [Wh] Import total - Reg. 180
END_STRUCT
END_TYPE
```

Rules:
- Use REAL for 16-bit values with gain, LREAL for 32-bit values (TCP)
- Document unit, gain, and register address in comments

## Step 3: Helper Functions

Choose the correct pattern file based on transport protocol:

- **TCP** → See [modbus-tcp-patterns.md](modbus-tcp-patterns.md): WORD-based helpers (`F_[Device]_Uint16`, `F_[Device]_int32`, `F_IEEE32_TO_REAL`)
- **RTU** → See [modbus-rtu-patterns.md](modbus-rtu-patterns.md): BYTE-based helpers (`F_[Device]_Real`, `F_[Device]_DINT`, `F_[Device]_UDINT`)

### Helper Function Naming Convention

| Function | Purpose | TCP Signature | RTU Signature |
|---|---|---|---|
| `F_[Device]_Uint16` | U16 with sentinel check | `(in : WORD)` | `(b1, b2 : BYTE)` |
| `F_[Device]_int16` | S16 with sentinel check | `(in : WORD)` | `(b1, b2 : BYTE)` |
| `F_[Device]_Uint32` | U32 big-endian | `(in1, in2 : WORD)` | `(b1, b2, b3, b4 : BYTE)` |
| `F_[Device]_int32` | S32 big-endian | `(in1, in2 : WORD)` | `(b1, b2, b3, b4 : BYTE)` |
| `F_[Device]_Real` | IEEE 754 FLOAT32 | `(in1, in2 : WORD)` | `(b1, b2, b3, b4 : BYTE)` |

## Step 4: FB Structure

### Shared VAR_INPUT

```iecst
VAR_INPUT
    bReadEnable   : BOOL := TRUE;
    bWriteEnable  : BOOL := FALSE;
    tReadInterval : TIME := T#5S;
    stControl     : ST_[Device]_Control;
END_VAR
```

---

### TCP-Specific

**Required Library:** `Tc2_ModbusSrv`

**Additional VAR_INPUT:**
```iecst
    sIPAddr  : STRING;           // Device IP address (no default — must be set)
    nUnitID  : BYTE := 1;       // Modbus TCP slave ID
    nTCPPort : UINT := 502;     // Modbus TCP port
    tTimeout : TIME := T#5S;    // Communication timeout
```

**VAR (Communication FBs + WORD Buffer):**
```iecst
VAR
    _fbMBReadInputRegs  : FB_MBReadInputRegs;          // FC04 (or FB_MBReadRegs for FC03)
    _arrReadMBData      : ARRAY[0..31] OF WORD;        // Variable size! Must be >= nQuantity. 32 here is just an example.
    _fbMBWriteSingleReg : FB_MBWriteSingleReg;         // FC06
END_VAR
```

**FB Calls (after CASE blocks):**
```iecst
_fbMBReadInputRegs(
    sIPAddr   := sIPAddr,
    nTCPPort  := nTCPPort,
    nUnitID   := nUnitID,
    nQuantity := _nReadQuantity,
    nMBAddr   := _nReadMBAddr,
    cbLength  := _cbReadLength,
    pDestAddr := _pReadDestAddr,
    bExecute  := _bReadExecute,
    tTimeout  := tTimeout,
    bBusy     => bReadBusy);

_fbMBWriteSingleReg(
    sIPAddr  := sIPAddr,
    nTCPPort := nTCPPort,
    nUnitID  := nUnitID,
    nMBAddr  := _nWriteMBAddr,
    nValue   := _nWriteValueU16,
    bExecute := _bWriteExecute,
    tTimeout := tTimeout,
    bBusy    => bWriteBusy);

_bReadExecute  := FALSE;
_bWriteExecute := FALSE;

bError := bReadError OR bWriteError;
bBusy  := bReadBusy OR bWriteBusy;
```

**Busy/Error Access (even steps):**
```iecst
IF NOT _fbMBReadInputRegs.bBusy THEN
    IF NOT _fbMBReadInputRegs.bError THEN ...

// Step 100:
nReadErrorMBAddr := _fbMBReadInputRegs.nMBAddr;
nReadErrId       := _fbMBReadInputRegs.nErrId;
```

**Limits:** Max 125 registers per read (Modbus protocol limit).

**Common Tc2_ModbusSrv FBs:**

| FB | FC | Purpose |
|----|-----|---------|
| `FB_MBReadInputRegs` | FC04 | Read input registers (read-only data) |
| `FB_MBReadRegs` | FC03 | Read holding registers (config + data) |
| `FB_MBWriteSingleReg` | FC06 | Write single 16-bit register |
| `FB_MBWriteRegs` | FC16 | Write multiple registers |
| `FB_MBReadCoils` | FC01 | Read coils (bits) |

---

### RTU-Specific

**Required Libraries:** `Tc3_ModbusRtuEB`, `Tc2_ModbusRTU`, `Tc2_Standard`, `Tc2_System`

**Architecture: FIFO Buffer**

```
Device FBs (FB_ModbusRtu)  -->  ST_ModbusComBuffer (FIFO)  -->  FB_ModbusRtuCom_*  -->  ModbusRtuMasterV2_*
                           <--  Answer via nMessageID       <--                     <--  Serial HW
```

**Additional VAR_INPUT + VAR_IN_OUT:**
```iecst
VAR_INPUT
    nUnitID    : BYTE;              // Modbus slave address (no default — must be set)
    tReadDelay : TIME := T#250MS;   // Delay between consecutive reads
END_VAR
VAR_IN_OUT
    stModbusComBuffer : ST_ModbusComBuffer;  // Shared FIFO buffer
END_VAR
```

**VAR (Communication FBs + BYTE Buffer):**
```iecst
VAR
    _fbModbusRead         : FB_ModbusRtu;
    _eReadModbusFunction  : E_ModbusFunction;
    _nReadUnitID          : BYTE;
    _pReadMemoryAddr      : POINTER TO BYTE;
    _cbLength             : UINT;
    _arrReadMBDataByte    : ARRAY[1..40] OF BYTE;  // Variable size! Must be >= nQuantity * 2 bytes. 40 here is just an example (= max 20 registers).
    _bReadError           : BOOL;                  // Shadow variable for FB error

    _fbModbusWrite        : FB_ModbusRtu;
    _eWriteModbusFunction : E_ModbusFunction;
    _nWriteUnitID         : BYTE;
    _pWriteMemoryAddr     : POINTER TO BYTE;
    _cbWriteLength        : UINT;
    _arrWriteData         : ARRAY[1..4] OF BYTE;
    _bWriteError          : BOOL;
END_VAR
```

**FB Calls (after CASE blocks):**
```iecst
_fbModbusRead(
    stModbusComBuffer := stModbusComBuffer,
    eModbusFunction   := _eReadModbusFunction,
    nUnitID           := _nReadUnitID,
    nQuantity         := _nReadQuantity,
    nMBAddr           := _nReadMBAddr,
    pMemoryAddr       := _pReadMemoryAddr,
    cbLength          := _cbLength,
    bExecute          := _bReadExecute,
    bBusy             => bReadBusy);

_bReadExecute := FALSE;
bReadBusy     := _fbModbusRead.bBusy;
_bReadError   := _fbModbusRead.bError;

_fbModbusWrite(
    stModbusComBuffer := stModbusComBuffer,
    eModbusFunction   := _eWriteModbusFunction,
    nUnitID           := _nWriteUnitID,
    nQuantity         := _nWriteQuantity,
    nMBAddr           := _nWriteMBAddr,
    pMemoryAddr       := _pWriteMemoryAddr,
    cbLength          := _cbWriteLength,
    bExecute          := _bWriteExecute,
    bBusy             => bWriteBusy);

_bWriteExecute := FALSE;
bWriteBusy     := _fbModbusWrite.bBusy;
_bWriteError   := _fbModbusWrite.bError;

bError := bReadError OR bWriteError;
bBusy  := bReadBusy OR bWriteBusy;
```

**Busy/Error Access (even steps) — use shadow variables:**
```iecst
IF NOT bReadBusy THEN
    IF NOT _bReadError THEN ...

// Step 100:
nReadErrorMBAddr := _fbModbusRead.nMBAddr;
nReadErrId       := _fbModbusRead.eErrorId;
```

**Limits:** Max ~20 registers (40 bytes) per read block.

**Hardware Selection:**

| Hardware | Com FB | Master FB | Use case |
|----------|--------|-----------|----------|
| KL6x22B | `FB_ModbusRtuCom_KL6x22B` | `ModbusRtuMasterV2_KL6x22B` | Field bus via EtherCAT |
| PC COM | `FB_ModbusRtuCom_PcCOM` | `ModbusRtuMasterV2_PcCOM` | Direct serial on IPC |

**Supported Modbus Functions:**

| E_ModbusFunction | FC | Description |
|------------------|----|-------------|
| `ReadCoils` | 1 | Read coil status |
| `ReadInputStatus` | 2 | Read input status |
| `ReadRegs` | 3 | Read holding registers |
| `ReadInputRegs` | 4 | Read input registers |
| `WriteSingleCoil` | 5 | Write single coil |
| `WriteSingleRegister` | 6 | Write single register |
| `Diagnostics` | 8 | Diagnostics |
| `WriteMultipleCoils` | 15 | Write multiple coils |
| `WriteRegs` | 16 | Write multiple registers |

## Step 5: MAIN Program Wiring

### TCP

```iecst
PROGRAM MAIN
VAR
    fbDevice : ARRAY[1..4] OF FB_[Device];
END_VAR

fbDevice[1](bReadEnable := TRUE, sIPAddr := '192.168.1.10', nUnitID := 1);
fbDevice[2](bReadEnable := TRUE, sIPAddr := '192.168.1.11', nUnitID := 1);
```

### RTU

```iecst
PROGRAM MAIN
VAR
    fbModbusRtuMaster      : ModbusRtuMasterV2_KL6x22B;
    fbModbusRtuCom_KL6x22B : FB_ModbusRtuCom_KL6x22B(FB_ModbusRtuMaster := fbModbusRtuMaster);
    stModbusComBuffer      : ST_ModbusComBuffer;
    fbDevice               : ARRAY[1..2] OF FB_[Device];
END_VAR

// Communication FB must be called FIRST, every cycle
fbModbusRtuCom_KL6x22B(
    bResetOverflowCounter := ,
    stModbusComBuffer     := stModbusComBuffer,
    bBusy                 =>);

// Device FBs share the same buffer
fbDevice[1](bReadEnable := TRUE, nUnitID := 1, stModbusComBuffer := stModbusComBuffer);
fbDevice[2](bReadEnable := TRUE, nUnitID := 2, stModbusComBuffer := stModbusComBuffer);
```

## Type Conversion & Advanced Patterns

- **TCP** → [modbus-tcp-patterns.md](modbus-tcp-patterns.md): IEEE 754, DWORD buffer, SunSpec discovery, multi-chunk reads (>125 regs)
- **RTU** → [modbus-rtu-patterns.md](modbus-rtu-patterns.md): BYTE helpers, FIFO buffer config, multi-block reads, FB_ModbusRtu internals
