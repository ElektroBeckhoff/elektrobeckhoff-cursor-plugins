"""Unit and integration tests for twincat_format and twincat_format_validate MCP tools."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import server as srv


class TestMcpFormatValidate:
    def test_format_validate_directory_with_multiple_files(self, tmp_path: Path):
        """Verify twincat_format_validate scans a directory with multiple files without timing out or deadlocking."""
        pou1 = tmp_path / "FB_One.TcPOU"
        pou1.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_One" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_One
VAR
    nVal : INT;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[nVal := 1;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        pou2 = tmp_path / "FB_Two.TcPOU"
        pou2.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Two" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Two
VAR
    bFlag : BOOL;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[bFlag := TRUE;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        pou3 = tmp_path / "FB_Three_InvalidGuid.TcPOU"
        pou3.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Three_InvalidGuid" Id="{invalid-guid-here}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Three_InvalidGuid
VAR
    fPower : REAL;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[fPower := 0.0;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        res_raw = srv.twincat_format_validate(path=str(tmp_path), recursive=True)
        res = json.loads(res_raw)

        assert res["total_files"] == 3
        assert res["success"] is False  # One file had invalid GUID
        assert len(res["issues"]) >= 1
        guid_issues = [i for i in res["issues"] if i["rule"] == "guid_format"]
        assert len(guid_issues) >= 1
        assert guid_issues[0]["file"] == "FB_Three_InvalidGuid.TcPOU"

    def test_format_directory_with_multiple_files(self, tmp_path: Path):
        """Verify twincat_format formats a directory with multiple files via ThreadPoolExecutor."""
        pou1 = tmp_path / "FB_Alpha.TcPOU"
        pou1.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Alpha" Id="{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Alpha
VAR
x:INT;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[x:=1;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        pou2 = tmp_path / "FB_Beta.TcPOU"
        pou2.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Beta" Id="{bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Beta
VAR
y:BOOL;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[y:=TRUE;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        res_raw = srv.twincat_format(path=str(tmp_path), recursive=True, dry_run=False)
        res = json.loads(res_raw)

        assert res["success"] is True
        assert res["total"] == 2
        assert res["errors"] == 0
        assert res["formatted"] == 2
