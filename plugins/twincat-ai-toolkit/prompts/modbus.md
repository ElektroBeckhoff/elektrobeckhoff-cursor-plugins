# Modbus Prompts

## New Modbus TCP Device

```
Erstelle eine Modbus TCP Integration für: [GERÄTENAME]

Register Map (aus Datenblatt):
[ADDR] x[COUNT] [TYPE] = [BESCHREIBUNG]
[ADDR] x[COUNT] [TYPE] = [BESCHREIBUNG]
...

IP: [192.168.1.x], Unit ID: [1], Read Interval: [T#5S]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ und .cursor/skills/ nach allen relevanten Rules und Skills
für Modbus TCP, Naming, Formatting, Comments und XML-Formate.
Lies und befolge sie vollständig bevor du Code generierst.

Generiere alle nötigen Dateien: Data-Struct, Control-Struct, Helper-Functions,
Device-FB mit State Machine, .plcproj-Registrierung. GUIDs mit [guid]::NewGuid().
```

---

## New Modbus RTU Device

```
Erstelle eine Modbus RTU Integration für: [GERÄTENAME]

Register Map (aus Datenblatt):
[ADDR] x[COUNT] [TYPE] = [BESCHREIBUNG]
[ADDR] x[COUNT] [TYPE] = [BESCHREIBUNG]
...

Unit ID: [1], Baud: [9600], Hardware: [KL6x22B / PcCOM]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ und .cursor/skills/ nach allen relevanten Rules und Skills
für Modbus RTU, Naming, Formatting, Comments und XML-Formate.
Lies und befolge sie vollständig bevor du Code generierst.

Generiere alle nötigen Dateien: Data-Struct, Control-Struct, BYTE-Helper-Functions,
Device-FB mit State Machine + FIFO-Buffer, MAIN-Beispiel, .plcproj-Registrierung.
GUIDs mit [guid]::NewGuid().
```

---

## Add Write to Existing Modbus FB

```
Ergänze Write-Funktionalität in FB_[GERÄTENAME].

Write-Register:
[ADDR] [TYPE] = [BESCHREIBUNG]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ und .cursor/skills/ nach den Modbus-Rules für
Dual State Machine, Write Change Detection und Signed Write Values.
Lies und befolge sie bevor du Code generierst.

Ergänze: Control-Struct, Change Detection, Write State Machine, bWriteEnable.
```
