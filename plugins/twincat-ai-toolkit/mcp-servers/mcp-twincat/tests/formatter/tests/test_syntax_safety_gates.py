"""Tests for Formatter Pre-Format and Post-Format Syntax Safety Gates."""
from __future__ import annotations

from pathlib import Path
from formatter.config import FormatterConfig
from formatter.file_processor import process_file


class TestFormatterSyntaxSafetyGates:
    def test_pre_format_gate_aborts_on_broken_source_syntax(self, tmp_path: Path):
        broken_pou = tmp_path / "FB_Broken.TcPOU"
        content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Broken" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Broken
VAR
    x : INT;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
IF x > 0 THEN
    x := x + 1;
(* MISSING END_IF -> fatal syntax error *)
]]></Implementation>
  </POU>
</TcPlcObject>"""
        broken_pou.write_text(content, encoding="utf-8")

        cfg = FormatterConfig()
        result = process_file(str(broken_pou), cfg, dry_run=False)

        assert result.success is False
        assert result.changed is False
        assert any("Pre-format syntax error" in err for err in result.errors)
        # Verify file content is completely untouched
        assert broken_pou.read_text(encoding="utf-8") == content

    def test_pre_format_gate_allows_valid_syntax(self, tmp_path: Path):
        clean_pou = tmp_path / "FB_Clean.TcPOU"
        content = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Clean" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Clean
VAR
    x : INT;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
IF x > 0 THEN
    x := x + 1;
END_IF;
]]></Implementation>
  </POU>
</TcPlcObject>"""
        clean_pou.write_text(content, encoding="utf-8")

        cfg = FormatterConfig()
        result = process_file(str(clean_pou), cfg, dry_run=False)

        assert result.success is True
        assert len(result.errors) == 0
