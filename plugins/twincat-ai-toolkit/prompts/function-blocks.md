# Function Block Prompts

## New Function Block

```
Erstelle einen Function Block: FB_[NAME]

Zweck: [BESCHREIBUNG]
Inputs: [LISTE]
Outputs: [LISTE]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ und .cursor/skills/ nach allen relevanten Rules für
TwinCAT3 Core, Naming, Formatting, Comments und XML-Formate.
Lies und befolge sie vollständig bevor du Code generierst.

Generiere FB als valides TcPOU-XML mit GUID ([guid]::NewGuid()).
```

---

## New Step-Based State Machine

```
Ergänze eine Step-basierte State Machine in FB_[NAME].

Zweck: [BESCHREIBUNG]
Schritte: [LISTE DER OPERATIONEN]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ nach den Rules für State Machines und Step-Pair Pattern.
Lies und befolge sie bevor du Code generierst.

Verwende CASE _nStep OF mit den Standard-Steps (Idle, Operations, Success, Error, Delay).
```

---

## Add Method to FB

```
Ergänze Methode [METHODENNAME] in FB_[NAME].

Zweck: [BESCHREIBUNG]
Parameter: [LISTE]
Rückgabe: [TYP]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ nach den Rules für Naming, XML-Formate und Comments.
Lies und befolge sie bevor du Code generierst.

Generiere Method-XML mit eigener GUID ([guid]::NewGuid()).
```

---

## Add Property to FB

```
Ergänze Property [PROPERTYNAME] in FB_[NAME].

Typ: [TYP]
Zugriff: [GET / SET / beides]
Zweck: [BESCHREIBUNG]

--- Ab hier nichts ändern ---
Suche in .cursor/rules/ nach den Rules für Naming, OOP und XML-Formate.
Lies und befolge sie bevor du Code generierst.

Generiere Property-XML mit 3 GUIDs ([guid]::NewGuid()).
```
