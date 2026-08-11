# TwinCAT3 Pagefault Checklist (InfoSys-only)

Every finding MUST cite a **Check-ID** below. Do not invent IDs.
**Only checks with direct TwinCAT InfoSys (MSHC) evidence are listed.**  
Evidence paths: `infosys-evidence.md`.

Legend:
- **ERROR** — InfoSys documents access violation / runtime stop / system crash / null-pointer problem for this pattern

Safe guard patterns (InfoSys):
1. Nested `IF` after validity check
2. `AND_THEN` / `OR_ELSE` (short-circuit) — **not** IEC `AND` / `OR`
3. IEC `AND`: TwinCAT **always evaluates all operands**

**Applies to every BOOL expression**, not only `IF`:
`IF` / `ELSIF` / `WHILE <expr> DO` / `REPEAT … UNTIL <expr>` / assignment of a BOOL expression.
(WHILE InfoSys: termination condition is a Boolean expression — same `AND` rules as `IF`.)

### Loop examples (same Check-IDs)

```iecst
(* BAD — AND always evaluates arr[nIndex] even when nIndex >= cMax *)
WHILE nIndex < cMax AND arr[nIndex] <> 0 DO
    nIndex := nIndex + 1;
END_WHILE

(* OK *)
WHILE nIndex < cMax AND_THEN arr[nIndex] <> 0 DO
    nIndex := nIndex + 1;
END_WHILE

(* BAD — pointer walk *)
WHILE pNode <> 0 AND pNode^.pNext <> 0 DO
    pNode := pNode^.pNext;
END_WHILE

(* OK *)
WHILE pNode <> 0 AND_THEN pNode^.pNext <> 0 DO
    pNode := pNode^.pNext;
END_WHILE
```

→ Flag with **PF-SC-*** + **PF-ARR-01** / **PF-PTR-*** as applicable.

---

## PF-SC — `AND` / `OR` vs `AND_THEN` / `OR_ELSE`

| ID | What to flag | InfoSys fact | Safe pattern | Sev |
|----|--------------|--------------|--------------|-----|
| **PF-SC-01** | `ptr <> 0 AND ptr^…` / `ptr <> 0 AND ptr^.…` (incl. in `WHILE`/`REPEAT`) | `AND` always evaluates all operands → RHS null deref | Nested `IF` or `ptr <> 0 AND_THEN …` | ERROR |
| **PF-SC-02** | `__ISVALIDREF(ref) AND ref.…` | Same `AND` rule + invalid ref use | Nested `IF` or `AND_THEN` | ERROR |
| **PF-SC-03** | `i <> 0 AND i.Method()` / property on RHS of `AND` | Same `AND` rule + interface must be checked | Nested `IF` or `AND_THEN` | ERROR |
| **PF-SC-04** | `OR` with a call/deref on another operand that must not run | `OR` still executes further operands (unlike `OR_ELSE`) | Nested `IF` / `OR_ELSE` | ERROR |
| **PF-SC-05** | Same as PF-SC-01 with compacted forms (`NOT (ptr = 0) AND ptr^…`) | Same `AND` rule | Nested `IF` / `AND_THEN` | ERROR |
| **PF-SC-06** | Multi-pointer / index: `n < cMax AND arr[n]…` or `p1 <> 0 AND p2 <> 0 AND p1^.x …` | Every operand of `AND` is evaluated (index/deref always runs) | Nested `IF` or `AND_THEN` chain | ERROR |
| **PF-SC-07** | `AND_THEN`/`OR_ELSE` but deref/index/call is on the **left** of the check | Short-circuit only skips **further** operands after fail/pass | Check **left**, use **right** | ERROR |

---

## PF-PTR — `POINTER TO`

| ID | What to flag | InfoSys fact | Safe pattern | Sev |
|----|--------------|--------------|--------------|-----|
| **PF-PTR-01** | `p^` / `p^.member` / `p^[i]` / `p[i]` without dominating `p <> 0` on that path | SA0039: check before **each** deref or **access violations**; CheckPointer: invalid pointer usually **stops runtime** | `IF p <> 0 THEN … END_IF` | ERROR |
| **PF-PTR-02** | `POINTER TO FB` call `pFb^(…)` / `pFb^.M_…` without `pFb <> 0` | Same as PF-PTR-01; __NEW samples use `IF (pFB <> 0) THEN` before call | Check then call | ERROR |
| **PF-PTR-03** | `p[i]` / pointer index with variable `i` not proven inside allocated/element range | POINTER: `p[i]` = address arithmetic + **implicit deref** | Bound `i` to valid element range | ERROR |

---

## PF-REF — `REFERENCE TO`

| ID | What to flag | InfoSys fact | Safe pattern | Sev |
|----|--------------|--------------|--------------|-----|
| **PF-REF-01** | Use of `REFERENCE TO` without `__ISVALIDREF(ref)` before read/write | SA0145 / REFERENCE: check with `__ISVALIDREF`; ref can be 0 | `IF __ISVALIDREF(ref) THEN … END_IF` | ERROR |
| **PF-REF-02** | `__ISVALIDREF` used on **INTERFACE** or **POINTER** | __ISVALIDREF: **only** `REFERENCE TO`; interfaces → `<> 0` | Correct API per type | ERROR |

