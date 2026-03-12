# Library & Types Prompts

## New Library

```
Erstelle eine neue TwinCAT3 Library: Tc3_[LIBNAME]

Zweck: [BESCHREIBUNG]
Benötigte Libraries: [z.B. Tc2_Standard, Tc3_IotBase, Tc2_ModbusSrv]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ und .cursor/skills/ nach allen relevanten Rules und Skills
für neue Libraries, Versioning, Naming, XML-Formate und .plcproj.
Lies und befolge sie vollständig bevor du Code generierst.

Generiere vollständige Ordnerstruktur mit allen nötigen Dateien:
Version-GVL, Param-GVL, Haupt-FB, Data-Struct, .plcproj.
GUIDs mit [guid]::NewGuid(). Version: 0.0.0.1.
```

---

## New Struct

```
Erstelle einen Struct: ST_[NAME]

Felder:
  [feldname] : [TYP] // [BESCHREIBUNG]
  [feldname] : [TYP] // [BESCHREIBUNG]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ nach den Rules für TcDUT-XML, Naming und Comments.
Lies und befolge sie bevor du Code generierst.

Generiere als valides TcDUT-XML mit GUID ([guid]::NewGuid()).
```

---

## New Enum

```
Erstelle ein Enum: E_[NAME]

Werte:
  [WERT1] = [BESCHREIBUNG]
  [WERT2] = [BESCHREIBUNG]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ und .cursor/skills/ nach den Rules für TcDUT-XML,
Naming und Attribute-Pragmas. Lies und befolge sie bevor du Code generierst.

Generiere als valides TcDUT-XML mit GUID ([guid]::NewGuid()).
```

---

## New GVL

```
Erstelle eine GVL: [Param_LibName / GVL_Domain]

Variablen:
  [name] : [TYP] := [WERT]; // [BESCHREIBUNG]
  [name] : [TYP] := [WERT]; // [BESCHREIBUNG]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ nach den Rules für TcGVL-XML und Naming.
Lies und befolge sie bevor du Code generierst.

Generiere als valides TcGVL-XML mit GUID ([guid]::NewGuid()).
```

---

## Register File in .plcproj

```
Registriere folgende Dateien in [PROJEKTNAME].plcproj:

Dateien:
  [relativer/pfad/zur/datei.TcPOU]
  [relativer/pfad/zur/datei.TcDUT]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ nach der Rule für .plcproj-Bearbeitung.
Lies und befolge sie bevor du Code generierst.

Prüfe ob Dateien bereits registriert sind.
```
