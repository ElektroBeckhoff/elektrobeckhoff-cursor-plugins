import os
import zipfile
from pathlib import Path

ext_dir = Path(__file__).parent.resolve()
mcp_dir = (ext_dir / ".." / "mcp-servers" / "mcp-twincat").resolve()
vsix_path = ext_dir / "twincat-iecst.vsix"

# Extract metadata manifests if existing
content_types = b"""<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json" />
  <Default Extension=".vsixmanifest" ContentType="text/xml" />
  <Default Extension=".js" ContentType="application/javascript" />
  <Default Extension=".md" ContentType="text/markdown" />
  <Default Extension=".py" ContentType="text/plain" />
</Types>"""

vsix_manifest = b"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="twincat-iecst" Version="0.1.0" Publisher="ElektroBeckhoff" />
    <DisplayName>TwinCAT 3 Structured Text &amp; Tooling</DisplayName>
    <Description xml:space="preserve">TwinCAT 3 Structured Text language support, syntax highlighting, and LSP integration powered by twincat_core.</Description>
    <Categories>Programming Languages,Formatters,Linters</Categories>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
  </Assets>
</PackageManifest>"""

if vsix_path.exists():
    try:
        with zipfile.ZipFile(vsix_path, "r") as old_z:
            if "[Content_Types].xml" in old_z.namelist():
                content_types = old_z.read("[Content_Types].xml")
            if "extension.vsixmanifest" in old_z.namelist():
                vsix_manifest = old_z.read("extension.vsixmanifest")
    except Exception:
        pass

temp_vsix = ext_dir / "twincat-iecst.temp.vsix"

with zipfile.ZipFile(temp_vsix, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", content_types)
    z.writestr("extension.vsixmanifest", vsix_manifest)

    # Extension assets
    for rel in [
        "package.json",
        "dist/extension.js",
        "language-configuration.json",
        "README.md",
        "syntaxes/iecst.tmLanguage.json",
        "syntaxes/xml.iecst.codeblock.json",
        "themes/twincat-xae-dark.json",
        "themes/twincat-xae-light.json",
    ]:
        fpath = ext_dir / rel
        if fpath.exists():
            z.write(fpath, f"extension/{rel}")

    # Bundle server packages
    for pkg_name in ["twincat_core", "formatter", "infosys_mshc"]:
        pkg_dir = mcp_dir / pkg_name
        if pkg_dir.is_dir():
            for root, dirs, files in os.walk(pkg_dir):
                dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
                for f in files:
                    if not f.endswith(".pyc") and not f.endswith(".pyo"):
                        fp = Path(root) / f
                        rel = fp.relative_to(mcp_dir)
                        z.write(fp, f"extension/server/{rel.as_posix()}")

if vsix_path.exists():
    vsix_path.unlink()
temp_vsix.rename(vsix_path)

print(f"Successfully packaged {vsix_path} ({vsix_path.stat().st_size / 1024:.1f} KB)")
