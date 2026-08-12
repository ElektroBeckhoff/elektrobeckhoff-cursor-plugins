# TwinCAT3 Comment Rules — Examples / Density Reference

Principles (lean): `rules/twincat3-comments.mdc`.
This file is the **examples SoT** (inline pseudocode density target). Match this
density — not denser, not bare. Do not open external library sources for style.

---

## 1. Syntax

Use **only** `(* *)`. Never `//` in ST CDATA.

English only. TwinCAT allows nested `(* outer (* inner *) *)`.

---

## 2. Density target (pseudocode map)

| Pattern | What good looks like |
|---------|----------------------|
| FB header | Multi-line `(* … *)` above `FUNCTION_BLOCK` — purpose / contracts |
| `VAR_INPUT` / `VAR_OUTPUT` | Section headers optional; **every** member has EOL `(* *)` |
| `VAR` | Section headers; selective private EOL (non-obvious only) |
| Body | Prose `(* … *)` before phases — why / order / invariant |
| Methods | Header when contract/OC/order matters; skip trivial helpers |

---

## 3. FB / FUNCTION / PROGRAM Header

```iecst
(* On/off hysteresis for a digital enable line. *)
FUNCTION_BLOCK FB_Lib_HysteresisTimer
```

Complex FBs: 2–3 lines of purpose/contract. Describes **what**, not line-by-line how.

---

## 4. VAR_INPUT / VAR_OUTPUT

```iecst
VAR_INPUT
    sHost     : STRING(15); (* Device host / IP *)
    nPort     : UINT := 502; (* [port] TCP port *)
    tTimeout  : TIME := T#5S; (* Response timeout *)
END_VAR
VAR_OUTPUT
    bBusy     : BOOL; (* TRUE while transaction running *)
    bError    : BOOL; (* TRUE on fault *)
    nErrorId  : UDINT; (* Last error code *)
END_VAR
```

- Units: `(* [A] … *)`, `(* [W] … *)`, `(* [%] … *)`, `(* [ms] … *)`
- BOOL: TRUE condition
- Do not repeat the identifier in the comment

---

## 5. VAR Section Headers + Selective Inline

```iecst
VAR
    (* edge triggers *)
    _posEdgeEnable : R_TRIG;
    _negEdgeDone   : F_TRIG;

    (* timers *)
    _fbTonRead : TON;

    (* state — non-obvious *)
    _nOwnerIdx : INT; (* Active owner; -1 = none *)
END_VAR
```

- Headers when ≥5 vars or clear subgroups
- One blank line between sections
- Extra EOL only for non-obvious members — not every `_fb*`

---

## 6. Implementation Phase Blocks

```iecst
(* Snapshot inputs once per cycle (no mid-cycle tear). *)
_stSnap := stIn;

(* Only apply outputs after settle time. *)
IF _fbTonSettle.Q THEN
    bApply := TRUE;
END_IF
```

Prefer prose over mandatory dash banners. `(* --- purpose --- *)` only if the
file already uses that style. Never for single obvious statements.

---

## 7. CASE Step Comments

```iecst
CASE _nStep OF
    0: (* idle *)
        ;
    1: (* issue request *)
        _bBusy := TRUE;
END_CASE
```

Every case label: inline `(* purpose *)`. Do not repeat the step number.

---

## 8. Method / Action Headers

```iecst
(* Flush pending bind after OC settle; returns TRUE if applied. *)
METHOD _ApplyDeferredBinding : BOOL
```

Trivial helpers: no essay. No required `------` banner boxes.

---

## 9. STRUCT DUT

```iecst
(* Bundled diagnostics; *Valid = TRUE only for a real source. *)
TYPE ST_Lib_Diagnostics :
STRUCT
    (* --- Aggregation --- *)
    nCount     : UINT; (* Number of reporting devices *)
    fLevelMean : REAL; (* [0..100] - Mean; 0 if nCount = 0 *)

    (* --- Quality --- *)
    bValid     : BOOL; (* TRUE after at least one resolved snapshot *)
END_STRUCT
END_TYPE
```

- Purpose above `TYPE`; `(* --- Section --- *)` when large
- Every member EOL-commented (units, TRUE-meaning, empty-count notes)

## 9b. ENUM DUT

```iecst
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_Lib_ControlMode : (
    Binary       := 0, (* 0 % or 100 % based on demand *)
    Proportional := 1, (* PID-based position 0..100 % *)
    Manual       := 2  (* Fixed manual position *)
);
END_TYPE
```

Every enumerator EOL-commented. Do not strip attributes.

## 9c. GVL / constants

GVL / `VAR CONSTANT`: comment each constant; units/register meta in `(* *)`
when useful.

---

## 10. Domain notes (e.g. register maps)

```iecst
stMeas.fPower_W := WORD_TO_REAL(arrBuf[0]) * 0.1; (* Reg 1000, Gain 0.1 *)
```

Still `(* *)`, never `//`.

---

## 11. What NOT to Comment

- Narration: `bDone := TRUE; (* Set bDone to TRUE *)`
- Duplicate name: `bEnable : BOOL; (* Enable flag for bEnable *)`
- `END_IF` / `END_CASE` / `END_FOR`
- TODO without owner/date — use `(* TODO(Name YYYY-MM-DD): … *)`
- Every private VAR
- `//` anywhere in ST CDATA

---

## 12. Checklist (per FB)

- [ ] Header `(* … *)` above `FUNCTION_BLOCK` / `FUNCTION` / `PROGRAM`
- [ ] Every `VAR_INPUT` member has inline `(* *)`
- [ ] Every `VAR_OUTPUT` member has inline `(* *)`
- [ ] `VAR` grouped with section headers when large
- [ ] Extra VAR inline comments only where non-obvious
- [ ] Non-trivial methods have declaration header comments
- [ ] Implementation has block comments on phase boundaries / invariants
- [ ] No `//` in CDATA
- [ ] No obvious narration comments
- [ ] STRUCT: TYPE header + every member; section headers when large
- [ ] ENUM: every enumerator commented; attributes intact
- [ ] Style density matches the pseudocode above (not denser, not bare)

Per-object pass: skill `twincat3-comment` / `/twincat3-cmd-comment`.
