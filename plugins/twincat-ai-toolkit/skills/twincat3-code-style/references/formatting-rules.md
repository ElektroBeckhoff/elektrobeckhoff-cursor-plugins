# TwinCAT3 Formatting Rules — Complete Reference

Source: project auto-formatter configuration + CLAUDE.md spec.

---

## 1. Indentation

- **4 spaces** per level. Never tabs.
- Continuation lines: **+4 spaces** from statement start (not from operator).

```iecst
nLongExpression := (nValue1 + nValue2)
                    * fGain;
```

---

## 2. Control Flow Keyword Placement

### IF / ELSIF / ELSE

`THEN` always stays on the **same line** as `IF`/`ELSIF`. `DO` stays on the same line as `FOR`/`WHILE`.

```iecst
IF bConditionA THEN
    DoA();
ELSIF bConditionB THEN
    DoB();
ELSE
    DoDefault();
END_IF
```

`ELSIF` and `ELSE` at column 0 (not indented).

**The body always goes on the next line — never write IF and its statement on one line:**

```iecst
// ✅ Correct
IF bError THEN
    RETURN;
END_IF

// ❌ Never
IF bError THEN RETURN; END_IF
```

### FOR

```iecst
FOR nIdx := 0 TO nCount - 1 DO
    arrData[nIdx] := 0;
END_FOR
```

### WHILE

```iecst
WHILE bRunning DO
    Process();
END_WHILE
```

### REPEAT

```iecst
REPEAT
    nIdx := nIdx + 1;
UNTIL nIdx >= nMax
END_REPEAT
```

---

## 3. CASE Statement

```iecst
CASE nState OF
    0:
        nValue := 0;
        bDone  := FALSE;

    1:
        nValue := 1;
        bDone  := TRUE;

    2:
        A_HandleError();

ELSE
    nValue := -1;
END_CASE
```

Rules:
- Case labels indented 4 spaces
- Body indented 8 spaces (or 4 if body is on same line as label for single-statement)
- Multi-statement body: label on its own line, body indented below
- `ELSE` at column 0
- Blank line between cases when bodies span multiple lines

Single-statement shorthand (only when trivially simple):
```iecst
CASE nMode OF
    0: nOut := 0;
    1: nOut := 100;
    2: nOut := 200;
ELSE
    nOut := -1;
END_CASE
```

---

## 4. Declarations — Column Alignment

Align `:`, `:=`, and `//` in columns **within each VAR block**:

```iecst
VAR_INPUT
    bEnable       : BOOL;                     // Enable the FB
    fSetpoint     : REAL := 0.0;              // [W] Power setpoint
    tTimeout      : TIME := T#5S;             // Modbus timeout
    stParam       : ST_EMS_PidParam;          // PID parameters
END_VAR

VAR_OUTPUT
    fOutput       : REAL;                     // [A] Controller output
    bBusy         : BOOL;                     // TRUE while executing
    bError        : BOOL;                     // TRUE on fault
    nErrorId      : UDINT;                    // Error code
END_VAR

VAR
    (* state machine *)
    _nStep        : INT;                      // Current step
    _nNextStep    : INT;                      // Next step after delay

    (* timers *)
    _fbTon        : TON;                      // Delay timer

    (* Modbus *)
    _fbMBRead     : ModbusRtuMaster_KL6x22B;  // Read FB instance
END_VAR
```

Rules:
- Column alignment resets per block — don't align across VAR/VAR_INPUT/VAR_OUTPUT
- `:=` initial values aligned in same column as `:` of type
- `//` comments aligned together (not necessarily to a fixed column)

---

## 5. VAR Block Order

```
1. VAR_INPUT
2. VAR_OUTPUT
3. VAR_IN_OUT
4. VAR        (private, grouped with (* section *) headers)
5. VAR CONSTANT
```

---

## 6. VAR Internal Grouping

Use `(* section name *)` headers for groups of ≥5 related vars.  
One blank line between groups.

```iecst
VAR
    (* edge triggers *)
    _posEdgeEnable : R_TRIG;
    _negEdgeDone   : F_TRIG;

    (* timers *)
    _fbTonStart    : TON;
    _fbTonTimeout  : TON;

    (* Modbus read state *)
    _nReadStep     : INT;
    _nReadNextStep : INT;
    _bReadExecute  : BOOL;
    _arrReadBuf    : ARRAY [0..15] OF WORD;

    (* Modbus write state *)
    _nWriteStep    : INT;
    _bWriteExecute : BOOL;
    _nWriteValue   : WORD;
END_VAR
```

