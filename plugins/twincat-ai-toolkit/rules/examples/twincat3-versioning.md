# TwinCAT3 Versioning — Examples

Principles: `rules/twincat3-versioning.mdc`. Apply workflow: skills
`twincat3-release` / `twincat3-new-version`.

## plcproj `<ProjectVersion>`

```xml
<ProjectVersion>0.0.0.1</ProjectVersion>
```

## Global_Version GVL (`ST_LibVersion` from `Tc2_System`)

```iecst
{attribute 'TcGenerated'}
VAR_GLOBAL CONSTANT
    stLibVersion : ST_LibVersion := (
        iMajor    := 0,
        iMinor    := 0,
        iBuild    := 0,
        iRevision := 1,
        sVersion  := '0.0.0.1'
    );
END_VAR
```

`.plcproj` `<ProjectVersion>` and `stLibVersion` **must match**.

## Versions folder layout

```
Versions/
  0.0.0.1/
    <LibName>-0.0.0.1.library
    <LibName>-0.0.0.1.compiled-library
    changelog-0.0.0.1.md
  1.0.0.0/
    <LibName>-1.0.0.0.library
    <LibName>-1.0.0.0.compiled-library
    changelog-1.0.0.0.md
```

On **release** / **new-version**, always ship both `.library` and `.compiled-library`.
