# InfoSys MSHC evidence (kept Check-IDs only)

Local TwinCAT 3 Help via `twincat_infosys_mshc_*`. Paths use `1033` = EN.
This file lists **only** evidence for IDs that remain in `checklist.md`.

---

## PF-SC — AND / OR evaluation

| ID | Evidence |
|----|----------|
| PF-SC-01…07 | **AND_THEN** `tc3_plc_intro/1033/2528923787.html`: `IF (ptr <> 0 AND_THEN ptr^ = 99)` avoids null-pointer problems. Quote: **“TwinCAT always evaluates all operands if the IEC operator AND is used.”** |
| PF-SC-04 | **OR_ELSE** `tc3_plc_intro/1033/2528929163.html`: with `OR`, further operands are still executed; with `OR_ELSE`, not after TRUE. |

---

## PF-PTR

| ID | Evidence |
|----|----------|
| PF-PTR-01 / 02 | **SA0039** `te1200_tc3_plcstaticanalysis/1033/20911344523.html`: check pointer `<> 0` before each dereference; else **access violations**. |
| PF-PTR-01 | **CheckPointer** `tc3_plc_intro/1033/2530405259.html`: invalid pointer access usually **stops the runtime**. |
| PF-PTR-02 | **__NEW** samples `tc3_plc_intro/1033/2529171083.html`: `IF (pFB <> 0) THEN` before `pFB^.…`. |
| PF-PTR-03 | **POINTER** `tc3_plc_intro/1033/2529453451.html`: `pData[i]` = arithmetic + **implicit dereference**. |
| (context) | **ExceptionCode** `tc3_plc_intro/1033/6753940235_37882063.html`: `RTSEXCPT_ACCESS_VIOLATION`, `RTSEXCPT_IN_PAGE_ERROR`, … |

---

## PF-REF

| ID | Evidence |
|----|----------|
| PF-REF-01 | **REFERENCE** `tc3_plc_intro/1033/2529458827.html` + **__ISVALIDREF** `tc3_plc_intro/1033/2529165707.html` + **SA0145** (via SA0039 overview). |
| PF-REF-02 | **__ISVALIDREF** page: only `REFERENCE TO`; interfaces → `IF iSample <> 0 THEN`. |
| (excluded) | Same REFERENCE page: prefer `VAR_IN_OUT` — always assigned → always valid. |

---

## PF-IFACE

| ID | Evidence |
|----|----------|
| PF-IFACE-01 | **Interface pointer** `tc3_plc_intro/1033/5680748299.html`: check `<> 0` before use. **SA0046** (via SA0039 overview). |

---

## PF-NEW

| ID | Evidence |
|----|----------|
| PF-NEW-01 | **__NEW** `tc3_plc_intro/1033/2529171083.html`: failure → return **0**. |
| PF-NEW-02 | **__DELETE** `tc3_plc_intro/1033/2529160331.html`: releases memory; **operand set to 0**. |

---

## PF-MEM

| ID | Evidence |
|----|----------|
| PF-MEM-01 | **MEMCPY** `tcplclib_tc2_system/1033/31041163.html`, **MEMMOVE** `…/31044235.html`, **MEMSET** `…/31042699.html`: Notice — incorrect parameters → **system crash** / forbidden memory. |

---

## PF-ARR

| ID | Evidence |
|----|----------|
| PF-ARR-01 | **CheckBounds** `tc3_plc_intro/1033/2530356875.html`; **ExceptionCode** `RTSEXCPT_ARRAYBOUNDS`. |
| (excluded) | C0380: `LOWER_BOUND`/`UPPER_BOUND` only for variable-length arrays. |

---

## WHILE / loop conditions (same AND rules)

| Topic | Evidence |
|-------|----------|
| WHILE condition is a BOOL expression | **ST instruction WHILE** `tc3_plc_intro/1033/2528291723.html` |
| Therefore PF-SC applies inside `WHILE <expr> DO` | Combined with AND_THEN page (always-evaluate `AND`) |

---

## EX-DIV — Division by zero (task stop, not pagefault)

| ID | Evidence |
|----|----------|
| EX-DIV-01 | **DIV** `tc3_plc_intro/1033/2528875403.html`: “In TwinCAT, **division by zero always leads to an exception and the corresponding task is stopped**.” **SA0040** `te1200_tc3_plcstaticanalysis/1033/20911346699.html`. ExceptionCode `RTSEXCPT_DIVIDEBYZERO` / `RTSEXCPT_FPU_DIVIDEBYZERO`. |
| EX-DIV-02 | Same + **AND_THEN** page: `AND` always evaluates all operands (divisor check does not protect `/` on the RHS). |

---

## Explicitly removed (not kept as Check-IDs)

| Removed topic | Why removed |
|---------------|-------------|
| CONCAT / string capacity | No pagefault wording in CONCAT MSHC |
| MEMCPY null dest/src alone | Documented return **0**, not crash |
| MEMCPY overlap | Documented **undefined**, not crash/pagefault |
| `__NEW` leak without `__DELETE` | Leak / unstable system — not pagefault |
| Double-`__DELETE`, size-0 `__NEW`, toolkit JSON/MQTT IDs | No dedicated pagefault evidence in our MSHC pass |
| Cross-cycle / Online-Change / `FB_exit` lifetime IDs | Speculative; covered by “check before each use” (SA0039) |
| `ANY`, jump tables, `SUPER^`, comment-only guards | Unproven |
| `VAR_IN_OUT` as “maybe invalid” | Contradicts InfoSys (always assigned) |