**Not in scope:** `VAR_IN_OUT` — InfoSys: must be assigned at call → treated as always valid (prefer over optional `REFERENCE TO`).

---

## PF-IFACE — Interface variables

| ID | What to flag | InfoSys fact | Safe pattern | Sev |
|----|--------------|--------------|--------------|-----|
| **PF-IFACE-01** | Method/property on interface without `i <> 0` | Interface page: check `<> 0` before use; SA0046 uninitialized interface | `IF i <> 0 THEN i.M(); END_IF` | ERROR |

---

## PF-NEW — `__NEW` / `__DELETE`

| ID | What to flag | InfoSys fact | Safe pattern | Sev |
|----|--------------|--------------|--------------|-----|
| **PF-NEW-01** | Use of `__NEW` result without `p <> 0` | __NEW returns **0** if allocation fails | Check immediately before any `p^` | ERROR |
| **PF-NEW-02** | Use of `p` / `p^` / **any alias** after `__DELETE(p)` | __DELETE releases memory and sets **the operand** to 0 — other variables still holding the address are not cleared | Never use after delete; do not keep aliases | ERROR |

**Not in scope as pagefault IDs:** memory leak without `__DELETE` (InfoSys: leak / unstable system — not documented as pagefault). Track leaks outside this audit if needed.

---

## PF-MEM — `MEMCPY` / `MEMMOVE` / `MEMSET`

| ID | What to flag | InfoSys fact | Safe pattern | Sev |
|----|--------------|--------------|--------------|-----|
| **PF-MEM-01** | `n` (byte count) larger than the real destination (and/or source) memory area | Tc2_System Notice: incorrect parameter values → **system crash** or access to forbidden memory | `n <=` actual buffer/alloc size | ERROR |

**Not in scope:**
- `destAddr==0` / `srcAddr==0` alone — return **0** (not documented as crash)
- MEMCPY overlap — documented as **undefined**, not as pagefault/crash (use MEMMOVE as coding practice, not a PF-* finding here)

---

## PF-ARR — Arrays

| ID | What to flag | InfoSys fact | Safe pattern | Sev |
|----|--------------|--------------|--------------|-----|
| **PF-ARR-01** | Variable array index that can leave the declared range, without an explicit bounds check (and without relying on a project `CheckBounds` POU) — incl. inside `WHILE`/`FOR`/`REPEAT` body or condition | CheckBounds / `RTSEXCPT_ARRAYBOUNDS`: field-bound violations are a defined runtime fault class | Compare index to **declared** bounds before access; in loop conditions use `AND_THEN` (see PF-SC-06) | ERROR |

**Not in scope:** `LOWER_BOUND`/`UPPER_BOUND` on fixed arrays (C0380: variable-length only). Constant out-of-range index (compiler error, not a runtime pagefault audit item).

---

## EX-DIV — Division by zero (not a pagefault; separate exception)

InfoSys: division by zero is **`RTSEXCPT_DIVIDEBYZERO` / task stop**, not a pagefault.  
Kept here because it is **100% documented** and often paired with the same `AND` mistake.

| ID | What to flag | InfoSys fact | Safe pattern | Sev |
|----|--------------|--------------|--------------|-----|
| **EX-DIV-01** | `/` or `DIV` with a variable divisor that is not proven `<> 0` on that path | **DIV**: “division by zero always leads to an exception and the corresponding **task is stopped**.” **SA0040**: check divisor for 0 first | `IF nDiv <> 0 THEN nQ := nA / nDiv; END_IF` | ERROR |
| **EX-DIV-02** | Guard divisor with IEC `AND` then divide on the RHS: `nDiv <> 0 AND (nA / nDiv) …` (also in `WHILE`) | `AND` always evaluates all operands → division still runs when `nDiv = 0` | Nested `IF` or `nDiv <> 0 AND_THEN (nA / nDiv) …` | ERROR |

Optional runtime helpers (InfoSys DIV page): `CheckDivInt` / `CheckDivDInt` / `CheckDivReal` / `CheckDivLReal` — do not replace an explicit `<> 0` check in application code unless the project standard requires them.

---

## Explicitly OUT OF SCOPE (do **not** report)

- CONCAT / string capacity / truncation (no pagefault wording in MSHC)
- `ANY` size guessing, JSON/MQTT/Modbus toolkit patterns without a concrete PF-* ID above
- Cross-cycle / Online-Change lifetime speculation (use PF-PTR-01 / PF-REF-01 / PF-IFACE-01: check **before each use**)
- Jump tables, `SUPER^` init order, comment-only “assumed valid”
- Style, naming, missing `bError`, performance
- FBD/CFC graphics
- Memory leaks alone (no `__DELETE`) — not a pagefault Check-ID here

---

## Required evidence per finding

1. Check-ID  
2. File + line (XML as opened)  
3. Short code excerpt  
4. One-sentence risk tied to the InfoSys fact for that ID  
5. Concrete fix (nested `IF` / `AND_THEN` / `<> 0` / `__ISVALIDREF` / bound `n` or index)
