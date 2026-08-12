# .plcproj — Examples

Principles: `rules/twincat3-plcproj.mdc`. Read when registering files, folders, or library references.

## Register a new file

```xml
<Compile Include="POUs\FB_NewDevice.TcPOU">
  <SubType>Code</SubType>
</Compile>

<Compile Include="DUTs\ST_NewDevice_Data.TcDUT">
  <SubType>Code</SubType>
</Compile>

<Compile Include="GVLs\GVL_NewDomain.TcGVL">
  <SubType>Code</SubType>
</Compile>
```

## Register a new folder

```xml
<Folder Include="POUs\NewSubfolder" />
```

## Placeholder library reference

```xml
<PlaceholderReference Include="Tc3_JsonXml">
  <DefaultResolution>Tc3_JsonXml, * (Beckhoff Automation GmbH)</DefaultResolution>
  <Namespace>Tc3_JsonXml</Namespace>
</PlaceholderReference>
```
