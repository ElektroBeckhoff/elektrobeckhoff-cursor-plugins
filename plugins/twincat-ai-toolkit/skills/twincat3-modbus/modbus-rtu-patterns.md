# Modbus RTU Patterns (Tc3_ModbusRtuEB)

> **Shared patterns** (state machine, step-pairs, delay, error handling, execute flags, interval timer, write change detection) are defined in `twincat3-modbus.mdc`. This file contains **only RTU-specific** implementation details.

## 1. BYTE-Based Helper Functions (RTU)

RTU uses `ARRAY[1..N] OF BYTE` buffers (1-based). The array size is variable and must be at least `nQuantity * 2` bytes (2 bytes per register). Example: `ARRAY[1..40] OF BYTE` for max 20 registers. All helper functions take BYTE inputs.

### 4 Bytes to IEEE 754 REAL (Big-Endian with Byte Swap)

The byte swap pattern depends on the device byte order. Check the device datasheet.
Some devices use straight Big-Endian (no swap needed), others swap bytes within words.

```iecst
FUNCTION F_[Device]_Real : REAL
VAR_INPUT
    Byte1 : BYTE;
    Byte2 : BYTE;
    Byte3 : BYTE;
    Byte4 : BYTE;
END_VAR
VAR
    _Byte1 : BYTE;
    _Byte2 : BYTE;
    _Byte3 : BYTE;
    _Byte4 : BYTE;
    dwData : DWORD;
    PTREAL : POINTER TO REAL;
END_VAR

// Swap bytes within each word (device-specific byte order)
_Byte1 := Byte2;
_Byte2 := Byte1;
_Byte3 := Byte4;
_Byte4 := Byte3;

dwData := (SHL(TO_DWORD(_Byte1), 24))
       OR (SHL(TO_DWORD(_Byte2), 16))
       OR (SHL(TO_DWORD(_Byte3), 8))
       OR TO_DWORD(_Byte4);

PTREAL          := ADR(dwData);
F_[Device]_Real := PTREAL^;
```

### 4 Bytes to DINT

```iecst
FUNCTION F_[Device]_DINT : DINT
VAR_INPUT
    Byte1 : BYTE;
    Byte2 : BYTE;
    Byte3 : BYTE;
    Byte4 : BYTE;
END_VAR
VAR
    wPart1 : WORD;
    wPart2 : WORD;
END_VAR

wPart1 := TO_WORD(Byte1) + SHL(TO_WORD(Byte2), 8);
wPart2 := TO_WORD(Byte3) + SHL(TO_WORD(Byte4), 8);

F_[Device]_DINT := SHL(TO_DINT(wPart1), 16) + TO_DINT(wPart2);
```

### 4 Bytes to UDINT

```iecst
FUNCTION F_[Device]_UDINT : UDINT
VAR_INPUT
    Byte1 : BYTE;
    Byte2 : BYTE;
    Byte3 : BYTE;
    Byte4 : BYTE;
END_VAR
VAR
    wPart1 : WORD;
    wPart2 : WORD;
END_VAR

wPart1 := TO_WORD(Byte1) + SHL(TO_WORD(Byte2), 8);
wPart2 := TO_WORD(Byte3) + SHL(TO_WORD(Byte4), 8);

F_[Device]_UDINT := SHL(TO_UDINT(wPart1), 16) + TO_UDINT(wPart2);
```

### Status Bitfield Decoding

```iecst
FUNCTION F_[Device]_Status : ST_[Device]_Status
VAR_INPUT
    wStatus : DWORD;
END_VAR
VAR
    result : ST_[Device]_Status;
END_VAR

result.bBit0_Description := (wStatus AND 16#0001) <> 0;
result.bBit1_Description := (wStatus AND 16#0002) <> 0;
result.bBit2_Description := (wStatus AND 16#0004) <> 0;

F_[Device]_Status := result;
```

### Byte-Swapped Bytes to STRING(20)

Modbus registers transmit strings with swapped byte order within each 16-bit word:

