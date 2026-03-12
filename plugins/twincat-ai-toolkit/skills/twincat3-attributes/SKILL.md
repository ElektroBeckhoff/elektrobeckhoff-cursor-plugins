---
name: twincat3-attributes
description: Complete reference for ALL TwinCAT3 IEC 61131-3 attribute pragmas ({attribute '...'}). Use when working with TwinCAT3 PLC code that needs attribute pragmas — hiding variables, making enums strict/qualified, enabling reflection/instance-path, controlling initialization order, retain/persistent variables, memory layout/pack_mode, ADS symbols, I/O linking, RPC, monitoring display, or any other pragma-controlled behavior. Source: https://infosys.beckhoff.com/content/1033/tc3_plc_intro/2529567115.html
---

# TwinCAT3 Attribute Pragmas

**Syntax:** `{attribute 'name'}` or `{attribute 'name' := 'value'}`
**Location:** Declaration part, one line **above** the target element.
**Exception:** Actions/Transitions in ST → at start of implementation (no declaration part).

Full details and examples: → [references/attributes-reference.md](references/attributes-reference.md)

---

## All Attributes — Quick Lookup

### Visibility & IntelliSense

| Attribute | Effect | Where |
|-----------|--------|-------|
| `'hide'` | Hide variable/POU from IntelliSense, cross-ref, ADS | Above POU or variable |
| `'hide_all_locals'` | Hide all VAR members of a POU | Above POU |
| `'conditionalshow'` | Un-hide specific variable inside a hidden POU | Above variable |
| `'conditionalshow_all_locals'` | Un-hide all locals despite hide | Above POU |

### Initialization

| Attribute | Effect | Where |
|-----------|--------|-------|
| `'noinit'` / `'no_init'` / `'no-init'` | Skip reset on cold/warm start | Above variable |
| `'initialize_on_call'` | Re-init input on every FB call (pointer safety) | Above FB + above variable |
| `'init_on_onchange'` / `'init_on_onlchange'` | Re-init on online change | Above variable |
| `'call_after_init'` | Call method after FB_init (before first cycle) | Above FB + above method |
| `'call_on_type_change' := 'FB_B'` | Call method when referenced type changes | Above method |

### OOP & Call Control

| Attribute | Effect | Where |
|-----------|--------|-------|
| `'reflection'` | Enable instance-path / is_connected scanning | Above FB |
| `'instance-path'` | Fill STRING with runtime instance path | Above STRING var (needs reflection + noinit) |
| `'is_connected' := 'inputName'` | BOOL = TRUE when named input is wired | Above BOOL var (needs reflection) |
| `'no_explicit_call' := 'msg'` | Block direct FB body call (error with msg) | Above FB |
| `'no_copy'` | Skip copy during online change, re-init instead | Above variable |
| `'no_assign'` | Block FB instance assignment (compile error) | Above FB |
| `'no_assign_warning'` | Same but warning only | Above FB |
| `'no_virtual_actions'` | Disable virtual dispatch for actions | Above FB |
| `'no-exit'` | Skip FB_exit generation | Above FB |
| `'enable_dynamic_creation'` | Allow `__NEW(FB_Type)` | Above FB/DUT |

### Enum Safety

| Attribute | Effect | Where |
|-----------|--------|-------|
| `'qualified_only'` | Force `E_Name.Value` / `GVL.var` qualified access | Above TYPE or VAR_GLOBAL |
| `'strict'` | Block invalid assignments/arithmetic on enum | Above TYPE |
| `'to_string'` | Auto-generate `TO_STRING()` for enum members | Above TYPE |

### Data Layout & Memory

| Attribute | Effect | Where |
|-----------|--------|-------|
| `'pack_mode' := '0\|1\|2\|4\|8'` | Set struct byte alignment (1=no padding) | Above STRUCT |
| `'minimal_input_size' := 'N'` | Set min process image size | Above I/O variable |
| `'c++_compatible'` | C++ layout for shared structs with TcCOM | Above STRUCT |
| `'estimated-stack-usage' := 'N'` | Declare stack usage in bytes | Above POU |
| `'memory_check'` | Enable runtime memory checks | Above POU |

### Retain & Persistence

