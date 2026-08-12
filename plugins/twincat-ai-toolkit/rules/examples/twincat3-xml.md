# TwinCAT3 TcPlcObject XML — Examples

Principles / GUID tables: `rules/twincat3-xml.mdc`. Read this file when creating or scaffolding new TcPlcObject files.

## Safe write pattern (scripts)

```python
# Read bytes → decode with detected encoding → edit CDATA only → encode same way → write bytes
# Use newline="" / write bytes so Python does not translate \n ↔ \r\n
path.write_bytes(edited_text.encode(detected_encoding))  # or open(..., "wb")
```

## GUID format

```
Id="{a1b2c3d4-e5f6-7890-abcd-ef1234567890}"
```

- PowerShell: `[guid]::NewGuid().ToString('D')` then wrap in `{}`
- Python: `import uuid; f'{{{uuid.uuid4()}}}'`

## .TcPOU — Function block skeleton

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <POU Name="FB_Example" Id="{GUID}" SpecialFunc="None">
    <Declaration><![CDATA[
FUNCTION_BLOCK FB_Example
VAR_INPUT
    bEnable : BOOL;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[
(* Implementation code here *)
]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>
```

## Method (inside POU)

```xml
    <Method Name="MethodName" Id="{DIFFERENT-GUID}">
      <Declaration><![CDATA[
METHOD MethodName : BOOL
VAR_INPUT
    nParam : INT;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[
MethodName := TRUE;
]]></ST>
      </Implementation>
    </Method>
```

## Property (read-write — 3 GUIDs)

```xml
    <Property Name="PropName" Id="{UNIQUE-GUID}">
      <Declaration><![CDATA[
PROPERTY PropName : INT
]]></Declaration>
      <Get Name="Get" Id="{UNIQUE-GUID}">
        <Declaration><![CDATA[VAR END_VAR]]></Declaration>
        <Implementation>
          <ST><![CDATA[PropName := _nValue;]]></ST>
        </Implementation>
      </Get>
      <Set Name="Set" Id="{UNIQUE-GUID}">
        <Declaration><![CDATA[VAR END_VAR]]></Declaration>
        <Implementation>
          <ST><![CDATA[_nValue := PropName;]]></ST>
        </Implementation>
      </Set>
    </Property>
```

## Action (no Declaration)

```xml
    <Action Name="A_HandleError" Id="{UNIQUE-GUID}">
      <Implementation>
        <ST><![CDATA[
nErrorCounter := nErrorCounter + 1;
bError        := TRUE;
]]></ST>
      </Implementation>
    </Action>
```

## .TcIO — Interface

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <Itf Name="I_Example" Id="{GUID}">
    <Declaration><![CDATA[INTERFACE I_Example
]]></Declaration>
  </Itf>
</TcPlcObject>
```

### Interface method (Declaration only)

```xml
    <Method Name="Start" Id="{GUID}">
      <Declaration><![CDATA[METHOD Start : BOOL
VAR_INPUT
    nMode : INT;
END_VAR
]]></Declaration>
    </Method>
```

### Interface property read-write (3 GUIDs)

```xml
    <Property Name="DisplayName" Id="{GUID}">
      <Declaration><![CDATA[PROPERTY DisplayName : STRING
]]></Declaration>
      <Get Name="Get" Id="{GUID}">
        <Declaration><![CDATA[]]></Declaration>
      </Get>
      <Set Name="Set" Id="{GUID}">
        <Declaration><![CDATA[]]></Declaration>
      </Set>
    </Property>
```

### Interface property read-only (2 GUIDs)

```xml
    <Property Name="IsEnabled" Id="{GUID}">
      <Declaration><![CDATA[PROPERTY IsEnabled : BOOL
]]></Declaration>
      <Get Name="Get" Id="{GUID}">
        <Declaration><![CDATA[]]></Declaration>
      </Get>
    </Property>
```

## .TcDUT — STRUCT

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <DUT Name="ST_Example" Id="{GUID}">
    <Declaration><![CDATA[
TYPE ST_Example :
STRUCT
    nValue   : INT;
    fPower   : LREAL;
    sName    : STRING(80);
    bEnabled : BOOL := TRUE;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
```

## .TcDUT — ENUM

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <DUT Name="E_Example" Id="{GUID}">
    <Declaration><![CDATA[
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_Example :
(
    IDLE    := 0,
    RUNNING := 1,
    ERROR   := 99
) := IDLE;
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
```

## .TcDUT — UNION

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <DUT Name="U_Example" Id="{GUID}">
    <Declaration><![CDATA[
TYPE U_Example :
UNION
    nValue   : DINT;
    arrBytes : ARRAY[0..3] OF BYTE;
END_UNION
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
```

## .TcGVL — Standard

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <GVL Name="GVL_Example" Id="{GUID}">
    <Declaration><![CDATA[
VAR_GLOBAL
    gbSystemReady : BOOL;
    gfActualSpeed : REAL;
END_VAR
]]></Declaration>
  </GVL>
</TcPlcObject>
```

## .TcGVL — Constant (Param)

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <GVL Name="Param_Example" Id="{GUID}">
    <Declaration><![CDATA[
VAR_GLOBAL CONSTANT
    cMaxRetries : UINT := 3;
    cTimeout    : TIME := T#5S;
END_VAR
]]></Declaration>
  </GVL>
</TcPlcObject>
```
