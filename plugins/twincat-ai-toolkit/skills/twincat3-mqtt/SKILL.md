---
name: twincat3-mqtt
description: MQTT communication in TwinCAT3 using FB_IotMqttClient from Tc3_IotBase. Publish/subscribe, message queues, topic routing, reconnection, QoS, TLS, Last Will. Use when implementing MQTT communication, IoT device control, or broker-based messaging in TwinCAT3.
---

# MQTT Communication (Tc3_IotBase)

> **Mandatory rules:** See `twincat3-mqtt.mdc` for connection, subscribe-on-connect, payload allocation, and reconnection rules.

## Quick Start

```
Task Progress:
- [ ] Step 1: Add Tc3_IotBase library reference
- [ ] Step 2: Declare MQTT client, message queue, and message FBs
- [ ] Step 3: Configure connection (host, port, client ID, credentials)
- [ ] Step 4: Implement subscribe-on-connect with reconnection handling
- [ ] Step 5: Implement message receive with dynamic payload allocation
- [ ] Step 6: Implement publish (string or dynamic JSON)
- [ ] Step 7: Add topic routing for incoming messages
```

## Required Library

```xml
<PlaceholderReference Include="Tc3_IotBase">
  <DefaultResolution>Tc3_IotBase, * (Beckhoff Automation GmbH)</DefaultResolution>
  <Namespace>Tc3_IotBase</Namespace>
</PlaceholderReference>
```

## Core FBs

| FB | Purpose |
|----|---------|
| `FB_IotMqttClient` | MQTT client (connect, publish, subscribe) |
| `FB_IotMqttMessageQueue` | Receive queue for incoming messages |
| `FB_IotMqttMessage` | Single received message (topic + payload) |

## Step 2: Declaration

```iecst
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

## Step 3: Connection Setup

```iecst
_fbMqttClient.sHostName       := '192.168.1.100';
_fbMqttClient.nHostPort       := 1883;
_fbMqttClient.sClientId       := 'TwinCAT-CX01';
_fbMqttClient.sUserName       := '';
_fbMqttClient.sPassword       := '';
_fbMqttClient.stTLS.bNoServerCertCheck := TRUE;
_fbMqttClient.ipMessageQueue  := _fbMsgQueue;

_fbMqttClient.Execute(bConnect := TRUE);
```

## Step 4: Subscribe with Reconnection

```iecst
// Reset on disconnect
IF _fbMqttClient.eConnectionState <> ETcIotMqttClientState.Connected THEN
    _bSubscribed := FALSE;
END_IF

// Subscribe on (re)connect
IF _fbMqttClient.eConnectionState = ETcIotMqttClientState.Connected
   AND NOT _bSubscribed
THEN
    _fbMqttClient.Subscribe(
        sTopic := 'device/+/status',
        eQoS   := TcIotMqttQos.AtLeastOnceDelivery);
    _bSubscribed := TRUE;
END_IF
```

## Step 5: Receive Messages

```iecst
IF _fbMsgQueue.nQueuedMessages > 0 THEN
    IF _fbMsgQueue.Dequeue(fbMessage := _fbMessage) THEN
        _fbMessage.GetTopic(pTopic := ADR(_sTopic), nTopicSize := SIZEOF(_sTopic));

        _nPayloadSize := _fbMessage.nPayloadSize + 1;
        _pPayload     := __NEW(BYTE, _nPayloadSize);

        IF _pPayload <> 0 THEN
            _fbMessage.GetPayload(
                pPayload            := _pPayload,
                nPayloadSize        := _nPayloadSize,
                bSetNullTermination := TRUE);

            // Parse JSON, route by topic, etc.

            __DELETE(_pPayload);
        END_IF
    END_IF
END_IF
```

## Step 6: Publish

### String Payload

```iecst
_fbMqttClient.Publish(
    sTopic       := 'device/cx01/command',
    pPayload     := ADR(sPayload),
    nPayloadSize := LEN2(ADR(sPayload)),
    eQoS         := TcIotMqttQos.AtLeastOnceDelivery,
    bRetain      := FALSE);
```

### Dynamic JSON Payload

See [mqtt-patterns.md](mqtt-patterns.md) for the complete `FB_JsonSaxWriter` + `__NEW`/`__DELETE` pattern.

## Step 7: Topic Routing

```iecst
IF FIND(_sTopic, '/status') > 0 THEN
    ProcessStatus();
ELSIF FIND(_sTopic, '/result') > 0 THEN
    ProcessResult();
ELSIF FIND(_sTopic, '/events') > 0 THEN
    ProcessEvent();
END_IF
```

## Advanced Patterns

See [mqtt-patterns.md](mqtt-patterns.md) for:
- Complete FB template with all VAR declarations
- Dynamic JSON publish with `FB_JsonSaxWriter`
- Wildcard subscriptions (`+`, `#`)
- QoS level selection guide
- TLS certificate configuration
- Last Will and Testament setup
- `ETcIotMqttClientState` reference
