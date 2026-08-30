"""Tests for XML formatter."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.xml_formatter import (
    parse_twincat_xml,
    format_xml_structure,
    restore_cdata,
    sort_pou_children,
)


SAMPLE_POU = '''<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.0">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test
VAR
    x : INT;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[x := x + 1;]]></ST>
    </Implementation>
    <Method Name="DoWork" Id="{22345678-1234-1234-1234-123456789012}">
      <Declaration><![CDATA[METHOD DoWork
VAR_INPUT
END_VAR]]></Declaration>
      <Implementation>
        <ST><![CDATA[]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>'''


class TestParseTwincatXml:
    def test_parse_and_preserve_cdata(self):
        root, cdata_map = parse_twincat_xml(SAMPLE_POU)
        assert root is not None
        assert len(cdata_map) > 0

    def test_cdata_content_preserved(self):
        _, cdata_map = parse_twincat_xml(SAMPLE_POU)
        contents = list(cdata_map.values())
        has_fb_decl = any("FUNCTION_BLOCK" in c for c in contents)
        assert has_fb_decl


class TestFormatXmlStructure:
    def test_produces_valid_output(self):
        result, cmap = format_xml_structure(SAMPLE_POU)
        assert result.startswith("<?xml")
        assert "<TcPlcObject" in result
        assert "<POU" in result

    def test_attribute_ordering(self):
        result, _ = format_xml_structure(SAMPLE_POU)
        pou_line = [l for l in result.split("\n") if "<POU" in l][0]
        name_pos = pou_line.index("Name")
        id_pos = pou_line.index("Id")
        assert name_pos < id_pos

    def test_indentation(self):
        result, _ = format_xml_structure(SAMPLE_POU)
        lines = result.split("\n")
        pou_line = next(l for l in lines if "<POU" in l)
        assert pou_line.startswith("  ")


class TestRestoreCdata:
    def test_restores_content(self):
        result, cmap = format_xml_structure(SAMPLE_POU)
        restored = restore_cdata(result, cmap)
        assert "<![CDATA[" in restored
        assert "FUNCTION_BLOCK" in restored
        assert "__CDATA_" not in restored


class TestSortPouChildren:
    def test_declaration_before_implementation(self):
        xml = '''<POU Name="T" Id="{a}">
            <Implementation><ST><![CDATA[]]></ST></Implementation>
            <Declaration><![CDATA[VAR END_VAR]]></Declaration>
        </POU>'''
        result, _ = format_xml_structure(
            f'<?xml version="1.0" encoding="utf-8"?><TcPlcObject Version="1.1" ProductVersion="3.1">{xml}</TcPlcObject>',
            sort_elements=True,
        )
        decl_pos = result.index("Declaration")
        impl_pos = result.index("Implementation")
        assert decl_pos < impl_pos