```iecst
FUNCTION F_[Device]_String_20 : STRING(20)
VAR_IN_OUT
    arrBytes : ARRAY[1..40] OF BYTE;
END_VAR
VAR
    i : INT;
END_VAR

FOR i := 1 TO 20 - 1 BY 2 DO
    IF arrBytes[i + 1] <> 0 THEN
        F_[Device]_String_20 := CONCAT(F_[Device]_String_20, CHR(arrBytes[i + 1]));
    END_IF

    IF arrBytes[i] <> 0 THEN
        F_[Device]_String_20 := CONCAT(F_[Device]_String_20, CHR(arrBytes[i]));
    END_IF
END_FOR
```

### Power Consumption/Delivery Split

```iecst
FUNCTION F_[Device]_Power_Consumption_Delivery : BOOL
VAR_INPUT
    fin : REAL;
END_VAR
VAR_OUTPUT
    fConsumed  : REAL;
    fDelivered : REAL;
END_VAR

IF fin = 0 THEN
    fConsumed  := 0;
    fDelivered := 0;
ELSIF fin > 0 THEN
    fConsumed  := fin;
    fDelivered := 0;
ELSE
    fConsumed  := 0;
    fDelivered := -fin;
END_IF
```

## 2. FIFO Buffer Configuration

### Buffer Parameters (Param_Modbus GVL)

```iecst
{attribute 'qualified_only'}
VAR_GLOBAL CONSTANT
    nSizeComBuffer           : INT  := 50;     // FIFO queue depth
    tSendDelayDifferentUnits : TIME := T#10MS;  // Delay between telegrams to different slaves
    tSendDelaySameUnit       : TIME := T#10MS;  // Delay between telegrams to same slave
END_VAR
```

### FIFO Setup Variants

**KL6x22B:**
```iecst
VAR
    fbModbusRtuMaster      : ModbusRtuMasterV2_KL6x22B;
    fbModbusRtuCom_KL6x22B : FB_ModbusRtuCom_KL6x22B(FB_ModbusRtuMaster := fbModbusRtuMaster);
    stModbusComBuffer      : ST_ModbusComBuffer;
END_VAR
```

**PcCOM:**
```iecst
VAR
    fbModbusRtuMaster    : ModbusRtuMasterV2_PcCOM;
    fbModbusRtuCom_PcCOM : FB_ModbusRtuCom_PcCOM(FB_ModbusRtuMaster := fbModbusRtuMaster);
    stModbusComBuffer    : ST_ModbusComBuffer;
END_VAR
```

## 3. Multi-Block Read Strategy

The buffer array size limits how many registers can be read in one block (e.g. `ARRAY[1..40]` = max 20 registers). Size the buffer to fit the largest single read block, then split larger register maps into multiple step pairs:

```
Step 1/2:   Read Regs 0-1        (Identification, 2 regs, 4 bytes)
Step 3/4:   Read InputRegs 0-19  (Block 1, 20 regs, 40 bytes)
Step 5/6:   Read InputRegs 20-39 (Block 2, 20 regs, 40 bytes)
Step 7/8:   Read InputRegs 40-59 (Block 3, 20 regs, 40 bytes)
...
Step N:     _nReadStep := 90     (jump to success)
```

Each block reads into the same `_arrReadMBDataByte` buffer, which is parsed in
the even step before the next read overwrites it.

## 4. FB_ModbusRtu Internal Mechanics

### Request Enqueue (FB_ModbusRtu)

1. Rising edge on `bExecute` fills `stModbusData` with request parameters
2. `nMessageID := ADR(THIS^)` set in `FB_init` — unique per instance
3. Scans buffer for first `Idle` slot, copies request there
4. If no idle slot found, `bNewData` stays TRUE — detected as buffer overflow on next cycle

### FIFO Processing (FB_ModbusRtuCom_*)

1. Checks `arrModbusData[1]` (head of queue)
2. If `Done`: shift entire buffer left via `MEMMOVE`, start inter-telegram delay
3. If valid mode and not busy and delay elapsed: start Modbus operation
4. Dispatches to correct `ModbusRtuMasterV2_*` method based on `eModbusMode`
5. When `NOT BUSY`: writes error/answer info to `arrModbusData[1]`, sets mode to `Answer`

### Answer Collection (FB_ModbusRtu)

1. Checks if `arrModbusData[1].nMessageID` matches own `nMessageID`
2. If mode is `Answer`: copies result data, sets mode to `Done`, clears `bBusy`
3. `Done` mode triggers FIFO shift in the next Com FB cycle
