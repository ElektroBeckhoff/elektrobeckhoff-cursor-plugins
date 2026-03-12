# TwinCAT3 Comment Rules — Complete Reference

---

## 1. FB / FUNCTION Header

One-line `//` purpose comment before `FUNCTION_BLOCK` / `FUNCTION`.  
Max 3 lines for complex FBs.

```iecst
// Modbus TCP client for Solplanet AI-Logger 1000.
// Reads inverter measurements via FC04, writes control registers via FC06.
FUNCTION_BLOCK FB_Solplanet_Ai_Logger_1000
```

```iecst
// Converts two WORD registers to DINT (big-endian, high word first).
FUNCTION F_Solplanet_Int32 : DINT
```

Rules:
- English only
- Describes **what** the FB does, not **how**
- No period at end
- No redundant `// FB for ...`

---

## 2. VAR_INPUT / VAR_OUTPUT — Always Commented

Every input and output **must** have an inline `//` comment.

```iecst
VAR_INPUT
    sIPAddr       : STRING(15) := '192.168.0.1'; // Inverter IP address
    nUnitID       : BYTE := 1;                   // Modbus unit ID
    nTCPPort      : UINT := 502;                 // [port] Modbus TCP port
    tTimeout      : TIME := T#5S;               // Modbus response timeout
    tReadInterval : TIME := T#5S;               // Polling interval
END_VAR

VAR_OUTPUT
    bBusy         : BOOL;  // TRUE while read/write cycle running
    bError        : BOOL;  // TRUE on Modbus fault
    nErrorId      : UDINT; // Last Modbus error code
END_VAR
```

### Unit bracket convention

Units always in brackets at the start of comment:

| Unit | Example |
|------|---------|
| Ampere | `// [A] Max phase current` |
| Volt | `// [V] Grid voltage` |
| Watt | `// [W] Active power setpoint` |
| Kilowatt-hour | `// [kWh] Total energy` |
| Percent | `// [%] State of charge` |
| Celsius | `// [°C] Temperature limit` |
| Milliseconds | `// [ms] Scan interval` |
| Seconds | `// [s] Timeout duration` |
| Port | `// [port] TCP port number` |

### BOOL comment style

Describe the TRUE condition:

```iecst
bEnabled   : BOOL; // TRUE when FB is active
bOverlimit : BOOL; // TRUE when current exceeds limit
bBusy      : BOOL; // TRUE while operation in progress
```

---

## 3. VAR Section Headers

Group private variables with `(* section name *)` headers.  
Use when a VAR block has ≥5 variables **or** has clearly distinct subgroups.

```iecst
VAR
    (* edge triggers *)
    _posEdgeEnable : R_TRIG;
    _negEdgeDone   : F_TRIG;

    (* timers *)
    _fbTonRead     : TON;
    _fbTonWrite    : TON;

    (* Modbus read state *)
    _nReadStep     : INT;
    _nReadNextStep : INT;
    _bReadExecute  : BOOL;
    _arrReadBuf    : ARRAY [0..15] OF WORD;

    (* Modbus write state *)
    _nWriteStep    : INT;
    _bWriteExecute : BOOL;
    _nWriteValue   : WORD;

    (* FB instances *)
    _fbMBRead      : FB_MBReadInputRegs;
    _fbMBWrite     : FB_MBWriteSingleReg;
END_VAR
```

One blank line between sections. Headers are lowercase, 2-4 words.

---

## 4. Code Block Separators

Use `(* --- Purpose --- *)` to separate logical sections in implementation:

```iecst
(* --- edge detection --- *)
_posEdgeEnable(CLK := bEnable);

(* --- parameter validation --- *)
IF tTimeout < T#100MS
THEN
    bError := TRUE;
    RETURN;
END_IF

(* --- read cycle --- *)
CASE _nReadStep OF
    (* ... *)
END_CASE

(* --- write cycle --- *)
CASE _nWriteStep OF
    (* ... *)
END_CASE
```

