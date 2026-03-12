# MQTT Patterns (Tc3_IotBase)

## Complete MQTT Device FB Template

```iecst
FUNCTION_BLOCK FB_MqttDevice
VAR_INPUT
    sHostName    : T_MaxString := '192.168.1.100';
    nHostPort    : UINT        := 1883;
    sClientId    : T_MaxString := 'TwinCAT-01';
    sTopicPrefix : T_MaxString := 'devices/mydevice';
    bConnect     : BOOL        := TRUE;
END_VAR
VAR_OUTPUT
    bConnected      : BOOL;
    bError          : BOOL;
    hrErrorCode     : HRESULT;
    eConnectionState : ETcIotMqttClientState;
END_VAR
VAR
    _fbMqttClient : FB_IotMqttClient;
    _fbMsgQueue   : FB_IotMqttMessageQueue;
    _fbMessage    : FB_IotMqttMessage;
    _bSubscribed  : BOOL;
    _sTopic       : T_MaxString;
    _pPayload     : POINTER TO BYTE;
    _nPayloadSize : UDINT;
END_VAR
```

## Topic Routing Pattern

Route messages based on topic segments:

```iecst
IF _fbMsgQueue.nQueuedMessages > 0 THEN
    IF _fbMsgQueue.Dequeue(fbMessage := _fbMessage) THEN
        _fbMessage.GetTopic(
            pTopic    := ADR(_sTopic),
            nTopicSize := SIZEOF(_sTopic));

        // Route by topic suffix
        IF FIND(_sTopic, '/status') > 0 THEN
            ProcessStatus();
        ELSIF FIND(_sTopic, '/result') > 0 THEN
            ProcessResult();
        ELSIF FIND(_sTopic, '/events') > 0 THEN
            ProcessEvent();
        END_IF
    END_IF
END_IF
```

## Wildcard Subscriptions

```iecst
// Single-level wildcard: + matches one level
_fbMqttClient.Subscribe(sTopic := 'devices/+/status', eQoS := TcIotMqttQos.AtLeastOnceDelivery);

// Multi-level wildcard: # matches all remaining levels
_fbMqttClient.Subscribe(sTopic := 'devices/#', eQoS := TcIotMqttQos.AtLeastOnceDelivery);

// Specific device
_fbMqttClient.Subscribe(sTopic := 'devices/shelly-001/status', eQoS := TcIotMqttQos.AtLeastOnceDelivery);
```

## Publish with Dynamic JSON Payload

```iecst
// Build JSON
_fbJsonWriter.ResetDocument();
_fbJsonWriter.StartObject();
_fbJsonWriter.AddKeyString('command', 'set');
_fbJsonWriter.AddKeyNumber('value', nSetValue);
_fbJsonWriter.EndObject();

// Get length and publish
_nPayloadSize := _fbJsonWriter.GetDocumentLength();

IF _nPayloadSize > 0 THEN
    _pPayload := __NEW(BYTE, _nPayloadSize);

    IF _pPayload <> 0 THEN
        _fbJsonWriter.CopyDocument(_pPayload^, _nPayloadSize);

        _fbMqttClient.Publish(
            sTopic       := CONCAT(sTopicPrefix, '/command'),
            pPayload     := _pPayload,
            nPayloadSize := _nPayloadSize,
            eQoS         := TcIotMqttQos.AtLeastOnceDelivery,
            bRetain      := FALSE);

        __DELETE(_pPayload);
    END_IF
END_IF
```

## Reconnection Handling

```iecst
// Reset subscription flag on disconnect
IF _fbMqttClient.eConnectionState <> ETcIotMqttClientState.Connected THEN
    _bSubscribed := FALSE;
END_IF

// Subscribe on (re)connect
IF _fbMqttClient.eConnectionState = ETcIotMqttClientState.Connected
   AND NOT _bSubscribed
THEN
    _fbMqttClient.Subscribe(
        sTopic := CONCAT(sTopicPrefix, '/#'),
        eQoS   := TcIotMqttQos.AtLeastOnceDelivery);
    _bSubscribed := TRUE;
END_IF
```

## QoS Levels

| QoS | Enum | Guarantee |
|-----|------|-----------|
| 0 | `TcIotMqttQos.AtMostOnceDelivery` | Fire and forget |
| 1 | `TcIotMqttQos.AtLeastOnceDelivery` | Delivered at least once (may duplicate) |
| 2 | `TcIotMqttQos.ExactlyOnceDelivery` | Delivered exactly once (slowest) |

Use QoS 1 for most device communication. QoS 0 for telemetry/status where occasional loss is OK.

## TLS Configuration

```iecst
_fbMqttClient.stTLS.sCA              := 'c:\TwinCAT\3.1\Target\certs\ca.pem';
_fbMqttClient.stTLS.sCert            := 'c:\TwinCAT\3.1\Target\certs\client.pem';
_fbMqttClient.stTLS.sKeyFile         := 'c:\TwinCAT\3.1\Target\certs\client.key';
_fbMqttClient.stTLS.bNoServerCertCheck := FALSE;  // TRUE to skip verification
```

## Last Will and Testament

```iecst
_fbMqttClient.sTopicWill   := CONCAT(sTopicPrefix, '/status');
_fbMqttClient.sPayloadWill := '{"online": false}';
_fbMqttClient.eQosWill     := TcIotMqttQos.AtLeastOnceDelivery;
_fbMqttClient.bRetainWill  := TRUE;
```

## ETcIotMqttClientState Reference

| State | Meaning |
|-------|---------|
| `Idle` | Not connected, not trying |
| `Connecting` | Connection in progress |
| `Connected` | Connected and ready |
| `Disconnecting` | Disconnect in progress |
| `Error` | Error occurred (check hrErrorCode) |
