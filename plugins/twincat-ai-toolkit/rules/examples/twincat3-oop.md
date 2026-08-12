# TwinCAT3 OOP — Examples

Principles: `rules/twincat3-oop.mdc`. Read when implementing EXTENDS, interfaces, properties, or FB_init.

## Inheritance — EXTENDS

```iecst
(* Base FB *)
FUNCTION_BLOCK FB_Base
VAR
    _bInitialized : BOOL;
END_VAR

METHOD Initialize : BOOL
    _bInitialized := TRUE;
    Initialize    := TRUE;
END_METHOD
```

```iecst
(* Derived FB *)
FUNCTION_BLOCK FB_Derived EXTENDS FB_Base
VAR
    _fSpeed : REAL;
END_VAR

METHOD Initialize : BOOL
    SUPER^.Initialize(); (* Call base method first *)
    _fSpeed := 0.0;
    Initialize := TRUE;
END_METHOD
```

## Interfaces

```iecst
(* Interface definition (.TcIO) *)
INTERFACE I_Controller
METHOD Start  : BOOL
METHOD Stop   : BOOL
METHOD IsRunning : BOOL
END_INTERFACE
```

```iecst
(* FB implementing interface *)
FUNCTION_BLOCK FB_MotorController IMPLEMENTS I_Controller
METHOD Start : BOOL
    _bRunning := TRUE;
    Start     := TRUE;
END_METHOD

METHOD Stop : BOOL
    _bRunning := FALSE;
    Stop      := TRUE;
END_METHOD

METHOD IsRunning : BOOL
    IsRunning := _bRunning;
END_METHOD
```

```iecst
(* Usage via interface reference *)
VAR
    iCtrl : I_Controller;
END_VAR

iCtrl := fbMotorController;

IF iCtrl.Start() THEN
    (* ... *)
END_IF
```

## Abstract FBs

```iecst
{attribute 'hide'}
FUNCTION_BLOCK ABSTRACT FB_AbstractBase
VAR
    _bEnabled : BOOL;
END_VAR

METHOD ABSTRACT Process : BOOL  (* must be implemented by derived FB *)
```

## Properties

```iecst
(* Getter *)
PROPERTY IsEnabled : BOOL
(* Get implementation: *)
IsEnabled := _bEnabled;

(* Setter — Set implementation: *)
_bEnabled := IsEnabled;
```

```iecst
fbMotor.IsEnabled := TRUE;   (* calls Set *)
bState := fbMotor.IsEnabled; (* calls Get *)
```

## FB_init — Dependency Injection

```iecst
{attribute 'hide'}
METHOD FB_init : BOOL
VAR_INPUT
    bInitRetains   : BOOL;
    bInCopyCode    : BOOL;
    fbComClient    : REFERENCE TO FB_SomeClient;
END_VAR
IF bInCopyCode THEN RETURN; END_IF

_fbComClient REF= fbComClient;
```

## Interface variables

```iecst
VAR
    _ipBase : I_Controller;
END_VAR

(* Assign in FB_init: *)
_ipBase := THIS^;

IF _ipBase <> 0 THEN
    _ipBase.Start();
END_IF
```
