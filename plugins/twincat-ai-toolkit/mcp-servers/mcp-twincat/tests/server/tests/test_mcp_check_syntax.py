"""Unit and integration tests for the twincat_check_syntax MCP tool."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import server as srv


class TestMcpCheckSyntax:
    def test_check_syntax_single_clean_file(self, tmp_path: Path):
        pou_file = tmp_path / "FB_Clean.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Clean" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Clean
VAR_INPUT
    bEnable : BOOL;
    nSpeed  : INT;
END_VAR
VAR_OUTPUT
    bRunning : BOOL;
END_VAR
VAR
    _nCounter : INT;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
IF bEnable THEN
    bRunning := TRUE;
    _nCounter := _nCounter + 1;
ELSE
    bRunning := FALSE;
END_IF;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        res_raw = srv.twincat_check_syntax(path=str(pou_file))
        res = json.loads(res_raw)

        assert res["success"] is True
        assert res["total_files"] == 1
        assert res["error_count"] == 0
        assert res["warning_count"] == 0
        assert len(res["diagnostics"]) == 0

    def test_check_syntax_single_file_with_declaration_error(self, tmp_path: Path):
        pou_file = tmp_path / "F_NoReturnType.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="F_NoReturnType" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[FUNCTION F_NoReturnType
VAR_INPUT
    nIn : INT;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
F_NoReturnType := nIn * 2;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        res_raw = srv.twincat_check_syntax(path=str(pou_file))
        res = json.loads(res_raw)

        assert res["success"] is False
        assert res["error_count"] >= 1
        decl_errors = [d for d in res["diagnostics"] if d["code"] == "TC-DECL-001"]
        assert len(decl_errors) == 1
        assert "explicit return type" in decl_errors[0]["message"]

    def test_check_syntax_single_file_with_type_mismatch_error(self, tmp_path: Path):
        pou_file = tmp_path / "FB_Mismatch.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Mismatch" Id="{33333333-3333-3333-3333-333333333333}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Mismatch
VAR
    sName : STRING;
    nVal  : INT;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
sName := nVal;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        res_raw = srv.twincat_check_syntax(path=str(pou_file))
        res = json.loads(res_raw)

        assert res["success"] is False
        assert res["error_count"] == 1
        assert res["diagnostics"][0]["code"] == "TC-SEM-006"
        assert "Cannot convert" in res["diagnostics"][0]["message"]

    def test_check_syntax_warnings_filtering(self, tmp_path: Path):
        pou_file = tmp_path / "FB_Warn.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Warn" Id="{44444444-4444-4444-4444-444444444444}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Warn
VAR
    nInt  : INT;
    nDint : DINT;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
nInt := nDint;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        # 1. include_warnings=True (default)
        res_with_warn = json.loads(srv.twincat_check_syntax(path=str(pou_file), include_warnings=True))
        assert res_with_warn["success"] is True  # No errors -> success is True
        assert res_with_warn["warning_count"] == 1
        assert len(res_with_warn["diagnostics"]) == 1
        assert res_with_warn["diagnostics"][0]["code"] == "TC-SEM-007"
        assert res_with_warn["diagnostics"][0]["severity"] == "warning"

        # 2. include_warnings=False
        res_no_warn = json.loads(srv.twincat_check_syntax(path=str(pou_file), include_warnings=False))
        assert res_no_warn["success"] is True
        assert res_no_warn["warning_count"] == 1
        assert len(res_no_warn["diagnostics"]) == 0

    def test_check_syntax_directory_multi_files(self, tmp_path: Path):
        f1 = tmp_path / "FB_One.TcPOU"
        f1.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_One" Id="{55555555-5555-5555-5555-555555555551}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_One
VAR
    x : INT;
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        f2 = tmp_path / "ST_Two.TcDUT"
        f2.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_Two" Id="{55555555-5555-5555-5555-555555555552}">
    <Declaration><![CDATA[TYPE ST_Two :
STRUCT
    fSpeed : LREAL;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        res = json.loads(srv.twincat_check_syntax(path=str(tmp_path)))
        assert res["success"] is True
        assert res["total_files"] == 2
        assert res["error_count"] == 0

    def test_check_syntax_nonexistent_path(self):
        res = json.loads(srv.twincat_check_syntax(path="c:/invalid/path/that/does/not/exist"))
        assert res["success"] is False
        assert "does not exist" in res["error"]
