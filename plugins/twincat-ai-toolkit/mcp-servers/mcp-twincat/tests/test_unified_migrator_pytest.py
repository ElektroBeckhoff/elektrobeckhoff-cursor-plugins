"""
Tests for twincat_unified_migrator.py

Covers: type-detection routing, mixed-folder batch, error isolation,
shared backup directory, combined report, CLI parameters, single-file
mode, empty folder, and MCP wrapper (twincat_migrate).

Run with:  pytest tests/test_unified_migrator_pytest.py -v
"""

import json
import os
import textwrap
from pathlib import Path

import pytest

import twincat_unified_migrator as U
from twincat_migrator_base import (
    MigrationConfig, MigrationLogger, MigrationReport, load_file,
)
from server import twincat_migrate


# ===================================================================
# Synthetic TcPOU XML fixtures
# ===================================================================

MINIMAL_NWL_POU = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="FbdProg" Id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}" SpecialFunc="None">
    <Declaration><![CDATA[PROGRAM FbdProg
VAR
    bOut : BOOL;
END_VAR
]]></Declaration>
    <Implementation>
      <NWL>
        <XmlArchive>
          <Data>
            <o xml:space="preserve" t="NWLImplementationObject">
              <v n="NetworkListComment">""</v>
              <v n="DefaultViewMode">"Fbd"</v>
              <l2 n="NetworkList" cet="Network">
                <o>
                  <v n="ILActive">false</v>
                  <v n="FBDValid">false</v>
                  <v n="ILValid">false</v>
                  <l2 n="ILLines" />
                  <v n="Comment">""</v>
                  <v n="Title">""</v>
                  <v n="Label">""</v>
                  <v n="OutCommented">false</v>
                  <l2 n="NetworkItems" cet="BoxTreeAssign">
                    <o>
                      <o n="OutputItems" t="OutputItemList">
                        <l2 n="OutputItems" cet="Operand">
                          <o>
                            <v n="Operand">"bOut"</v>
                            <v n="Type">"BOOL"</v>
                            <v n="Comment">""</v>
                            <v n="SymbolComment">""</v>
                            <v n="Address">""</v>
                            <o n="Flags" t="Flags"><v n="Flags">0</v><v n="Fixed">false</v><v n="Extensible">false</v></o>
                            <v n="LValue">true</v>
                            <v n="Boolean">false</v>
                            <v n="IsInstance">false</v>
                            <v n="Id">1L</v>
                          </o>
                        </l2>
                      </o>
                      <o n="Operand" t="Operand">
                        <v n="Operand">"TRUE"</v>
                        <v n="Type">"BOOL"</v>
                        <v n="Comment">""</v>
                        <v n="SymbolComment">""</v>
                        <v n="Address">""</v>
                        <o n="Flags" t="Flags"><v n="Flags">0</v><v n="Fixed">false</v><v n="Extensible">false</v></o>
                        <v n="LValue">false</v>
                        <v n="Boolean">false</v>
                        <v n="IsInstance">false</v>
                        <v n="Id">2L</v>
                      </o>
                    </o>
                  </l2>
                </o>
              </l2>
              <v n="BranchCounter">0</v>
              <v n="ValidIds">true</v>
            </o>
          </Data>
          <TypeList>
            <Type n="Boolean">System.Boolean</Type>
            <Type n="BoxTreeAssign">{9873c309-1f09-4ebf-9078-42d8057ef11b}</Type>
            <Type n="BoxTreeOperand">{9de7f100-1b87-424c-a62e-45b0cfc85ed2}</Type>
            <Type n="Flags">{668066f2-6069-46b3-8962-8db8d13d7db2}</Type>
            <Type n="Int32">System.Int32</Type>
            <Type n="Int64">System.Int64</Type>
            <Type n="Network">{d9a99d73-b633-47db-b876-a752acb25871}</Type>
            <Type n="NWLImplementationObject">{25e509de-33d4-4447-93f8-c9e4ea381c8b}</Type>
            <Type n="Operand">{c9b2f165-48a2-4a45-8326-3952d8a3d708}</Type>
            <Type n="Operator">{bffb3c53-f105-4e85-aba2-e30df579d75f}</Type>
            <Type n="OutputItemList">{f40d3e09-c02c-4522-a88c-dac23558cfc4}</Type>
            <Type n="ParamList">{71496971-9e0c-4677-a832-b9583b571130}</Type>
            <Type n="String">System.String</Type>
          </TypeList>
        </XmlArchive>
      </NWL>
    </Implementation>
  </POU>
