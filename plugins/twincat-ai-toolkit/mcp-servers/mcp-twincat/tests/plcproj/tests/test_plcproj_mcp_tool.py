"""
Tests for the twincat_plcproj_verify / twincat_plcproj_sync MCP tool
wrappers in server.py.

Verifies parameter-to-argv mapping, JSON response format, and error
handling without requiring TcXaeShell or pywin32.
"""
import json
import os
import textwrap
from pathlib import Path

import pytest

from server import twincat_plcproj_verify, twincat_plcproj_sync


MINIMAL_PLCPROJ = (
    '<?xml version="1.0" encoding="utf-8"?>\r\n'
    '<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">\r\n'
    '  <PropertyGroup>\r\n'
    '    <Name>TestLib</Name>\r\n'
    '    <ProjectVersion>1.0.0.0</ProjectVersion>\r\n'
    '  </PropertyGroup>\r\n'
    '  <ItemGroup>\r\n'
    '    <Compile Include="POUs\\FB_Main.TcPOU">\r\n'
    '      <SubType>Code</SubType>\r\n'
    '    </Compile>\r\n'
    '  </ItemGroup>\r\n'
    '  <ItemGroup>\r\n'
    '    <Folder Include="POUs" />\r\n'
    '  </ItemGroup>\r\n'
    '</Project>\r\n'
)

MINIMAL_TCPOU = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <TcPlcObject Version="1.1.0.1">
      <POU Name="FB_Main" Id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}">
        <Declaration><![CDATA[FUNCTION_BLOCK FB_Main]]></Declaration>
        <Implementation>
          <ST><![CDATA[;]]></ST>
        </Implementation>
      </POU>
    </TcPlcObject>
""")


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


def _write(path: Path, content: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _make_project(tmp_dir: Path) -> Path:
    proj = tmp_dir / "TestLib.plcproj"
    _write(proj, MINIMAL_PLCPROJ)
    _write(tmp_dir / "POUs" / "FB_Main.TcPOU", MINIMAL_TCPOU)
    return proj


# ===================================================================
# TestMcpToolResponseFormat
# ===================================================================

class TestMcpToolResponseFormat:
    def test_verify_returns_json(self, tmp_dir):
        _make_project(tmp_dir)
        raw = twincat_plcproj_verify(input=str(tmp_dir))
        result = json.loads(raw)
        assert "success" in result
        assert "exit_code" in result
        assert "output" in result
        assert isinstance(result["success"], bool)

    def test_sync_returns_json(self, tmp_dir):
        _make_project(tmp_dir)
        raw = twincat_plcproj_sync(input=str(tmp_dir), dry_run=True, force=True)
        result = json.loads(raw)
        assert "success" in result
        assert "exit_code" in result
        assert isinstance(result["success"], bool)

    def test_nonexistent_input_fails(self):
        raw = twincat_plcproj_verify(input="nonexistent_xyz_path")
        result = json.loads(raw)
        assert result["success"] is False
        assert result["exit_code"] != 0


# ===================================================================
# TestMcpToolParameterMapping
# ===================================================================

class TestMcpToolParameterMapping:
    def test_verify_ok(self, tmp_dir):
        _make_project(tmp_dir)
        raw = twincat_plcproj_verify(input=str(tmp_dir))
        result = json.loads(raw)
        assert result["success"] is True

    def test_verify_drift_detected(self, tmp_dir):
        _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")
        raw = twincat_plcproj_verify(input=str(tmp_dir))
        result = json.loads(raw)
        assert result["success"] is False

    def test_sync_force_writes(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")
        raw = twincat_plcproj_sync(input=str(tmp_dir), force=True)
        result = json.loads(raw)
        assert result["success"] is True
        content = proj.read_text(encoding="utf-8")
        assert "FB_New.TcPOU" in content

    def test_sync_dry_run_no_write(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")
        orig = proj.read_text(encoding="utf-8")
        raw = twincat_plcproj_sync(input=str(tmp_dir), force=True, dry_run=True)
        result = json.loads(raw)
        assert result["success"] is True
        assert proj.read_text(encoding="utf-8") == orig

    def test_sync_no_force_drift_fails(self, tmp_dir):
        _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")
        raw = twincat_plcproj_sync(input=str(tmp_dir))
        result = json.loads(raw)
        assert result["success"] is False

    def test_sync_backup_created(self, tmp_dir):
        _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")
        twincat_plcproj_sync(input=str(tmp_dir), force=True, backup=True)
        baks = list(tmp_dir.glob("*.plcproj.bak"))
        assert len(baks) == 1

    def test_sync_no_backup(self, tmp_dir):
        _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")
        twincat_plcproj_sync(input=str(tmp_dir), force=True, backup=False)
        baks = list(tmp_dir.glob("*.plcproj.bak"))
        assert len(baks) == 0

    def test_sync_ensure_guids(self, tmp_dir):
        proj = _make_project(tmp_dir)
        no_id = '<TcPlcObject><POU Name="FB_Main"></POU></TcPlcObject>'
        _write(tmp_dir / "POUs" / "FB_Main.TcPOU", no_id)

        raw = twincat_plcproj_sync(
            input=str(tmp_dir), force=True, ensure_object_guids=True,
        )
        result = json.loads(raw)
        assert result["success"] is True
        updated = (tmp_dir / "POUs" / "FB_Main.TcPOU").read_text()
        assert 'Id="{' in updated

    def test_verify_skip_folder_sync(self, tmp_dir):
        _make_project(tmp_dir)
        (tmp_dir / "NewDir").mkdir()
        raw = twincat_plcproj_verify(input=str(tmp_dir), skip_folder_sync=True)
        result = json.loads(raw)
        assert result["success"] is True
