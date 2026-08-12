# Modbus TCP Patterns

> **Shared patterns** (state machine, step-pairs, delay, error handling, execute flags, interval timer, write change detection) are defined in `rules/twincat3-modbus.mdc`. This file contains **only TCP-specific** implementation details.
>
> Workflow: skill `twincat3-modbus` / `SKILL.md`.

## 0. Data struct (TCP)

```iecst
TYPE ST_[Device]_Data :
STRUCT
    fVoltageL1    : REAL;  (* [V] L1 Phase voltage (Gain 0.1) - Reg 1000 *)
    fCurrentL1    : REAL;  (* [A] L1 Phase current (Gain 0.01) - Reg 1001 *)
    fActivePower  : LREAL; (* [W] Active power (S32) - Reg 1010-1011 *)
    nFaultState   : UINT;  (* 0=OK, 1=Fault - Reg 1020 *)
END_STRUCT
END_TYPE
```

Use REAL for 16-bit values with gain, LREAL for 32-bit values. Document unit, gain, and register address in comments.

## 0b. FB skeleton (TCP)

**Additional VAR_INPUT:**

```iecst
    sIPAddr  : STRING;           (* Device IP address (no default — must be set) *)
    nUnitID  : BYTE := 1;       (* Modbus TCP slave ID *)
    nTCPPort : UINT := 502;     (* Modbus TCP port *)
    tTimeout : TIME := T#5S;    (* Communication timeout *)
```

**Shared VAR_INPUT** (both transports): `bReadEnable`, `bWriteEnable`, `tReadInterval`, `stControl`.

**VAR (communication FBs + WORD buffer):**

```iecst
VAR
    _fbMBReadInputRegs  : FB_MBReadInputRegs;          (* FC04 (or FB_MBReadRegs for FC03) *)
    _arrReadMBData      : ARRAY[0..31] OF WORD;        (* Variable size! Must be >= nQuantity. 32 here is just an example. *)
    _fbMBWriteSingleReg : FB_MBWriteSingleReg;         (* FC06 *)
END_VAR
```

**FB calls (after CASE blocks):**

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

**Busy/error access (even steps):**

```iecst
IF NOT _fbMBReadInputRegs.bBusy THEN
    IF NOT _fbMBReadInputRegs.bError THEN ...

(* Step 100: *)
nReadErrorMBAddr := _fbMBReadInputRegs.nMBAddr;
nReadErrId       := _fbMBReadInputRegs.nErrId;
```

Limits: max 125 registers per read (Modbus protocol).

## 0c. MAIN wiring (TCP)

```iecst
PROGRAM MAIN
VAR
    fbDevice : ARRAY[1..4] OF FB_[Device];
END_VAR

fbDevice[1](bReadEnable := TRUE, sIPAddr := '192.168.1.10', nUnitID := 1);
fbDevice[2](bReadEnable := TRUE, sIPAddr := '192.168.1.11', nUnitID := 1);
```

## 1. WORD-Based Helper Functions (TCP)

TCP uses `ARRAY[0..N] OF WORD` buffers. All helper functions take WORD inputs.

### U16 with Sentinel Check

```iecst
FUNCTION F_[Device]_Uint16 : UINT
VAR_INPUT  in : WORD; END_VAR
VAR_OUTPUT bValid : BOOL; END_VAR

IF in = 16#FFFF THEN
    F_[Device]_Uint16 := 0;
ELSE
    F_[Device]_Uint16 := WORD_TO_UINT(in);
    bValid            := TRUE;
END_IF
```

### S16 with Sentinel Check

```iecst
FUNCTION F_[Device]_int16 : INT
VAR_INPUT  in : WORD; END_VAR
VAR_OUTPUT bValid : BOOL; END_VAR

IF in = 16#8000 THEN
    F_[Device]_int16 := 0;
ELSE
    F_[Device]_int16 := WORD_TO_INT(in);
    bValid           := TRUE;
END_IF
```

