---
name: twincat3-infosys-lookup
description: Look up Beckhoff TwinCAT3 standard library types (FB_, ST_, E_, F_, I_) from InfoSys documentation via web search. Use when the user asks about a Beckhoff library type, when you need the exact signature of a standard Beckhoff FB/struct/enum/function, or when you are unsure about input/output parameters of Tc2_*/Tc3_* library types.
---

# TwinCAT3 InfoSys Lookup

Look up exact signatures, parameters, methods, and requirements for Beckhoff standard library types directly from InfoSys.

## When to Use

- User asks "what are the inputs of FB_IotMqttClient?"
- You need the exact VAR_INPUT/VAR_OUTPUT of a Beckhoff library FB
- You're unsure about parameter types, defaults, or string lengths
- You need to know which library to reference (Tc3_IotBase, Tc2_System, etc.)
- User references a Beckhoff type you don't have in your training data

## Lookup Workflow

### Step 1: Search Google for the InfoSys page

Use `WebSearch` with this pattern:

```
Beckhoff InfoSys [TypeName] TwinCAT3
```

Examples:
- `Beckhoff InfoSys FB_IotMqttClient TwinCAT3`
- `Beckhoff InfoSys ST_IotMqttWill TwinCAT3`
- `Beckhoff InfoSys FB_JsonDynDomParser TwinCAT3`
- `Beckhoff InfoSys FB_MBReadInputRegs TwinCAT3`
- `Beckhoff InfoSys E_IotMqttQos TwinCAT3`

The first result is almost always the correct InfoSys page.

### Step 2: Fetch the InfoSys page

Use `WebFetch` on the URL from Step 1. InfoSys URLs follow this pattern:

```
https://infosys.beckhoff.com/content/1033/[library_section]/[page_id].html
```

- `/1033/` = English documentation
- `/1031/` = German documentation (use English by default)

### Step 3: Extract the relevant information

From the fetched page, extract and present:

1. **Syntax** — the full `FUNCTION_BLOCK` / `TYPE` declaration with VAR_INPUT/VAR_OUTPUT
2. **Inputs** — name, type, default, description
3. **Outputs** — name, type, description
4. **Methods** — name, description (for FBs)
5. **Requirements** — TwinCAT version, target platform, PLC library to include

### Step 4: Format for the user

Present the result as a clean ST declaration block:

```iecst
// From InfoSys: https://infosys.beckhoff.com/...
FUNCTION_BLOCK FB_IotMqttClient
VAR_INPUT
    sClientId      : STRING(255);            // Unique client ID (auto-generated if empty)
    sHostName      : STRING(255) := '127.0.0.1'; // Broker address
    nHostPort      : UINT := 1883;           // Broker port
    sTopicPrefix   : STRING(255);            // Auto-prepended to all pub/sub topics
    nKeepAlive     : UINT := 60;             // [s] Watchdog interval
    sUserName      : STRING(255);            // Optional auth
    sUserPassword  : STRING(255);            // Optional auth
    stWill         : ST_IotMqttWill;         // Last will message
    stTLS          : ST_IotMqttTls;          // TLS configuration
    ipMessageQueue : I_IotMqttMessageQueue;  // Queue for received messages
END_VAR
VAR_OUTPUT
    bError           : BOOL;                 // Error flag
    hrErrorCode      : HRESULT;              // Error code
    eConnectionState : ETcIotMqttClientState; // Connection state enum
    bConnected       : BOOL;                 // TRUE when connected
END_VAR
// Library: Tc3_IotBase | Min TwinCAT: v3.1.4022.0
```

## Common Library Mapping

If you already know the library, you can search more specifically:

| Library | InfoSys Section | Common Types |
|---------|----------------|--------------|
| Tc3_IotBase | tf6701_tc3_iot_communication_mqtt | FB_IotMqttClient, FB_IotMqttMessageQueue |
| Tc3_JsonXml | tf6760_tc3_json_xml | FB_JsonDynDomParser, FB_JsonSaxWriter |
| Tc2_ModbusSrv | tf6250_tc3_modbus_tcp | FB_MBReadInputRegs, FB_MBWriteRegs |
| Tc2_System | tcplclib_tc2_system | ST_LibVersion, GETCURTASKINDEX |
| Tc2_Standard | tcplclib_tc2_standard | TON, TOF, R_TRIG, F_TRIG, CTU |
| Tc2_Utilities | tcplclib_tc2_utilities | FB_FormatString, FB_FileOpen |
| Tc3_Module | tcplclib_tc3_module | FB_TcMessage, TcEventSeverity |
| Tc3_IotBase (HTTP) | tf6760_tc3_iot_https_rest | FB_IotHttpClient, FB_IotHttpRequest |

## Tips

- If search returns multiple versions, pick the page from the latest TwinCAT version
- For methods of an FB, each method has its own InfoSys page — fetch those individually if needed
- If the user asks in German, still fetch the English `/1033/` page (more complete), but present your answer in German
- Cache mentally: if you already looked up a type in this conversation, don't re-fetch
