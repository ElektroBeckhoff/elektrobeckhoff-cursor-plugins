# IoT Communication Prompts

## New MQTT Function Block

```
Erstelle einen MQTT Function Block für: [NAME / GERÄT]

Broker: [IP:PORT]
Subscribe Topics: [TOPIC1, TOPIC2, ...]
Publish Topics: [TOPIC1, TOPIC2, ...]
Payload Format: [JSON / Plain String]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ und .cursor/skills/ nach allen relevanten Rules und Skills
für MQTT, Naming, Formatting, Comments, JSON und XML-Formate.
Lies und befolge sie vollständig bevor du Code generierst.

Generiere alle nötigen Dateien: Device-FB mit MQTT Client + Message Queue,
Subscribe-on-Connect, Reconnection, Receive mit dynamischer Payload-Allokation,
Publish, Topic-Routing, Data-Struct, .plcproj-Registrierung.
GUIDs mit [guid]::NewGuid().
```

---

## New HTTP REST Function Block

```
Erstelle einen HTTP REST Client für: [NAME / API]

Host: [HOSTNAME:PORT]
Endpoints:
  [GET/POST] [/api/endpoint] = [BESCHREIBUNG]
  [GET/POST] [/api/endpoint] = [BESCHREIBUNG]
Auth: [API-Key / Bearer Token / None]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ und .cursor/skills/ nach allen relevanten Rules und Skills
für HTTP, Naming, Formatting, Comments, JSON und XML-Formate.
Lies und befolge sie vollständig bevor du Code generierst.

Generiere alle nötigen Dateien: Client-FB mit Execute + Send-Methoden,
Error-Mapping-Function, Param-Struct, GVL, Properties, Data-Structs,
.plcproj-Registrierung. GUIDs mit [guid]::NewGuid().
```

---

## Parse JSON (MQTT Payload / HTTP Response)

```
Ergänze JSON-Parsing in FB_[NAME] für [MQTT Payload / HTTP Response].

Felder:
  [feldname] : [TYP] = [BESCHREIBUNG]
  [feldname] : [TYP] = [BESCHREIBUNG]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ und .cursor/skills/ nach den relevanten Rules und Skills
für JSON-Parsing und Naming. Lies und befolge sie bevor du Code generierst.

Erstelle Data-Struct und Parse-Logik mit dynamischer Speicher-Allokation.
```

---

## Build JSON (Publish / HTTP Body)

```
Erstelle JSON-Payload in FB_[NAME] für [MQTT Publish / HTTP POST].

Felder:
  [feldname] : [TYP] = [BESCHREIBUNG]
  [feldname] : [TYP] = [BESCHREIBUNG]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ und .cursor/skills/ nach den relevanten Rules und Skills
für JSON-Writing und Naming. Lies und befolge sie bevor du Code generierst.
```
