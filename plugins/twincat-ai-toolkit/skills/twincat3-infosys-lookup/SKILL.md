---
name: twincat3-infosys-lookup
description: Fallback for Beckhoff TwinCAT3 type lookups via web when the offline MSHC search returns 0 results. Use ONLY after twincat3-infosys-mshc skill returned nothing. Searches InfoSys online via WebSearch + WebFetch.
---

# Online InfoSys Lookup (Fallback)

**Use ONLY when the offline MSHC search returned 0 results.** Always try `twincat_infosys_mshc_search` first.

## Workflow

### 1. WebSearch

```
Beckhoff InfoSys [TypeName] TwinCAT3
```

### 2. WebFetch

Fetch the InfoSys URL (prefer `/1033/` for English):

```
https://infosys.beckhoff.com/content/1033/[section]/[page_id].html
```

### 3. Extract and Present

From the page, extract: syntax declaration, inputs, outputs, methods, requirements. Present as clean ST block.

## Common Library Mapping

| Library | Section | Types |
|---------|---------|-------|
| Tc3_IotBase | tf6701_tc3_iot_communication_mqtt | FB_IotMqttClient, FB_IotMqttMessageQueue |
| Tc3_JsonXml | tf6760_tc3_json_xml | FB_JsonDynDomParser, FB_JsonSaxWriter |
| Tc2_ModbusSrv | tf6250_tc3_modbus_tcp | FB_MBReadInputRegs, FB_MBWriteRegs |
| Tc2_System | tcplclib_tc2_system | ST_LibVersion, GETCURTASKINDEX |
| Tc2_Standard | tcplclib_tc2_standard | TON, TOF, R_TRIG, F_TRIG |
| Tc3_IotBase (HTTP) | tf6760_tc3_iot_https_rest | FB_IotHttpClient, FB_IotHttpRequest |

## Tips

- Pick the latest TwinCAT version page if multiple exist
- Still fetch English `/1033/` even for German users (more complete)
- Cache results within the conversation -- do not re-fetch