Rules:
- At least 3 dashes on each side: `(* --- text --- *)`
- Lowercase text, 2-5 words
- **1 blank line before** separator, **no blank line after** it
- Only for groups of ≥3 related lines
- Never for single statements

---

## 5. STRUCT / DUT Members

Same rules as VAR_INPUT — each member should have an inline comment:

```iecst
TYPE ST_Solplanet_InverterBasic :
STRUCT
    (* power *)
    fActivePower    : REAL; // [W] Total active power (Reg 36100)
    fReactivePower  : REAL; // [var] Total reactive power (Reg 36102)
    fApparentPower  : REAL; // [VA] Total apparent power (Reg 36104)

    (* temperatures *)
    fTempInternal   : REAL; // [°C] Internal temperature (Reg 1310)
    fTempPhaseU     : REAL; // [°C] U phase temperature (Reg 1311)
    fTempPhaseV     : REAL; // [°C] V phase temperature (Reg 1312)
    fTempPhaseW     : REAL; // [°C] W phase temperature (Reg 1313)
    fTempBoost      : REAL; // [°C] Boost temperature (Reg 1314)
    fTempDCDC       : REAL; // [°C] Bidirectional DC/DC converter temp (Reg 1315)
END_STRUCT
END_TYPE
```

STRUCT can also use `(* section name *)` headers to group members.

---

## 6. Action / Method Headers (Large FBs Only)

For complex actions/methods in FBs with 5+ actions, use a 3-line block header:

```iecst
(* ------------------------------------------- *)
(*           Modbus Read Cycle                 *)
(* ------------------------------------------- *)
```

Only for FBs with 5+ actions/methods. Small FBs: plain `(* --- name --- *)` is enough.

---

## 7. Inline Modbus Register Comments

When assigning from Modbus buffer arrays, always include register address:

```iecst
// ✅ Clear — reader knows exactly which register maps to what
stWeather.fIrradiance       := WORD_TO_REAL(_arrReadBuf[0]) * 0.1;   // Reg 1000, Gain 0.1
stWeather.fModuleTemp       := F_Solplanet_Int16(_arrReadBuf[1]) * 0.1; // Reg 1001, S16 Gain 0.1
stWeather.fAmbientTemp      := F_Solplanet_Int16(_arrReadBuf[2]) * 0.1; // Reg 1002, S16 Gain 0.1
stWeather.fWindSpeed        := WORD_TO_REAL(_arrReadBuf[3]) * 0.1;   // Reg 1003, Gain 0.1
```

Include:
- Modbus register address
- Data type if non-obvious (S16, S32, U32)
- Gain/multiplier if applied

---

## 8. What NOT to Comment

```iecst
// ❌ Narrates what the code already says
bDone := TRUE;   // Set bDone to TRUE

// ❌ Duplicates variable name
bEnable : BOOL;  // Enable flag for bEnable

// ❌ Commenting END_IF / END_CASE / END_FOR
END_IF   // end if
END_CASE // end case

// ❌ TODO without owner and date
// TODO: add timeout

// ✅ Correct TODO
// TODO(ChristianAu 2026-01-14): add watchdog timeout for Modbus disconnect
```

- Internal VAR members: comments **optional**, only if purpose is non-obvious
- Don't comment trivial assignments in the body — only at declaration
- Don't state the obvious with `(* --- end of ... --- *)` after END_IF blocks

---

## 9. GVL / Constants Comments

Every constant in a GVL or `VAR CONSTANT` block should have a comment:

```iecst
VAR CONSTANT
    READ_DELAY               : TIME := T#200MS; // Inter-register group delay
    WRITE_DELAY              : TIME := T#100MS; // Post-write stabilization delay

    REG_TOTAL_ACTIVE_POWER   : WORD := 36100;   // S32, Gain 1, [W]
    REG_TOTAL_REACTIVE_POWER : WORD := 36102;   // S32, Gain 1, [var]
    REG_WEATHER_IRRADIANCE   : WORD := 1000;    // U16, Gain 0.1, [W/m²]
END_VAR
```

Format for register constants: `// DataType, Gain, [Unit]`