| Attribute | Effect | Survives download |
|-----------|--------|------------------|
| `'TcRetain'` | Retain in NovRAM (power fail only) | ❌ |
| `'TcPersistent'` | Persistent on file system (power fail + download) | ✅ |
| `'TcIgnorePersistent'` | Don't restore from persistence file on start | Above variable |
| `'TcInitOnReset'` | Re-init to default on every reset | Above variable |

### Strings & Encoding

| Attribute | Effect | Where |
|-----------|--------|-------|
| `'TcEncoding' := 'UTF-8'` | STRING uses UTF-8 (special chars, JSON) | Above STRING var |
| `'parameterstringof'` | Pass pragma parameter as string | Above var/method |
| `'to_string'` | Enum → string conversion function (see Enum) | Above ENUM TYPE |

### ADS Symbols & I/O Linking

| Attribute | Effect | Where |
|-----------|--------|-------|
| `'TcNoSymbol'` / `'tc_no_symbol'` | No ADS symbol generated | Above variable |
| `'TcHideSubItems'` | Parent visible in ADS, children not | Above struct var |
| `'TcInitSymbol'` | ADS client writes value before PLC start | Above variable |
| `'TcLinkTo' := 'path'` | Link to hardware I/O by path | Above variable |
| `'TcLinkToOSO' := 'path'` | Link to output-synchronous I/O | Above variable |
| `'TcSwapWord'` | Swap bytes within each WORD (endian fix) | Above variable |
| `'TcSwapDWord'` | Swap WORDs within each DWORD (endian fix) | Above variable |
| `'TcDisplayScale' := 'f'` | Scale display value in System Manager | Above variable |
| `'TcNcAxis'` | Link to NC axis object | Above AXIS_REF var |
| `'TcCallAfterOutputUpdate'` | Call POU after I/O output update | Above POU |
| `'TcRpcEnable'` | Enable ADS Remote Procedure Call on method | Above method |
| `'TcContextId' := 'N'` | Assign to PLC task context by ID | Above POU |
| `'TcContextName' := 'name'` | Assign to PLC task context by name | Above POU |
| `'Tc2GvlVarNames'` | TC2 compatibility for GVL naming | Above VAR_GLOBAL |

### Compilation & Linking

| Attribute | Effect | Where |
|-----------|--------|-------|
| `'linkalways'` | Always include in output even if unreferenced | Above POU or VAR_GLOBAL |
| `'obsolete' := 'msg'` | Compiler warning with message on use | Above POU/TYPE |
| `'const_replaced'` | Inline constant value (no ADS symbol) | Above CONSTANT var |
| `'const_non_replaced'` | Keep constant as ADS symbol (not inlined) | Above CONSTANT var |
| `'no_check'` | Disable implicit range checks | Above variable |
| `'subsequent'` | Compile this POU last | Above POU |
| `'no-analysis'` | Disable static analysis warnings | Above POU |
| `'dataflow'` | Enable dataflow diagram view | Above POU |
| `'noflow'` / `'flow'` | Dataflow visualization for variable | Above variable |

### Monitoring & Display

| Attribute | Effect | Where |
|-----------|--------|-------|
| `'monitoring' := 'variable'` | Monitor property via cached variable | Above property |
| `'monitoring' := 'call'` | Monitor property by calling Get (scalar only) | Above property |
| `'monitoring_display'` | Custom display format in online view | Above variable |
| `'displaymode' := 'Hex\|Dec\|Bin'` | Default display format in declaration editor | Above variable |
| `'ExpandFully'` | Expand array/struct by default in online view | Above variable |
| `'pingroup' := 'name'` | Group pins visually in FBD | Above variable |
| `'pin_presentation_order_inputs' := 'N'` | Pin order in FBD (inputs) | Above variable |
| `'pin_presentation_order_outputs' := 'N'` | Pin order in FBD (outputs) | Above variable |

### Init Order & Timing

| Attribute | Effect | Where |
|-----------|--------|-------|
| `'global_init_slot' := 'N'` | GVL init order (lower = earlier) | Above VAR_GLOBAL |
| `'call_after_global_init_slot' := 'N'` | Call POU/method after GVL slot N init | Above POU or method |
| `'call_after_online_change_slot' := 'N'` | Call POU after online change, slot N | Above POU |
| `'init_namespace'` | Init namespace before other startup | Above POU (library dev) |
