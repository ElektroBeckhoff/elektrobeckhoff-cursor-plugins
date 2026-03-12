# TwinCAT3 XML Templates

## Function Block (TcPOU)

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <POU Name="FB_[LibName]_[Device]" Id="{GUID-1}" SpecialFunc="None">
    <Declaration><![CDATA[
FUNCTION_BLOCK FB_[LibName]_[Device]
VAR_INPUT
    bEnable : BOOL := TRUE;
END_VAR
VAR_OUTPUT
    bDone       : BOOL;
    bError      : BOOL;
    hrErrorCode : HRESULT;
END_VAR
VAR
    _nStep : INT;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[
CASE _nStep OF
    0: // Idle
        IF bEnable THEN
            _nStep := 1;
        END_IF

    1: // Processing
        bDone  := TRUE;
        _nStep := 2;

    2: // Done
        IF NOT bEnable THEN
            bDone  := FALSE;
            _nStep := 0;
        END_IF

END_CASE
]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>
```

## Function Block with Method

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <POU Name="FB_[LibName]_[Device]" Id="{GUID-1}" SpecialFunc="None">
    <Declaration><![CDATA[
FUNCTION_BLOCK FB_[LibName]_[Device]
VAR
    _nStep : INT;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[
// Cyclic logic
]]></ST>
    </Implementation>
    <Method Name="Init" Id="{GUID-2}">
      <Declaration><![CDATA[
METHOD Init : BOOL
VAR_INPUT
    stParam : REFERENCE TO ST_[LibName]_Param;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[
IF NOT __ISVALIDREF(stParam) THEN
    Init := FALSE;
    RETURN;
END_IF

Init := TRUE;
]]></ST>
      </Implementation>
    </Method>
    <Method Name="Reset" Id="{GUID-3}">
      <Declaration><![CDATA[
METHOD Reset : BOOL
]]></Declaration>
      <Implementation>
        <ST><![CDATA[
_nStep := 0;
Reset  := TRUE;
]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>
```

## Struct (TcDUT)

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <DUT Name="ST_[LibName]_[Device]_Measurement" Id="{GUID}">
    <Declaration><![CDATA[
TYPE ST_[LibName]_[Device]_Measurement :
STRUCT
    fPower       : LREAL;        // Active power [W]
    fEnergy      : LREAL;        // Total energy [Wh]
    fVoltage     : LREAL;        // Voltage [V]
    fCurrent     : LREAL;        // Current [A]
    fTemperature : LREAL;        // Temperature [C]
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
```

## Enum (TcDUT)

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <DUT Name="E_[LibName]_State" Id="{GUID}">
    <Declaration><![CDATA[
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_[LibName]_State :
(
    IDLE     := 0,
    STARTING := 1,
    RUNNING  := 2,
    STOPPING := 3,
    ERROR    := 99
) := IDLE;
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
```

## Global Variable List (TcGVL)

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <GVL Name="Param_[LibName]" Id="{GUID}">
    <Declaration><![CDATA[
VAR_GLOBAL CONSTANT
    cMaxDevices : UINT := 10;
    cTimeout    : TIME := T#5S;
    cMaxRetries : UINT := 3;
END_VAR
]]></Declaration>
  </GVL>
</TcPlcObject>
```

## Global_Version.TcGVL

```xml
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.15">
  <GVL Name="Global_Version" Id="{GUID}">
    <Declaration><![CDATA[
{attribute 'TcGenerated'}
VAR_GLOBAL CONSTANT
    stLibVersion_Tc3_[LibName] : ST_LibVersion := (
        iMajor    := 1,
        iMinor    := 0,
        iBuild    := 0,
        iRevision := 0,
        sVersion  := '1.0.0.0'
    );
END_VAR
]]></Declaration>
  </GVL>
</TcPlcObject>
```

## plcproj Registration

```xml
<ItemGroup>
  <Compile Include="POUs\FB_[LibName]_[Device].TcPOU">
    <SubType>Code</SubType>
  </Compile>
  <Compile Include="DUTs\Structs\ST_[LibName]_[Device]_Measurement.TcDUT">
    <SubType>Code</SubType>
  </Compile>
  <Compile Include="DUTs\Enums\E_[LibName]_State.TcDUT">
    <SubType>Code</SubType>
  </Compile>
  <Compile Include="GVLs\Param_[LibName].TcGVL">
    <SubType>Code</SubType>
  </Compile>
  <Compile Include="Version\Global_Version.TcGVL">
    <SubType>Code</SubType>
  </Compile>
</ItemGroup>
```
