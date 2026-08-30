"""Tests for XML validator."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.xml_validator import validate_twincat_xml


VALID_POU = '''<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.0">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test
VAR
    x : INT;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[x := x + 1;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>'''


class TestValidPou:
    def test_no_issues(self):
        issues = validate_twincat_xml(VALID_POU, "test.TcPOU")
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) == 0


class TestGuidValidation:
    def test_invalid_guid_format(self):
        xml = VALID_POU.replace("{12345678-1234-1234-1234-123456789012}", "{invalid}")
        issues = validate_twincat_xml(xml, "test.TcPOU")
        guid_issues = [i for i in issues if i.rule == "guid_format"]
        assert len(guid_issues) > 0

    def test_duplicate_guid(self):
        xml = '''<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1" ProductVersion="3.1">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
    <Method Name="M1" Id="{12345678-1234-1234-1234-123456789012}">
      <Declaration><![CDATA[METHOD M1]]></Declaration>
      <Implementation><ST><![CDATA[]]></ST></Implementation>
    </Method>
  </POU>
</TcPlcObject>'''
        issues = validate_twincat_xml(xml, "test.TcPOU")
        dup_issues = [i for i in issues if i.rule == "guid_unique"]
        assert len(dup_issues) > 0


class TestStructureValidation:
    def test_missing_declaration(self):
        xml = '''<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1" ProductVersion="3.1">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>'''
        issues = validate_twincat_xml(xml, "test.TcPOU")
        struct_issues = [i for i in issues if i.rule == "pou_structure"]
        assert any("Declaration" in i.message for i in struct_issues)

    def test_missing_implementation(self):
        xml = '''<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1" ProductVersion="3.1">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>
  </POU>
</TcPlcObject>'''
        issues = validate_twincat_xml(xml, "test.TcPOU")
        struct_issues = [i for i in issues if i.rule == "pou_structure"]
        assert any("Implementation" in i.message for i in struct_issues)


class TestNameMatch:
    def test_mismatch_detected(self):
        xml = '''<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1" ProductVersion="3.1">
  <POU Name="FB_Wrong" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Correct]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>'''
        issues = validate_twincat_xml(xml, "test.TcPOU")
        name_issues = [i for i in issues if i.rule == "name_match"]
        assert len(name_issues) > 0
