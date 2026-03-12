---
name: twincat3-logging
description: Structured logging with F_IoT_Utilities_MessageLog from Tc3_IoT_Utilities. Log level filtering via Param GVL, instance-path resolution, edge-detected state logging, and FormatString helpers. Use when adding logging, diagnostics, ADS log output, error reporting, connection monitoring, or any F_IoT_Utilities_MessageLog usage in TwinCAT3.
---

# Logging with Tc3_IoT_Utilities

## Required Library

```xml
<PlaceholderReference Include="Tc3_IoT_Utilities">
  <DefaultResolution>Tc3_IoT_Utilities, * (Beckhoff Automation GmbH)</DefaultResolution>
  <Namespace>Tc3_IoT_Utilities</Namespace>
</PlaceholderReference>
```

## Log Levels (E_IoT_Utilities_MessageLog)

```iecst
{attribute 'to_string'}
TYPE E_IoT_Utilities_MessageLog : (
    None     := 0,
    Critical := 1,
    Error    := 2,
    Warning  := 3,
    Info     := 4,
    Debug    := 5
) BYTE;
END_TYPE
```

Lower number = higher severity. A message is logged when `eMask <= eMode`.

## Core Function: F_IoT_Utilities_MessageLog

```iecst
F_IoT_Utilities_MessageLog(
    eMode : E_IoT_Utilities_MessageLog;  // Active log level (from Param GVL)
    eMask : E_IoT_Utilities_MessageLog;  // Severity of THIS message
    sPath : REFERENCE TO T_MaxString;    // Instance path (auto-resolved)
    sFmt  : T_MaxString;                 // Format string with %s placeholders
    sArg1 : T_MaxString;                 // First substitution
    sArg2 : T_MaxString;                 // Second substitution
) : T_MaxString;                         // Returns the formatted log string
```

Internally maps levels to ADS log types:
- Critical/Error → `ADSLOG_MSGTYPE_ERROR`
- Warning → `ADSLOG_MSGTYPE_WARN`
- Info/Debug → `ADSLOG_MSGTYPE_HINT`

Output format: `| LEVEL | ReducedPath.sFmt(sArg1, sArg2)`

See [logging-patterns.md](logging-patterns.md) for complete patterns and real-world examples.

## Setup Checklist

Every FB that logs needs these two things:

### 1. Instance Path Variable

```iecst
{attribute 'instance-path'}
{attribute 'noinit'}
_sPath : T_MaxString;
```

Declare in `VAR` of the FB. The TwinCAT runtime fills this automatically with the full ADS path (e.g. `PLC.GVL_IoT.fbComClient`). The logging function strips the project prefix via `F_IoT_Utilities_ReduceAdsPath`.

### 2. Param GVL Log Level Constant

Every library defines its log level in its `Param_[Lib]` GVL:

```iecst
{attribute 'qualified_only'}
VAR_GLOBAL CONSTANT
    cnMessageLog : BYTE := 3; (* 0=None, 1=Critical, 2=Error, 3=Warning, 4=Info, 5=Debug *)
END_VAR
```

Pass as `eMode` parameter. Default 3 (Warning) means Critical + Error + Warning are logged. Set to 5 during development/debugging.

## Basic Logging Call

```iecst
F_IoT_Utilities_MessageLog(
        eMode := Param_MyLib.cnMessageLog,
        eMask := E_IoT_Utilities_MessageLog.Info,
        sPath := _sPath,
        sFmt  := 'Connected: %s:%s',
        sArg1 := sHostName,
        sArg2 := UINT_TO_STRING(nPort));
```

## FormatString Helpers (3–8 args)

When you need more than 2 substitution args, pre-format with helpers:

```iecst
F_IoT_Utilities_FormatString_2(sFormat, arg1, arg2) : T_MaxString
F_IoT_Utilities_FormatString_3(sFormat, arg1, arg2, arg3) : T_MaxString
...
F_IoT_Utilities_FormatString_8(sFormat, arg1..arg8) : T_MaxString
```

Use as `sArg1` input to `F_IoT_Utilities_MessageLog`:

```iecst
F_IoT_Utilities_MessageLog(
        eMode := Param_Influx.cnMessageLog,
        eMask := E_IoT_Utilities_MessageLog.Debug,
        sPath := _sPath,
        sFmt  := 'SendQuery.RequestInfo: (%s)',
        sArg1 := F_IoT_Utilities_FormatString_4(
                sFormat := 'Contentsize: %s Bytes / TableRows: %s with max. %s TableFields / Datapoints: %s',
                arg1    := TO_STRING(nContentSize),
                arg2    := TO_STRING(nTableRows),
                arg3    := TO_STRING(nTableFieldsMax),
                arg4    := TO_STRING(nDataPoints)),
        sArg2 := '');
```

## Inline Return Value Usage

`F_IoT_Utilities_MessageLog` returns the formatted string. Use inline for combined logging + string capture:

```iecst
_sLogString := F_IoT_FormatString_2(
        sFormat := '%s Message: %s',
        arg1    := SYSTEMTIME_TO_STRING(FILETIME64_TO_SYSTEMTIME(_fbLocalTime.tTimeLocal)),
        arg2    := F_IoT_Utilities_MessageLog(
                eMode := Param_IoT_BA.cnMessageLog,
                eMask := E_IoT_Utilities_MessageLog.Debug,
                sPath := THIS^._sPath,
                sFmt  := 'fbWriteAdsSymByName.VarName: %s Value: %s',
                sArg1 := sVarName,
                sArg2 := sValue));
```