</TcPlcObject>''')


MINIMAL_CFC_POU = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="CfcProg" Id="{22222222-3333-4444-5555-666666666666}" SpecialFunc="None">
    <Declaration><![CDATA[PROGRAM CfcProg
VAR
    bOut : BOOL;
END_VAR
]]></Declaration>
    <Implementation>
      <CFC>
        <XmlArchive>
          <Data>
            <o xml:space="preserve" t="CFCImplementationObject">
              <o n="Items" t="CFCItemList">
                <l2 n="InnerList">
                  <o t="CFCInputElement">
                    <o n="Output" t="CFCOutputPin">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Negated">false</v>
                      <v n="Id">1L</v>
                    </o>
                    <o n="Text" t="CFCText">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Text">"TRUE"</v>
                      <v n="Modifiable">true</v>
                      <v n="Id">101L</v>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="Id">10L</v>
                  </o>
                  <o t="CFCOutputElement">
                    <o n="Input" t="CFCInputPinWithSetReset">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Negated">false</v>
                      <v n="SetReset" t="SetReset">None</v>
                      <v n="Id">2L</v>
                    </o>
                    <o n="Text" t="CFCText">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Text">"bOut"</v>
                      <v n="Modifiable">true</v>
                      <v n="Id">102L</v>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="Id">20L</v>
                  </o>
                </l2>
              </o>
            </o>
          </Data>
        </XmlArchive>
      </CFC>
    </Implementation>
  </POU>
</TcPlcObject>''')