### U32 Big-Endian (HIGH Word First)

```iecst
FUNCTION F_[Device]_Uint32 : UDINT
VAR_INPUT
    in1 : WORD;    // First register = HIGH word
    in2 : WORD;    // Second register = LOW word
END_VAR
VAR
    buffer : ARRAY[0..1] OF UDINT;
END_VAR
VAR_OUTPUT bValid : BOOL; END_VAR

buffer[0] := WORD_TO_UDINT(in1);
buffer[1] := WORD_TO_UDINT(in2);

IF (F_[Device]_Uint32 := (SHL(buffer[0], 16) + buffer[1])) = 16#FFFFFFFF THEN
    F_[Device]_Uint32 := 0;
ELSE
    bValid := TRUE;
END_IF
```

### S32 Big-Endian (HIGH Word First)

```iecst
FUNCTION F_[Device]_int32 : DINT
VAR_INPUT
    in1 : WORD;    // First register = HIGH word
    in2 : WORD;    // Second register = LOW word
END_VAR
VAR
    buffer : ARRAY[0..1] OF DINT;
END_VAR
VAR_OUTPUT bValid : BOOL; END_VAR

buffer[0] := WORD_TO_DINT(in1);
buffer[1] := WORD_TO_DINT(in2);

IF (F_[Device]_int32 := (SHL(buffer[0], 16) + buffer[1])) = 16#80000000 THEN
    F_[Device]_int32 := 0;
ELSE
    bValid := TRUE;
END_IF
```

## 2. IEEE 754 FLOAT32 Conversion (Janitza / Eastron SDM)

Some devices (Janitza UMG, Eastron SDM630) return FLOAT32 (IEEE 754) in two consecutive Modbus registers. The standard Beckhoff pattern uses `ROR` + `POINTER TO REAL` to reinterpret raw bits:

```iecst
FUNCTION F_IEEE32_TO_REAL : REAL
VAR_INPUT
    IN : DWORD;
END_VAR
VAR
    BUFFER : DWORD;
    PTREAL : POINTER TO REAL;
END_VAR

BUFFER           := ROR(IN, 16);    // Swap high/low words (Modbus byte order)
PTREAL           := ADR(BUFFER);
F_IEEE32_TO_REAL := PTREAL^;        // Reinterpret raw bits as IEEE 754 float
```

**Never** use `DWORD_TO_REAL` — it performs a value conversion, not a bit reinterpretation.

### DWORD Buffer Pattern

When each Modbus register pair represents one IEEE 754 FLOAT32, use a `DWORD` buffer instead of WORD:

```iecst
VAR
    _arrDaten : ARRAY[1..61] OF DWORD;   // 61 floats = 122 registers
END_VAR

_fbMBReadRegs(
    nQuantity := 122,
    nMBAddr   := 19000,
    cbLength  := SIZEOF(_arrDaten),
    pDestAddr := ADR(_arrDaten),
    bExecute  := TRUE);

stData.fVoltageL1 := F_IEEE32_TO_REAL(_arrDaten[1]);
stData.fVoltageL2 := F_IEEE32_TO_REAL(_arrDaten[2]);
stData.fCurrentL1 := F_IEEE32_TO_REAL(_arrDaten[4]);
```

### WORD Buffer Pattern (Integer Devices like Solplanet)

When registers contain integer types with gain factors, use the standard `WORD` buffer:

```iecst
VAR
    _arrReadMBData : ARRAY[0..31] OF WORD;   // Variable size! Must be >= nQuantity. 32 is just an example.
END_VAR

// U16 with gain
stData.fVoltageL1 := UINT_TO_REAL(F_Device_Uint16(_arrReadMBData[0])) * 0.1;

// S32 from two consecutive WORD registers
stData.fActivePower := DINT_TO_LREAL(F_Device_int32(_arrReadMBData[2], _arrReadMBData[3]));
```

## 3. Sentinel Value Reference