---

## 7. Function / FB Calls

**≤4 params → single line:**
```iecst
fbTimer(IN := bStart, PT := T#5S, Q => bDone);
fbRead(sIP := sIPAddr, nPort := 502, nUnit := 1, bExec := TRUE);
```

**>4 params → multiline:**  
Break after `(`, align `:=` and `=>`, closing `);` on last param line — no extra line for `)`:

```iecst
_fbMBRead(
    sIPAddr      := sIPAddr,
    nTCPPort     := nTCPPort,
    nUnitID      := nUnitID,
    nMBAddr      := _nReadAddr,
    nQuantity    := _nReadCount,
    pDestAddr    := _pReadDest,
    cbLength     := _cbReadLen,
    bExecute     := _bReadExecute,
    tTimeout     := tTimeout,
    bBusy        => bReadBusy,
    bError       => _bReadError,
    nErrId       => _nReadErrId);
```

No trailing comma. `);` stays on last param line.

---

## 8. Assignment Alignment

Align `:=` in related groups:

```iecst
// ✅ Aligned group
_bReadExecute  := TRUE;
_nReadAddr     := REG_TOTAL_POWER;
_nReadCount    := 2;
_pReadDest     := ADR(_arrReadBuf);
_cbReadLen     := SIZEOF(_arrReadBuf);

// ❌ Unrelated assignments — don't force align
nIdx := 0;
nLongVariableName := 42;
```

---

## 9. Array Initializers

**≤30 elements → single line:**
```iecst
arrZero : ARRAY [0..4] OF INT := [0, 0, 0, 0, 0];
```

**>30 elements → multiline:**
```iecst
arrLookup : ARRAY [0..35] OF REAL :=
[
    0.0, 0.5, 1.0, 1.5, 2.0, 2.5,
    3.0, 3.5, 4.0, 4.5, 5.0, 5.5,
    (* ... *)
];
```

---

## 10. Enum / TYPE Inline Rule

**≤5 members → one line:**
```iecst
TYPE E_Mode : ( IDLE := 0, RUN := 1, FAULT := 99 ) := IDLE; END_TYPE
```

**>5 members → multiline:**
```iecst
TYPE E_State :
(
    IDLE       := 0,
    STARTING   := 10,
    RUNNING    := 20,
    STOPPING   := 30,
    FAULT      := 90,
    INIT_ERROR := 99
) := IDLE;
END_TYPE
```

---

## 11. Long Line Wrapping

- Hard limit: **200 characters**
- Wrap **after** binary operators, not before:

```iecst
// ✅ After operator
fResult := (fCurrent * fVoltage * fPowerFactor) +
           fOffsetCorrection;

// ❌ Before operator
fResult := (fCurrent * fVoltage * fPowerFactor)
           + fOffsetCorrection;
```

---

## 12. Blank Lines

| Context | Rule |
|---|---|
| Before / after IF, CASE, FOR, WHILE | 1 blank line |
| Between END_VAR and first code line | 0 blank lines |
| Between logical groups in implementation | 1 blank line |
| Maximum consecutive blank lines | 1 |
| Between CASE blocks (multi-statement) | 1 blank line |

---

## 13. Spaces

| Context | Rule |
|---|---|
| Around `:=`, `+`, `-`, `*`, `/`, `=`, `<>` | Space on both sides |
| `AND`, `OR`, `NOT`, `MOD`, `XOR` | Space on both sides |
| After commas | 1 space |
| Around `:` in declarations | Space on both sides |
| Before `.` (member access) | No space |
| Before `[` (array index) | No space |
| Inside `(` / `)` | No space after `(`, no space before `)` |
| Before `(` in function call | No space |

---

## 14. STRUCT / TYPE Formatting

STRUCT always on its own line after `:`, not indented:

```iecst
TYPE ST_EMS_Example :
STRUCT
    fCurrent      : REAL := 0.0;   // [A] Phase current
    bEnable       : BOOL;          // Enable flag
    nMode         : INT;           // Operating mode
END_STRUCT
END_TYPE
```

- `TYPE ST_Name :` — colon on same line
- `STRUCT` at column 0 (not indented, not on same line as `:`)
- Members indented 4 spaces
- `END_STRUCT` and `END_TYPE` at column 0
- Column-align `:`, `:=`, and `//` within the struct