MINIMAL_ST_POU = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="AlreadyST" Id="{11111111-2222-3333-4444-555555555555}" SpecialFunc="None">
    <Declaration><![CDATA[PROGRAM AlreadyST
VAR
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>''')


MINIMAL_GVL = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <GVL Name="GVL_Test" Id="{33333333-4444-5555-6666-777777777777}">
    <Declaration><![CDATA[VAR_GLOBAL
    bGlobal : BOOL;
END_VAR
]]></Declaration>
  </GVL>
</TcPlcObject>''')


BROKEN_XML = '<?xml version="1.0" encoding="utf-8"?>\n<TcPlcObject><POU Name="Broken"'


# ===================================================================
# Helpers
# ===================================================================

def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ===================================================================
# Test: Type-detection routing
# ===================================================================

class TestRouting:
    """process_file routes NWL -> FBD, CFC -> CFC, ST -> skip."""

    def test_nwl_routes_to_fbd(self, tmp_path):
        p = tmp_path / "Fbd.TcPOU"
        _write(p, MINIMAL_NWL_POU)
        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        cfg = MigrationConfig(input_path=str(tmp_path))
        result = U.process_file(p, cfg, mlog, report)
        assert result is True
        fbd_entries = [r for r in report.file_reports if r["impl_type_before"] == "NWL"]
        assert len(fbd_entries) == 1

    def test_cfc_routes_to_cfc(self, tmp_path):
        p = tmp_path / "Cfc.TcPOU"
        _write(p, MINIMAL_CFC_POU)
        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        cfg = MigrationConfig(input_path=str(tmp_path))
        result = U.process_file(p, cfg, mlog, report)
        assert result is True

    def test_st_skipped(self, tmp_path):
        p = tmp_path / "St.TcPOU"
        _write(p, MINIMAL_ST_POU)
        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        cfg = MigrationConfig(input_path=str(tmp_path))
        result = U.process_file(p, cfg, mlog, report)
        assert result is True
        assert len(report.file_reports) == 0

    def test_gvl_skipped(self, tmp_path):
        p = tmp_path / "Vars.TcGVL"
        _write(p, MINIMAL_GVL)
        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        cfg = MigrationConfig(input_path=str(tmp_path))
        result = U.process_file(p, cfg, mlog, report)
        assert result is True
        assert len(report.file_reports) == 0


# ===================================================================
# Test: Mixed folder batch
# ===================================================================

class TestMixedFolder:
    """Folder with NWL + CFC + ST + GVL -> only NWL/CFC converted."""

    def test_mixed_folder_dry_run(self, tmp_path):
        d = tmp_path / "Proj"
        _write(d / "Fbd.TcPOU", MINIMAL_NWL_POU)
        _write(d / "Cfc.TcPOU", MINIMAL_CFC_POU)
        _write(d / "St.TcPOU", MINIMAL_ST_POU)
        _write(d / "Vars.TcGVL", MINIMAL_GVL)

        code = U.main(["--input", str(d), "--dry-run", "--no-log", "--no-report"])
        assert code == 0

    def test_mixed_folder_force(self, tmp_path):
        d = tmp_path / "Proj"
        _write(d / "Fbd.TcPOU", MINIMAL_NWL_POU)
        _write(d / "Cfc.TcPOU", MINIMAL_CFC_POU)
        _write(d / "St.TcPOU", MINIMAL_ST_POU)

        code = U.main(["--input", str(d), "--force", "--no-backup",
                        "--no-log", "--no-report"])
        assert code == 0

    def test_mixed_folder_recursive(self, tmp_path):
        d = tmp_path / "Proj"
        sub = d / "POUs"
        _write(sub / "Fbd.TcPOU", MINIMAL_NWL_POU)
        _write(sub / "Cfc.TcPOU", MINIMAL_CFC_POU)

        code = U.main(["--input", str(d), "--recursive", "--dry-run",
                        "--no-log", "--no-report"])
        assert code == 0


# ===================================================================
# Test: Error isolation
# ===================================================================

class TestErrorIsolation:
    """A broken file must not abort the entire batch."""

    def test_broken_file_does_not_abort_batch(self, tmp_path):
        d = tmp_path / "Proj"
        _write(d / "Good.TcPOU", MINIMAL_NWL_POU)
        _write(d / "Bad.TcPOU", BROKEN_XML)

        code = U.main(["--input", str(d), "--dry-run", "--no-log", "--no-report"])
        assert code == 1

    def test_broken_file_reported_as_error(self, tmp_path):
        p = tmp_path / "Bad.TcPOU"
        _write(p, BROKEN_XML)
        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        cfg = MigrationConfig(input_path=str(tmp_path))
        result = U.process_file(p, cfg, mlog, report)
        assert result is False
        assert len(report.file_reports) == 1
        assert report.file_reports[0]["errors"]


# ===================================================================
# Test: Shared backup directory
# ===================================================================

class TestSharedBackup:
    """Force + backup creates a single shared backup directory."""

    def test_force_backup_creates_single_dir(self, tmp_path):
        d = tmp_path / "Proj"
        _write(d / "Fbd.TcPOU", MINIMAL_NWL_POU)
        _write(d / "Cfc.TcPOU", MINIMAL_CFC_POU)

        code = U.main(["--input", str(d), "--force", "--no-log", "--no-report"])
        assert code == 0

        backup_dirs = [p for p in tmp_path.iterdir()
                       if p.is_dir() and "backup" in p.name.lower()]
        assert len(backup_dirs) == 1


# ===================================================================
# Test: Report completeness
# ===================================================================

class TestReport:
    """Report entries must contain correct impl_type_before."""

    def test_report_has_correct_impl_types(self, tmp_path):
        d = tmp_path / "Proj"
        _write(d / "Fbd.TcPOU", MINIMAL_NWL_POU)
        _write(d / "Cfc.TcPOU", MINIMAL_CFC_POU)

        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        cfg = MigrationConfig(input_path=str(d), dry_run=True)

        from twincat_migrator_base import collect_input_files
        files = collect_input_files(cfg)
        for f in files:
            U.process_file(f, cfg, mlog, report)

        impl_types = {r["impl_type_before"] for r in report.file_reports}
        assert "NWL" in impl_types or "CFC" in impl_types


# ===================================================================
# Test: CLI parameters
# ===================================================================

class TestCLI:
    """CLI argument forwarding."""

    def test_verify_only_single_nwl(self, tmp_path):
        p = tmp_path / "Fbd.TcPOU"
        _write(p, MINIMAL_NWL_POU)
        code = U.main(["--input", str(p), "--dry-run", "--no-log", "--no-report"])
        assert code == 0

    def test_analyze_only(self, tmp_path):
        p = tmp_path / "Fbd.TcPOU"
        _write(p, MINIMAL_NWL_POU)
        code = U.main(["--input", str(p), "--analyze-only", "--no-log", "--no-report"])
        assert code == 0

    def test_force_no_backup(self, tmp_path):
        d = tmp_path / "Proj"
        _write(d / "Fbd.TcPOU", MINIMAL_NWL_POU)
        code = U.main(["--input", str(d), "--force", "--no-backup",
                        "--no-log", "--no-report"])
        assert code == 0
        backup_dirs = [p for p in tmp_path.iterdir()
                       if p.is_dir() and "backup" in p.name.lower()]
        assert len(backup_dirs) == 0

    def test_empty_folder(self, tmp_path):
        d = tmp_path / "Empty"
        d.mkdir()
        code = U.main(["--input", str(d), "--no-log", "--no-report"])
        assert code == 1

    def test_nonexistent_path(self):
        code = U.main(["--input", "nonexistent_xyz_path",
                        "--no-log", "--no-report"])
        assert code == 1


# ===================================================================
# Test: Single file mode
# ===================================================================

class TestSingleFile:
    """Single NWL or CFC file processing."""

    def test_single_nwl_file(self, tmp_path):
        p = tmp_path / "Fbd.TcPOU"
        _write(p, MINIMAL_NWL_POU)
        code = U.main(["--input", str(p), "--dry-run", "--no-log", "--no-report"])
        assert code == 0

    def test_single_cfc_file(self, tmp_path):
        p = tmp_path / "Cfc.TcPOU"
        _write(p, MINIMAL_CFC_POU)
        code = U.main(["--input", str(p), "--dry-run", "--no-log", "--no-report"])
        assert code == 0

    def test_single_st_file(self, tmp_path):
        p = tmp_path / "St.TcPOU"
        _write(p, MINIMAL_ST_POU)
        code = U.main(["--input", str(p), "--dry-run", "--no-log", "--no-report"])
        assert code == 0


# ===================================================================
# Test: MCP wrapper
# ===================================================================

class TestMcpWrapper:
    """twincat_migrate MCP tool wrapper."""

    def test_returns_valid_json(self, tmp_path):
        p = tmp_path / "Fbd.TcPOU"
        _write(p, MINIMAL_NWL_POU)
        raw = twincat_migrate(input=str(p), dry_run=True, log=False, report=False)
        result = json.loads(raw)
        assert "success" in result
        assert "exit_code" in result
        assert "output" in result
        assert isinstance(result["success"], bool)

    def test_nwl_success(self, tmp_path):
        p = tmp_path / "Fbd.TcPOU"
        _write(p, MINIMAL_NWL_POU)
        raw = twincat_migrate(input=str(p), dry_run=True, log=False, report=False)
        result = json.loads(raw)
        assert result["success"] is True

    def test_nonexistent_input_fails(self):
        raw = twincat_migrate(input="nonexistent_xyz_path", log=False, report=False)
        result = json.loads(raw)
        assert result["success"] is False

    def test_mixed_folder_via_mcp(self, tmp_path):
        d = tmp_path / "Proj"
        _write(d / "Fbd.TcPOU", MINIMAL_NWL_POU)
        _write(d / "Cfc.TcPOU", MINIMAL_CFC_POU)
        _write(d / "St.TcPOU", MINIMAL_ST_POU)
        raw = twincat_migrate(input=str(d), dry_run=True, log=False, report=False)
        result = json.loads(raw)
        assert result["success"] is True

    def test_force_dry_run_via_mcp(self, tmp_path):
        d = tmp_path / "Proj"
        _write(d / "Fbd.TcPOU", MINIMAL_NWL_POU)
        raw = twincat_migrate(input=str(d), force=True, dry_run=True,
                              log=False, report=False)
        result = json.loads(raw)
        assert result["success"] is True
