---
name: twincat3-new-library
description: Create a new TwinCAT3 PLC library project from scratch with correct folder structure, solution files, and initial POUs/DUTs/GVLs. Use when creating a new library, starting a new TwinCAT3 project, or setting up a PLC project structure.
---

# Create New TwinCAT3 Library

## Quick Start

```
Task Progress:
- [ ] Step 1: Create folder structure
- [ ] Step 2: Generate GUIDs for all files
- [ ] Step 3: Create initial files (DUTs, POUs, GVLs)
- [ ] Step 4: Register files in .plcproj
- [ ] Step 5: Verify build
```

## Step 1: Folder Structure

TwinCAT3 libraries use a nested structure:

```
Tc3_[LibName]/
  Tc3_[LibName]/                    # Solution level
    Tc3_[LibName].sln
    Tc3_[LibName]/                  # TwinCAT project level
      Tc3_[LibName].tsproj
      Tc3_[LibName]/                # PLC project level
        Tc3_[LibName].plcproj
        DUTs/
          Enums/                    # E_*.TcDUT
          Structs/                  # ST_*.TcDUT
        POUs/
          Helper/                   # Internal helpers
        GVLs/
        Version/
          Global_Version.TcGVL
        _Libraries/                 # Referenced .compiled-library files
  Samples_/                         # Optional sample projects
  docs/
  Versions/                         # Released .library / .compiled-library
  README.md
```

## Step 2: Generate GUIDs

Every .TcPOU, .TcDUT, .TcGVL file needs a unique GUID. Methods inside FBs need their own GUIDs too.

PowerShell:
```powershell
[guid]::NewGuid()
# Generate multiple at once:
1..10 | ForEach-Object { [guid]::NewGuid() }
```

## Step 3: Minimum Files

| File | Purpose |
|------|---------|
| `Version/Global_Version.TcGVL` | Library version (ST_LibVersion from Tc2_System) |
| `GVLs/Param_[LibName].TcGVL` | Configuration constants |
| `POUs/FB_[LibName]_[Main].TcPOU` | Main function block |
| `DUTs/Structs/ST_[LibName]_Data.TcDUT` | Primary data structure |
| `DUTs/Enums/E_[LibName]_State.TcDUT` | State enum (optional) |

See [templates.md](templates.md) for ready-to-use XML templates.

## Step 4: Register in .plcproj

Every file must be registered in the `.plcproj` MSBuild XML:

```xml
<ItemGroup>
  <Compile Include="POUs\FB_[LibName]_[Main].TcPOU">
    <SubType>Code</SubType>
  </Compile>
</ItemGroup>
```

New folders need a `<Folder Include="..." />` entry.

## Step 5: Common Beckhoff Library References

Add as `<PlaceholderReference>` in .plcproj depending on communication needs:

| Library | When to Use |
|---------|-------------|
| `Tc2_Standard` | Always (timers, counters, triggers) |
| `Tc2_System` | String ops, time, ST_LibVersion |
| `Tc2_Utilities` | File ops, CSV, advanced string handling |
| `Tc3_IotBase` | MQTT (FB_IotMqttClient), HTTP (FB_IotHttpClient) |
| `Tc3_JsonXml` | JSON parse (FB_JsonDynDomParser), JSON write (FB_JsonSaxWriter) |
| `Tc2_ModbusSrv` | Modbus TCP/RTU (FB_MBReadInputRegs, FB_MBWriteRegs) |
| `Tc2_TcpIp` | Raw TCP/UDP sockets |
| `Tc2_EtherCAT` | EtherCAT fieldbus access |