| Type | Sentinel | Meaning |
|------|----------|---------|
| U16 | `0xFFFF` | Not implemented |
| S16 | `0x8000` | Not implemented |
| U32 | `0xFFFFFFFF` | Not implemented |
| S32 | `0x80000000` | Not implemented |
| FLOAT32 | `0xFFFFFFFF` or NaN | Not implemented |
| SunSpec SF | `0x8000` | Not implemented |

## 4. Multi-Chunk Read (>125 Registers)

Modbus limits each read to max 125 registers. For large register blocks, split into chunks using pointer offsets into a shared buffer:

```iecst
VAR
    _arrMBData : ARRAY[1..375] OF WORD;   // 3 x 125 registers
END_VAR

CASE _nReadStep OF
    10: // Chunk 1: registers 0-124
        _nReadQuantity := 125;
        _nReadMBAddr   := nBaseAddr;
        _pReadDestAddr := ADR(_arrMBData[1]);
        _cbReadLength  := 250;   // 125 x 2 bytes

    20: // Chunk 2: registers 125-249
        _nReadQuantity := 125;
        _nReadMBAddr   := nBaseAddr + 125;
        _pReadDestAddr := ADR(_arrMBData[126]);
        _cbReadLength  := 250;

    30: // Chunk 3: registers 250-374
        _nReadQuantity := 125;
        _nReadMBAddr   := nBaseAddr + 250;
        _pReadDestAddr := ADR(_arrMBData[251]);
        _cbReadLength  := 250;
END_CASE
```

## 5. SunSpec Discovery Pattern

SunSpec devices follow a standardized discovery protocol.

### "SunS" Identifier Scan

```iecst
VAR
    _arrDataSID    : ARRAY[1..2] OF WORD;
    _nMBAddr       : UINT := 40000;
    _nMBAddrOffset : UINT := 0;
END_VAR

_fbMBReadRegs(
    nQuantity := 2,
    nMBAddr   := _nMBAddr + _nMBAddrOffset,
    nUnitID   := _nUnitId,
    cbLength  := SIZEOF(_arrDataSID),
    pDestAddr := ADR(_arrDataSID),
    bExecute  := TRUE);

IF NOT _fbMBReadRegs.bBusy THEN
    IF NOT _fbMBReadRegs.bError
       AND F_SunSpec_Uint32(_arrDataSID[1], _arrDataSID[2]) = 16#53756E53 THEN
        _bSID_Valid := TRUE;
    ELSE
        IF bEnableAutoSearch THEN
            ChangeModbusAddressParameter();  // Try 40000, 50000, 0
        END_IF
    END_IF
END_IF
```

### SunSpec Scale Factor

```iecst
FUNCTION F_SunSpec_Sunssf : LREAL
VAR_INPUT  in : WORD; END_VAR
VAR_OUTPUT bValid : BOOL; END_VAR

IF in = 16#8000 THEN RETURN; END_IF

F_SunSpec_Sunssf := EXPT(10, WORD_TO_INT(in));

IF NOT IsFinite(F_LREAL(F_SunSpec_Sunssf)) THEN
    F_SunSpec_Sunssf := 0;
    RETURN;
END_IF

bValid := TRUE;
```

Usage:
```iecst
stModel.rV_SF := F_SunSpec_Sunssf(_arrMBData[14]);
stData.fVoltage := TO_LREAL(F_SunSpec_Uint16(_arrMBData[5])) * stModel.rV_SF;
```

## 6. Common Tc2_ModbusSrv FBs

| FB | FC | Purpose |
|----|-----|---------|
| `FB_MBReadInputRegs` | FC04 | Read input registers (read-only process data) |
| `FB_MBReadRegs` | FC03 | Read holding registers (config + setpoints) |
| `FB_MBWriteSingleReg` | FC06 | Write single 16-bit register |
| `FB_MBWriteRegs` | FC16 | Write multiple consecutive registers |
| `FB_MBReadCoils` | FC01 | Read coils (boolean bits) |
