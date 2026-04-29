"""
Tests for the twincat_fup_migrate MCP tool wrapper in server.py.

Verifies parameter-to-argv mapping, JSON response format, and
error handling without requiring TcXaeShell or pywin32.
"""
import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import twincat_fup_migrate


MINIMAL_NWL_POU = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="TestProg" Id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}" SpecialFunc="None">
    <Declaration><![CDATA[PROGRAM TestProg
VAR
    bStart : BOOL;
    bOut   : BOOL;
END_VAR]]></Declaration>
    <Implementation>
      <NWL>
        <XmlArchive>
          <Data>
            <o xml:space="preserve" t="NWLImplementationObject">
              <v n="NetworkListComment"></v>
              <l2 n="NetworkList" cet="Network">
                <o>
                  <v n="ILActive">false</v>
                  <v n="FBDValid">false</v>
                  <v n="ILValid">false</v>
                  <l2 n="ExpressionList" cet="BoxTreeAssign">
                    <o>
                      <o n="OutputItems" t="OutputItemList">
                        <l2 n="OutputItems" cet="Operand">
                          <o><v n="Expression">"bOut"</v></o>
                        </l2>
                      </o>
                      <o n="Operand" t="Operand"><v n="Expression">"bStart"</v></o>
                    </o>
                  </l2>
                </o>
              </l2>
            </o>
          </Data>
        </XmlArchive>
      </NWL>
    </Implementation>
  </POU>
</TcPlcObject>
''')

MINIMAL_ST_POU = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="StProg" Id="{11111111-2222-3333-4444-555555555555}" SpecialFunc="None">
    <Declaration><![CDATA[PROGRAM StProg
VAR
    x : INT;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[x := x + 1;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>
''')


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestMcpToolResponseFormat:
    """Verify the MCP tool returns well-formed JSON with expected keys."""

    def test_dry_run_returns_json(self, tmp_dir):
        pou = _write(tmp_dir / "Test.TcPOU", MINIMAL_NWL_POU)
        raw = twincat_fup_migrate(input=str(pou), dry_run=True)
        result = json.loads(raw)
        assert "success" in result
        assert "exit_code" in result
        assert "output" in result
        assert isinstance(result["success"], bool)
        assert isinstance(result["exit_code"], int)

    def test_analyze_only_returns_json(self, tmp_dir):
        pou = _write(tmp_dir / "Test.TcPOU", MINIMAL_NWL_POU)
        raw = twincat_fup_migrate(input=str(pou), analyze_only=True)
        result = json.loads(raw)
        assert result["success"] is True
        assert result["exit_code"] == 0

    def test_nonexistent_input_fails(self):
        raw = twincat_fup_migrate(input="/nonexistent/path/Test.TcPOU", dry_run=True)
        result = json.loads(raw)
        assert result["success"] is False
        assert result["exit_code"] == 1


class TestMcpToolParameterMapping:
    """Verify that MCP tool parameters translate to correct migrator behavior."""

    def test_dry_run_no_output_files_written(self, tmp_dir):
        pou = _write(tmp_dir / "Test.TcPOU", MINIMAL_NWL_POU)
        twincat_fup_migrate(input=str(pou), dry_run=True, log=False, report=False)
        generated = list(tmp_dir.glob("*_ST_Generated*")) + list(tmp_dir.glob("*_fup_backup_*"))
        assert generated == []

    def test_analyze_only_no_output_files_written(self, tmp_dir):
        pou = _write(tmp_dir / "Test.TcPOU", MINIMAL_NWL_POU)
        twincat_fup_migrate(input=str(pou), analyze_only=True, log=False, report=False)
        generated = list(tmp_dir.glob("*_ST_Generated*")) + list(tmp_dir.glob("*_fup_backup_*"))
        assert generated == []

    def test_no_swap_creates_generated_file(self, tmp_dir):
        pou = _write(tmp_dir / "Test.TcPOU", MINIMAL_NWL_POU)
        raw = twincat_fup_migrate(
            input=str(pou), swap=False, log=False, report=False,
        )
        result = json.loads(raw)
        assert result["success"] is True
        generated = list(tmp_dir.glob("*_ST_Generated*"))
        assert len(generated) == 1

    def test_swap_mode_creates_backup(self, tmp_dir):
        pou = _write(tmp_dir / "Test.TcPOU", MINIMAL_NWL_POU)
        raw = twincat_fup_migrate(
            input=str(pou), log=False, report=False,
        )
        result = json.loads(raw)
        assert result["success"] is True
        backups = list(tmp_dir.glob("*_fup_backup_*"))
        assert len(backups) == 1

    def test_recursive_folder(self, tmp_dir):
        sub = tmp_dir / "sub"
        _write(sub / "A.TcPOU", MINIMAL_NWL_POU)
        _write(sub / "inner" / "B.TcPOU", MINIMAL_NWL_POU)
        raw = twincat_fup_migrate(
            input=str(sub), recursive=True, dry_run=True,
        )
        result = json.loads(raw)
        assert result["success"] is True

    def test_st_file_skipped(self, tmp_dir):
        pou = _write(tmp_dir / "StProg.TcPOU", MINIMAL_ST_POU)
        raw = twincat_fup_migrate(input=str(pou), dry_run=True)
        result = json.loads(raw)
        assert result["exit_code"] == 0

    def test_strict_mode(self, tmp_dir):
        pou = _write(tmp_dir / "Test.TcPOU", MINIMAL_NWL_POU)
        raw = twincat_fup_migrate(
            input=str(pou), strict=True, dry_run=True,
        )
        result = json.loads(raw)
        assert "success" in result
