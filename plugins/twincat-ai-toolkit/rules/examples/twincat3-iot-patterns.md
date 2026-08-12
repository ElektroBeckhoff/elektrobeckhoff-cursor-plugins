# IoT Building Automation — Examples

Principles: `rules/twincat3-iot-patterns.mdc`. Read this file when implementing Tc3_IoT_BA device/widget wiring.

## Architecture sketch

```
FB_IoT_ComClient (MQTT broker, JSON, ADS bridge)
  └── FB_IoT_View (UI view container)
       └── FB_IoT_Widget_* (Lighting, Shading, AirCon, etc.)
            └── FB_IoT_[Device]_* (Shelly, Hue, Somfy, Dali device)
```

## FB_init dependency injection (IoT-BA)

```iecst
{attribute 'hide'}
METHOD FB_init : BOOL
VAR_INPUT
    bInitRetains      : BOOL;
    bInCopyCode       : BOOL;
    fbIotComClient    : REFERENCE TO FB_IoT_ComClient;
    fbView            : REFERENCE TO FB_IoT_View;
    stShellyMqttParam : REFERENCE TO ST_Shelly_MqttParam;  (* device-specific *)
END_VAR
```

Inside `FB_init`:

```iecst
IF bInCopyCode THEN RETURN; END_IF
THIS^._ipBase   := THIS^._fbWidget;
THIS^._ipWidget := THIS^._fbWidget;
InitClient(fbIotComClient);
InitView(fbView);
InitMqttClient(stShellyMqttParam);  (* device-specific init *)
```

## Widget write every cycle

```iecst
_fbWidget.stVariantInput.sDisplayName := sDisplayName;
_fbWidget.stVariantInput.bReadOnly    := bReadOnly;
_fbWidget.stVariantInput.bLight       := UINT_TO_BOOL(nTargetLevelPercent);
_fbWidget.stVariantInput.nLight       := UINT_TO_INT(nTargetLevelPercent);
_fbWidget.stVariantInput.eUserGroup   := eUserGroup;
_fbWidget(bEnable := bVisible, bError => bError, eError => eError);
```

## Widget command read

```iecst
IF _fbWidget.bSetValue THEN
    _nSetValue := INT_TO_UINT(_fbWidget.nSetValue);
END_IF
IF _fbWidget.bOn THEN ... END_IF
IF _fbWidget.bOff THEN ... END_IF
```

## InitParameter

```iecst
METHOD InitParameter : BOOL
_fbWidget.stVariantInput.bLightModeVisible    := FALSE;
_fbWidget.stVariantInput.bLightSliderVisible  := TRUE;
_fbWidget.stVariantInput.nModesCount          := 0;
```

## Common VAR_INPUT / VAR_OUTPUT

```iecst
VAR_INPUT
    sDisplayName : T_IoT_NameString := 'Device Name';
    bSwitchDimm  : BOOL := FALSE;
    bOn          : BOOL := FALSE;
    bOff         : BOOL := FALSE;
    eUserGroup   : E_IoT_UserGroup := E_IoT_UserGroup.Standard;
END_VAR
VAR_OUTPUT
    bLight              : BOOL;
    nActualLevelPercent : UINT;
    fPower              : LREAL;
    stMeasurement       : ST_*_Measurement;
    eActiveColorMode    : E_IoT_LightType;
END_VAR
```
