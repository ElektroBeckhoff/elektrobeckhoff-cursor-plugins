---
name: twincat3-pagefault-audit
description: >-
  InfoSys-backed TwinCAT3 ST audit for page-fault / access-violation patterns:
  AND always evaluates all operands, POINTER/REFERENCE/INTERFACE null checks,
  __NEW/__DELETE use-after-free, MEMCPY size, array bounds. Use for
  /twincat3-cmd-pagefault-audit.
---

# TwinCAT3 Pagefault Audit (InfoSys-only)

Defect-first static review for **documented** page-fault / access-violation risks.
Not a style review. **Do not invent findings outside `checklist.md`.**

## Quick Start

```
Task Progress:
- [ ] Step 1: Resolve scope — ask if unclear
- [ ] Step 2: Read checklist.md + infosys-evidence.md
- [ ] Step 3: Read rules/twincat3-pagefault-safety.mdc
- [ ] Step 4: Scan in-scope .TcPOU/.TcDUT/.TcGVL/.TcIO ST (CDATA)
- [ ] Step 5: Report only kept Check-IDs
```

## Step 1: Scope

| User intent | Scope |
|-------------|--------|
| Paths / folder | Those files |
| Whole project | ST objects under `.plcproj` tree |
| Unclear | Ask once |

Skip FBD/CFC (note unaudited).

## Step 2: Kept Check-ID groups (full tables in checklist)

| Prefix | InfoSys-backed focus |
|--------|----------------------|
| **PF-SC-*** | `AND` always evaluates all operands; use nested `IF` / `AND_THEN` |
| **PF-PTR-*** | `p <> 0` before each deref/call; bound `p[i]` |
| **PF-REF-*** | `__ISVALIDREF` for `REFERENCE TO` only |
| **PF-IFACE-*** | Interface `<> 0` before use |
| **PF-NEW-*** | `__NEW` → check `<> 0`; no use after `__DELETE` |
| **PF-MEM-*** | `MEMCPY`/`MEMMOVE`/`MEMSET` byte count `n` > real buffer → crash class |
| **PF-ARR-*** | Variable index outside declared bounds (incl. `WHILE`/`FOR`) |
| **EX-DIV-*** | Division by zero → **task stop** (not pagefault; InfoSys DIV/SA0040) |

**Loops:** `WHILE`/`REPEAT` BOOL conditions use the same `AND` rules as `IF` — e.g. `WHILE n < cMax AND arr[n]…` is PF-SC-06 (+ PF-ARR-01). Prefer `AND_THEN` or nested checks.

Everything else (CONCAT, leaks-only, OC lifetime, JSON toolkit, MEMCPY null return-0, …) is **out of scope** — see checklist.

## Step 3: Scan

1. Search: `POINTER TO`, `REFERENCE TO`, `^`, `__NEW`, `__DELETE`, `MEMCPY`, `MEMMOVE`, `MEMSET`, `__ISVALIDREF`, `AND_THEN`, `OR_ELSE`, interface-typed VARs, ` AND `.
2. For each hit: dominating check on **every** path.
3. Flag PF-SC when validity + deref share one `AND`/`OR`.
4. Trace `__NEW` → use → `__DELETE` (aliases).

## Step 4: Output format

```
Pagefault audit: <scope>

Errors (X)
  [PF-SC-01] path/File.TcPOU:L123
    Code: IF p <> 0 AND p^.bEnable THEN
    Risk: AND always evaluates RHS → null deref (InfoSys AND_THEN)
    Fix: IF p <> 0 THEN … END_IF  — or  p <> 0 AND_THEN p^.bEnable

Coverage
  Files audited: N
  Check-ID groups: PF-SC, PF-PTR, …

Summary
  X errors. Residual: only InfoSys-backed IDs were applied.
```

## Rules of engagement

- Finding without a **kept** Check-ID → discard.
- Do not report UNPROVEN topics listed as out of scope in the checklist.
- Do not edit code unless the user asks after the report.
- Language: same as user query.

## Related

- `checklist.md` / `infosys-evidence.md`
- Rule: `twincat3-pagefault-safety`
- Command: `/twincat3-cmd-pagefault-audit`
- Agent: `twincat-pagefault-auditor`
