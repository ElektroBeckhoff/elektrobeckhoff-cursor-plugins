# TwinCAT3 Attributes — Complete Reference

Source: https://infosys.beckhoff.com/content/1033/tc3_plc_intro/2529567115.html

**Syntax:** `{attribute 'name'}` or `{attribute 'name' := 'value'}`
**Location:** Declaration part, one line above the target element.
**Exception:** In Actions/Transitions (ST), place at start of implementation (no declaration part exists).

---

## Table of Contents

1. [Visibility & IntelliSense](#1-visibility--intellisense)
2. [Initialization Control](#2-initialization-control)
3. [OOP & Call Control](#3-oop--call-control)
4. [Enum Safety](#4-enum-safety)
5. [Data Layout & Memory](#5-data-layout--memory)
6. [Retain & Persistence](#6-retain--persistence)
7. [Strings & Encoding](#7-strings--encoding)
8. [ADS Symbols & I/O Linking](#8-ads-symbols--io-linking)
9. [Compilation & Linking](#9-compilation--linking)
10. [Monitoring & Display](#10-monitoring--display)
11. [Init Order & Timing](#11-init-order--timing)
12. [User-Defined Attributes](#12-user-defined-attributes)
13. [Copy-Paste Quick Reference](#13-copy-paste-quick-reference)

---

## 1. Visibility & IntelliSense

### `{attribute 'hide'}`
Hides a variable or POU from IntelliSense, cross-reference search, and online monitoring. No ADS symbol is generated — symbolic access from ADS clients, SCADA, or HMI is blocked.

- **On a POU:** hides the entire POU from input assistant
- **On a variable:** hides only that specific variable; put the pragma on the line immediately above it

```iecst
FUNCTION_BLOCK FB_Example
VAR_INPUT
    bPublic  : BOOL;
    {attribute 'hide'}
    bPrivate : BOOL;  // hidden from IntelliSense and ADS
END_VAR
```

> ⚠️ Variables with `'hide'` cannot be saved as PERSISTENT. Process image generation is also suppressed for hidden variables.

---

### `{attribute 'hide_all_locals'}`
Hides **all** variables in the `VAR` section of a POU. VAR_INPUT / VAR_OUTPUT remain visible. Useful for library FBs where internal state should never be exposed.

```iecst
{attribute 'hide_all_locals'}
FUNCTION_BLOCK FB_InternalOnly
```

---

### `{attribute 'conditionalshow'}`
Shows a specific variable in online mode even if the POU has `'hide_all_locals'`. Acts as an exception to the blanket hide.

```iecst
{attribute 'hide_all_locals'}
FUNCTION_BLOCK FB_Example
VAR
    _nHidden : INT;          // hidden
    {attribute 'conditionalshow'}
    _nVisible : INT;         // visible despite hide_all_locals
END_VAR
```

---

### `{attribute 'conditionalshow_all_locals'}`
Shows all local variables in online mode even if the POU is hidden. Applied to the POU, not individual variables.

---

## 2. Initialization Control

### `{attribute 'noinit'}` / `{attribute 'no_init'}` / `{attribute 'no-init'}`
Variable is **not reset** on PLC reset or cold start. Retains its value. All three spellings are equivalent.

Required companion for `'instance-path'`.

```iecst
VAR
    nReset    : INT;             // reset to 0 on every cold start
    {attribute 'noinit'}
    nKeepVal  : INT;             // keeps value across resets
END_VAR
```

---

### `{attribute 'initialize_on_call'}`
Applied to a FB **and** individual input variables. Causes those input variables to be re-initialized every time the FB is called. Prevents stale pointer values after online changes.

Must appear **both** on the FB (first line) **and** on each affected input variable:

```iecst
{attribute 'initialize_on_call'}
FUNCTION_BLOCK FB_WithPointer
VAR_INPUT
    {attribute 'initialize_on_call'}
    pSetpoint : POINTER TO LREAL := 0;
END_VAR
```

---

### `{attribute 'init_on_onchange'}` / `{attribute 'init_on_onlchange'}`
Re-initializes the variable/object on every online change (both spellings accepted).

---

### `{attribute 'call_after_init'}`
Causes a **method** to be called automatically after FB_init and instance initialization, before the first PLC cycle. Method name is freely selectable (not FB_init, FB_reinit, FB_exit).

Must appear on **both** the FB and the method:

```iecst
{attribute 'call_after_init'}
FUNCTION_BLOCK FB_Example
```

```iecst
{attribute 'call_after_init'}
METHOD MyPostInit : BOOL
// called automatically after initialization
```

> In derived FBs: override the method and call `SUPER^.MyPostInit()`.

---

### `{attribute 'call_on_type_change' := 'FB_B, FB_C'}`
Applied to a **method** of FB_A. The method is called automatically when the type of a referenced FB (via POINTER or REFERENCE) changes. Comma-separate multiple FB type names.

```iecst
{attribute 'call_on_type_change' := 'FB_B, FB_C'}
METHOD METH_ReactOnTypeChange : INT
```

---

## 3. OOP & Call Control

### `{attribute 'reflection'}`
Marks a FB so the compiler searches it for `'instance-path'` and `'is_connected'` variables. Without `'reflection'`, those attributes have no effect. Improves build time by limiting the search scope.

```iecst
{attribute 'reflection'}
FUNCTION_BLOCK FB_WithPath
VAR
    {attribute 'instance-path'}
    {attribute 'noinit'}
    sPath : STRING;
END_VAR
```

---

### `{attribute 'instance-path'}`
Applied to a `STRING` variable inside a FB that also has `{attribute 'reflection'}`. The string is automatically filled with the full device-tree instance path (e.g. `".MAIN.fbMotor1"`) at FB initialization.

**Requires:** `'reflection'` on the FB **AND** `'noinit'` on the STRING variable.

```iecst
{attribute 'reflection'}
FUNCTION_BLOCK FB_WithPath
VAR
    {attribute 'instance-path'}
    {attribute 'noinit'}
    sInstancePath : STRING;  // auto = ".MAIN.fbDevice1"
END_VAR
```

---

### `{attribute 'is_connected' := 'inputVarName'}`
Applied to a BOOL variable inside a FB (with `'reflection'`). The BOOL becomes TRUE when the named input has an assignment at the call site, FALSE if not connected.

```iecst
{attribute 'reflection'}
FUNCTION_BLOCK FB_Sample
VAR_INPUT
    nIn1 : INT;
    nIn2 : INT;
END_VAR
VAR
    {attribute 'is_connected' := 'nIn1'}
    bIn1Connected : BOOL;   // TRUE if nIn1 is wired at call site
    {attribute 'is_connected' := 'nIn2'}
    bIn2Connected : BOOL;
END_VAR
```

---

### `{attribute 'no_explicit_call' := 'message'}`
Prevents direct call of the FB body (`fbInstance()`). Methods and properties can still be called normally. Generates a **compile error** with the message text if the body is called directly.

```iecst
{attribute 'no_explicit_call' := 'do not call this POU directly, use methods'}
FUNCTION_BLOCK FB_OopOnly
```

---

### `{attribute 'no_copy'}`
Prevents copying of a specific variable during an online change (the variable is re-initialized instead of copied). Use for pointer variables that may become invalid after an online change moves memory.

```iecst
VAR
    {attribute 'no_copy'}
    pBuffer : POINTER TO BYTE;  // re-initialized on online change
END_VAR
```

---

### `{attribute 'no_assign'}`
Prevents assigning one FB instance to another (`fb1 := fb2` → **compile error**). Use for FBs containing pointers where copying would cause issues.

```iecst
{attribute 'no_assign'}
FUNCTION_BLOCK FB_WithPointers
VAR
    pData : POINTER TO LREAL;
END_VAR
```

---

### `{attribute 'no_assign_warning'}`
Same as `'no_assign'` but generates a **warning** instead of an error.

---

### `{attribute 'no_virtual_actions'}`
Disables virtual dispatch for actions in a derived FB. Without this, actions in derived FBs override parent actions (virtual by default). Add this to prevent unintended overriding.

---

### `{attribute 'no-exit'}`
Prevents generation of FB_exit (destructor) code for a POU. Reduces overhead when no cleanup is needed.

---

### `{attribute 'enable_dynamic_creation'}`
Required for FBs/DUTs that can be dynamically allocated using `__NEW()`. Without this, `__NEW(FB_Type)` causes a compile error.

```iecst
{attribute 'enable_dynamic_creation'}
FUNCTION_BLOCK FB_DynamicAlloc
```

Usage:
```iecst
pFB := __NEW(FB_DynamicAlloc);
// ...
__DELETE(pFB);
```

---

## 4. Enum Safety

### `{attribute 'qualified_only'}`
Forces **qualified access** — GVL variables must use `GVL.varName`, enum values must use `E_Name.Value`. Prevents name collisions with local variables.

Applied to the whole GVL or enum — cannot be applied to individual variables within a GVL.

```iecst
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_DeviceState :
(
    IDLE    := 0,
    RUNNING := 1,
    ERROR   := 99
) := IDLE;
END_TYPE
```

Correct: `eState := E_DeviceState.RUNNING;`
Wrong: `eState := RUNNING;` → compile error

---

### `{attribute 'strict'}`
Applied to ENUMs. Causes **compile errors** for:
- Assigning a non-enum-typed value to an enum variable
- Assigning a constant that is not a valid enum member
- Arithmetic operations on enum variables

Always combine with `'qualified_only'` on ENUMs.

---

### `{attribute 'to_string'}`
Applied to an ENUM. Automatically generates a `TO_STRING()` conversion function for the enum, returning the member name as a string. Useful for diagnostics/logging.

```iecst
{attribute 'qualified_only'}
{attribute 'strict'}
{attribute 'to_string'}
TYPE E_Mode :
(
    AUTO   := 0,
    MANUAL := 1
) := AUTO;
END_TYPE
```

Usage: `sMode := TO_STRING(eMode);` → returns `'AUTO'` or `'MANUAL'`

---

## 5. Data Layout & Memory

### `{attribute 'pack_mode' := 'N'}`
Controls byte alignment of a STRUCT. Applied above the TYPE definition. Default (no attribute) = 8-byte aligned.

| Value | Alignment | Typical use |
|-------|-----------|-------------|
| `'0'` or `'1'` | All vars at byte addresses — no padding gaps | Modbus, serial protocol mapping |
| `'2'` | 2-byte aligned | Mixed BOOL/INT structs |
| `'4'` | 4-byte aligned | Mixed with DWORD/DINT |
| `'8'` | 8-byte aligned (default) | Standard TwinCAT behavior |

```iecst
{attribute 'pack_mode' := '1'}
TYPE ST_ModbusFrame :
STRUCT
    nFunction : BYTE;
    nAddress  : WORD;
    nData     : WORD;
END_STRUCT
END_TYPE
```

> ⚠️ Always use `'pack_mode' := '1'` when mapping a STRUCT directly onto a Modbus/serial byte buffer to avoid hidden padding bytes.

---

### `{attribute 'minimal_input_size' := 'N'}`
Sets a minimum byte size for the process image of I/O variables. Used with hardware mapping.

---

### `{attribute 'c++_compatible'}`
Generates C++-compatible struct layout. Needed when sharing data structures between TwinCAT PLC and TcCOM C++ objects via shared memory.

---

### `{attribute 'estimated-stack-usage' := 'N'}`
Manually declares the estimated stack usage in bytes for a POU. Use when automatic analysis underestimates (e.g. recursive patterns, indirect calls).

---

### `{attribute 'memory_check'}`
Enables additional runtime memory checks for the POU. Useful for debugging heap/pointer issues.

---

## 6. Retain & Persistence

### `{attribute 'TcRetain'}`
Marks a variable as **Retain** — value survives power failure (stored in NovRAM via Retain Handler). Alternative to `VAR RETAIN` keyword.

```iecst
VAR
    {attribute 'TcRetain'}
    nOperatingHours : UDINT;  // survives power loss
END_VAR
```

> ⚠️ Cannot be applied to whole POUs, only individual variables.

---

### `{attribute 'TcPersistent'}`
Marks a variable as **Persistent** — value is saved to file and restored on next PLC start (survives code download too). Alternative to `VAR PERSISTENT`.

```iecst
VAR
    {attribute 'TcPersistent'}
    nTotalCycles : UDINT;  // survives downloads and power loss
END_VAR
```

| | Retain | Persistent |
|--|--------|-----------|
| Survives power loss | ✅ | ✅ |
| Survives code download | ❌ | ✅ |
| Storage | NovRAM | File system |

---

### `{attribute 'TcIgnorePersistent'}`
Prevents a PERSISTENT variable from being restored from the persistence file on startup. The variable keeps its declaration default value even if a saved value exists.

---

### `{attribute 'TcInitOnReset'}`
Re-initializes the variable to its declaration default on every PLC reset (cold AND warm start), even if it is a RETAIN/PERSISTENT variable.

---

## 7. Strings & Encoding

### `{attribute 'TcEncoding' := 'UTF-8'}`
Makes a `STRING` variable use UTF-8 encoding. Required for non-ASCII characters (€, ü, Chinese, etc.) especially in JSON/MQTT payloads.

```iecst
VAR
    {attribute 'TcEncoding' := 'UTF-8'}
    sJsonPayload : STRING(4095);
END_VAR
```

> ⚠️ UTF-8 uses 1–4 bytes per character. `LEN(s)` returns **bytes**, not characters. Assign literals using `UTF8#'text'` (TC3.1 Build 4026+) or helper functions `sLiteral_TO_UTF8()` / `wsLiteral_TO_UTF8()`.

---

### `{attribute 'parameterstringof'}`
Allows passing the string representation of a pragma parameter to a function. Used in metaprogramming / template patterns.

---

## 8. ADS Symbols & I/O Linking

### `{attribute 'TcNoSymbol'}` / `{attribute 'tc_no_symbol'}`
Prevents an ADS symbol from being generated. The variable becomes invisible to all ADS clients (SCADA, HMI, monitoring tools). Use for purely internal pointer or buffer variables.

```iecst
VAR
    {attribute 'TcNoSymbol'}
    _pInternalBuffer : POINTER TO BYTE;
END_VAR
```

---

### `{attribute 'TcHideSubItems'}`
The parent variable (STRUCT/FB) is visible in the ADS symbol tree, but its child members are not accessible individually. The parent can be read/written as a block, but not member-by-member.

---

### `{attribute 'TcInitSymbol'}`
Marks a variable as an "Init Symbol" — its value is written by an ADS client **before** the PLC starts running. Used for startup configuration that must come from an external source.

---

### `{attribute 'TcLinkTo' := 'HW_path'}` / `{attribute 'TcLinkToOSO' := 'HW_path'}`
Links a PLC variable to a hardware I/O channel via its device tree path. Alternative to graphical linking in the TwinCAT System Manager.

```iecst
VAR
    {attribute 'TcLinkTo' := 'Term 1 (EK1100)^Term 2 (EL1008)^Channel 1^Input'}
    bDigitalInput : BOOL;
END_VAR
```

`TcLinkToOSO` is the variant for linking to outputs with output-synchronous update.

---

### `{attribute 'TcSwapWord'}`
Swaps the byte order within each WORD of the variable. Used when external hardware sends 16-bit values in opposite endianness.

```iecst
{attribute 'TcSwapWord'}
nRawRegister : WORD;  // bytes A,B become B,A after swap
```

---

### `{attribute 'TcSwapDWord'}`
Swaps the WORD order within each DWORD (32-bit). Used for 32-bit endianness correction (word-swap, not byte-swap within word).

---

### `{attribute 'TcDisplayScale' := 'factor'}`
Scales the display value shown in the TwinCAT System Manager. Visual only — does not affect the actual variable value or ADS symbol.

---

### `{attribute 'TcNcAxis'}`
Links a variable to a TwinCAT NC axis object. Applied to variables of type `AXIS_REF`.

---

### `{attribute 'TcCallAfterOutputUpdate'}`
POU is called after the output update phase of the I/O task. Ensures the POU's outputs are written in the same cycle as the I/O update.

---

### `{attribute 'TcRpcEnable'}`
Enables a method for ADS Remote Procedure Call (RPC). The method can then be invoked remotely by ADS clients from outside the PLC.

```iecst
{attribute 'TcRpcEnable'}
METHOD GetVersion : STRING
```

---

### `{attribute 'TcContextId' := 'N'}` / `{attribute 'TcContextName' := 'name'}`
Assigns a specific PLC task context (by numeric ID or name) to a POU. Used in multi-core or multi-task projects to pin code execution to a specific core/task.

---

### `{attribute 'Tc2GvlVarNames'}`
Enables TwinCAT 2 compatibility mode for global variable naming conventions. Use only when migrating TC2 projects.

---

## 9. Compilation & Linking

### `{attribute 'linkalways'}`
Forces the compiler to always include this POU or GVL in the compiled output, even if it has no references anywhere in the project. Without this, the linker may strip unreferenced code.

```iecst
{attribute 'linkalways'}
PROGRAM PRG_Watchdog
```

```iecst
{attribute 'linkalways'}
VAR_GLOBAL
    gDiag : ST_Diagnostics;
END_VAR
```

---

### `{attribute 'obsolete' := 'user message'}`
Marks a POU or data type as deprecated. Generates a **compiler warning** with the message text whenever the marked element is used. Use to guide users to a replacement.

```iecst
{attribute 'obsolete' := 'Use FB_NewDevice instead of FB_OldDevice'}
FUNCTION_BLOCK FB_OldDevice
```

---

### `{attribute 'const_replaced'}`
The constant value is **inlined** at every call site (like a C `#define`). No ADS symbol is generated — the constant is not accessible at runtime.

---

### `{attribute 'const_non_replaced'}`
The constant is **kept as a named symbol** in the compiled output (not inlined). Accessible via ADS at runtime. Use when the constant must be visible in the symbol configuration or SCADA.

```iecst
VAR_GLOBAL CONSTANT
    {attribute 'const_non_replaced'}
    nMaxSpeed : INT := 3000;  // visible via ADS
    fKp       : REAL := 1.5;  // inlined (no ADS symbol)
END_VAR
```

---

### `{attribute 'no_check'}`
Disables implicit range checks on a variable. Removes safety bounds checking for that variable — use only when performance is critical and bounds are guaranteed by other means.

---

### `{attribute 'subsequent'}`
Applied to POUs — causes the POU to be compiled **after** all others. Use when compilation order matters (e.g. type definitions that other POUs depend on).

---

### `{attribute 'no-analysis'}`
Disables static code analysis warnings for the marked POU. Use only for generated/imported code or known false positives. Do NOT use to silence real bugs.

---

### `{attribute 'dataflow'}`
Enables the Dataflow diagram view for this POU in the TwinCAT editor (visualizes signal flow graphically in FBD-style).

---

### `{attribute 'noflow'}` / `{attribute 'flow'}`
Controls dataflow visualization for individual variables within a POU.

---

## 10. Monitoring & Display

### `{attribute 'monitoring' := 'variable'}` / `{attribute 'monitoring' := 'call'}`
Controls how a property value is monitored in online view and watch lists.

| Value | Behavior |
|-------|----------|
| `'variable'` | Creates an implicit variable that stores the last property value whenever Set/Get is called. Shows that cached value. Works for all types including structs. |
| `'call'` | Monitors by calling the property Get method directly. Real-time value. Only works for **scalar types or pointers** (not structs/arrays). |

```iecst
PROPERTY Minutes : INT
// Declaration:
{attribute 'monitoring' := 'variable'}
```

---

### `{attribute 'monitoring_display'}`
Controls the display format of a value in online monitoring view.

---

### `{attribute 'displaymode' := 'format'}`
Sets the default display format in the declaration editor.

| Value | Display |
|-------|---------|
| `'Bin'` | Binary |
| `'Dec'` | Decimal |
| `'Hex'` | Hexadecimal |

```iecst
{attribute 'displaymode' := 'Hex'}
nStatusWord : WORD;  // shown as 16#0000 in declarations
```

---

### `{attribute 'ExpandFully'}`
Applied to an array or struct variable — shows all elements expanded by default in the online monitoring view (no need to manually expand).

---

### `{attribute 'pingroup' := 'name'}`
Groups FB inputs/outputs together visually in the FBD (Function Block Diagram) editor. Pins with the same group name appear as a block.

---

### `{attribute 'pin_presentation_order_inputs' := 'N'}` / `{attribute 'pin_presentation_order_outputs' := 'N'}`
Sets the visual display order of input/output pins in the FBD editor. Lower N = higher up.

---

## 11. Init Order & Timing

### `{attribute 'global_init_slot' := 'N'}`
Controls the initialization order of GVLs. Lower slot numbers initialize first. GVLs with the same slot number have undefined order relative to each other.

```iecst
{attribute 'global_init_slot' := '10'}
VAR_GLOBAL
    gSystemConfig : ST_Config;  // initialized early (slot 10)
END_VAR
```

---

### `{attribute 'call_after_global_init_slot' := 'N'}`
Applied to functions or programs. The POU is called automatically after all GVLs with the given init slot have finished initializing. Lower N = called earlier.

If applied to a method, TwinCAT calls that method on **all instances** of the FB after the specified slot.

---

### `{attribute 'call_after_online_change_slot' := 'N'}`
Applied to functions or programs. The POU is called automatically after an online change, in slot order (lower N = called first).

---

### `{attribute 'init_namespace'}`
Initializes the namespace for a POU during startup. Used in library development where namespace setup must precede other initialization.

---

## 12. User-Defined Attributes

Custom attributes can be defined freely and queried in conditional compilation pragmas. They act as compile-time feature flags.

```iecst
{attribute 'my_feature' := 'enabled'}
FUNCTION_BLOCK FB_WithFeature
```

Query with conditional pragma:
```iecst
{IF defined(attr:'my_feature')}
    // compiled only when attribute is present
{END_IF}
```

Full documentation: https://infosys.beckhoff.com/content/1033/tc3_plc_intro/2529572491.html

---

## 13. Copy-Paste Quick Reference

```iecst
// Hide from IntelliSense + ADS (on POU or variable)
{attribute 'hide'}

// Hide all internal VAR from IntelliSense
{attribute 'hide_all_locals'}
FUNCTION_BLOCK FB_Library

// Get runtime instance path (".MAIN.fbDevice")
{attribute 'reflection'}
FUNCTION_BLOCK FB_WithPath
VAR
    {attribute 'instance-path'}
    {attribute 'noinit'}
    sPath : STRING;
END_VAR

// Detect if an input is wired at the call site
{attribute 'reflection'}
FUNCTION_BLOCK FB_Sample
VAR_INPUT
    nIn1 : INT;
END_VAR
VAR
    {attribute 'is_connected' := 'nIn1'}
    bIn1Wired : BOOL;
END_VAR

// Enum: safe qualified access + no arithmetic
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_State : ( IDLE := 0, RUNNING := 1, ERROR := 99 ) := IDLE; END_TYPE

// Enum: also generate TO_STRING() function
{attribute 'qualified_only'}
{attribute 'strict'}
{attribute 'to_string'}
TYPE E_Mode : ( AUTO := 0, MANUAL := 1 ) := AUTO; END_TYPE

// STRUCT: no byte padding (for protocol/Modbus mapping)
{attribute 'pack_mode' := '1'}
TYPE ST_Protocol : STRUCT ... END_STRUCT END_TYPE

// UTF-8 string (for JSON/MQTT with special chars)
{attribute 'TcEncoding' := 'UTF-8'}
sPayload : STRING(4095);

// Retain value after power failure
{attribute 'TcRetain'}
nOperatingHours : UDINT;

// Persistent across code downloads + power failure
{attribute 'TcPersistent'}
nTotalCycles : UDINT;

// No ADS symbol (internal pointers/buffers)
{attribute 'TcNoSymbol'}
pBuffer : POINTER TO BYTE;

// Prevent direct FB body call (methods-only FB)
{attribute 'no_explicit_call' := 'use methods only'}
FUNCTION_BLOCK FB_OopOnly

// Allow dynamic __NEW() allocation
{attribute 'enable_dynamic_creation'}
FUNCTION_BLOCK FB_Dynamic

// Prevent instance-to-instance assignment (FB with pointers)
{attribute 'no_assign'}
FUNCTION_BLOCK FB_WithPointers

// Reinit pointer variable on online change (not copied)
VAR
    {attribute 'no_copy'}
    pData : POINTER TO BYTE;
END_VAR

// Always compile/link even if unreferenced
{attribute 'linkalways'}
PROGRAM PRG_Watchdog

// Mark as deprecated with message
{attribute 'obsolete' := 'Use FB_New instead'}
FUNCTION_BLOCK FB_Old

// Show in hex in declaration editor
{attribute 'displaymode' := 'Hex'}
nStatusWord : WORD;

// Keep constant as ADS symbol (not inlined)
{attribute 'const_non_replaced'}
nMaxRetries : INT := 3;

// Link I/O variable to hardware
{attribute 'TcLinkTo' := 'Box 1 (EK1100)^Term 2 (EL1008)^Channel 1^Input'}
bDigitalIn : BOOL;

// Swap 16-bit byte order (endianness fix)
{attribute 'TcSwapWord'}
nRawValue : WORD;

// Enable ADS RPC for a method
{attribute 'TcRpcEnable'}
METHOD GetStatus : STRING

// Init slot: this GVL initializes before slot 20+ GVLs
{attribute 'global_init_slot' := '10'}
VAR_GLOBAL
    gConfig : ST_Config;
END_VAR

// Method called after FB_init completes
{attribute 'call_after_init'}
FUNCTION_BLOCK FB_Example

{attribute 'call_after_init'}
METHOD PostInit : BOOL
```
