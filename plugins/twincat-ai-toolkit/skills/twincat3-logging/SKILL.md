---
name: twincat3-logging
description: Structured logging with F_IoT_Utilities_MessageLog (Tc3_IoT_Utilities). Param GVL level, instance-path, edge-detect, FormatString. Use for ADS log/diagnostics.
---

# Logging with Tc3_IoT_Utilities

**Read first**

1. `rules/twincat3-logging.mdc` — mandatory rules
2. [logging-patterns.md](logging-patterns.md) — edge-detect, HTTP/MQTT/Modbus samples, level guide

## Library

`Tc3_IoT_Utilities` via PlaceholderReference.

## API (summary)

`F_IoT_Utilities_MessageLog(eMode, eMask, sPath, sFmt, sArg1, sArg2) : T_MaxString`

- Levels (`E_IoT_Utilities_MessageLog`): None=0 … Debug=5. Logged when `eMask <= eMode`.
- ADS mapping: Critical/Error → ERROR; Warning → WARN; Info/Debug → HINT.
- Output: `| LEVEL | ReducedPath.sFmt(sArg1, sArg2)`

## Setup checklist

1. FB: `{attribute 'instance-path'}` + `{attribute 'noinit'}` → `_sPath : T_MaxString`
2. Param GVL: `cnMessageLog` (BYTE 0–5; default 3=Warning)
3. Calls: edge-detect only; both `sArg1`/`sArg2`; explicit conversions
4. >2 args: `F_IoT_Utilities_FormatString_N` into `sArg1`

ST for edge-detect, FormatString, domain samples → [logging-patterns.md](logging-patterns.md).
