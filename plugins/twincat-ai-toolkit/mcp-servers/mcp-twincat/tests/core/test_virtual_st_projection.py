"""Comprehensive tests for twincat_core.projection (Virtual ST & Source Mapping)."""
from pathlib import Path
import pytest

from twincat_core.projection import (
    SectionMapping,
    SourceMap,
    VirtualStDocument,
    project_to_virtual_st,
    sync_virtual_st_to_xml,
)
from twincat_core.xml.reader import read_tc_xml


SAMPLE_POU_XML = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Conveyor" Id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Conveyor
VAR_INPUT
    bStart : BOOL;
    fSpeed : REAL := 1.5;
END_VAR
VAR_OUTPUT
    bRunning : BOOL;
END_VAR
VAR
    _nCycles : UDINT := 0;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[IF bStart THEN
    bRunning := TRUE;
    _nCycles := _nCycles + 1;
ELSE
    bRunning := FALSE;
END_IF;
]]></ST>
    </Implementation>
    <Method Name="M_Stop" Id="{11111111-2222-3333-4444-555555555555}">
      <Declaration><![CDATA[METHOD PUBLIC M_Stop : BOOL
VAR_INPUT
    bEmergency : BOOL := FALSE;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[bRunning := FALSE;
M_Stop := TRUE;
]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>"""

SAMPLE_DUT_XML = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <DUT Name="E_MotorState" Id="{99999999-8888-7777-6666-555555555555}">
    <Declaration><![CDATA[{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_MotorState :
(
    Stopped := 0,
    Starting := 1,
    Running := 2,
    Faulted := 99
);
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>"""


class TestVirtualStProjection:
    """Test projecting XML files to Virtual ST and bidirectional source mapping."""

    def test_project_single_cdata_dut(self):
        vdoc = project_to_virtual_st(SAMPLE_DUT_XML)
        assert "TYPE E_MotorState :" in vdoc.virtual_st
        assert "Stopped := 0" in vdoc.virtual_st
        assert len(vdoc.source_map.sections) == 1

        sec = vdoc.source_map.sections[0]
        assert sec.label == "DUT: E_MotorState"
        assert sec.virt_start_line == 1

    def test_project_multi_section_pou(self):
        vdoc = project_to_virtual_st(SAMPLE_POU_XML)
        # Should contain all 4 CDATA sections: POU decl, POU impl, Method decl, Method impl
        assert len(vdoc.source_map.sections) == 4
        assert "FUNCTION_BLOCK FB_Conveyor" in vdoc.virtual_st
        assert "IF bStart THEN" in vdoc.virtual_st
        assert "METHOD PUBLIC M_Stop : BOOL" in vdoc.virtual_st
        assert "bRunning := FALSE;" in vdoc.virtual_st

        # Verify section markers are embedded
        assert "[twincat-section:pou_declaration:FB_Conveyor:0]" in vdoc.virtual_st
        assert "[twincat-section:pou_implementation:FB_Conveyor:1]" in vdoc.virtual_st
        assert "[twincat-section:method_declaration:M_Stop:2]" in vdoc.virtual_st
        assert "[twincat-section:method_implementation:M_Stop:3]" in vdoc.virtual_st

    def test_source_map_position_translation(self):
        vdoc = project_to_virtual_st(SAMPLE_POU_XML)

        # Map virtual line in POU declaration section to XML line
        sec0 = vdoc.source_map.sections[0]
        virt_line = sec0.virt_content_start_line  # Line of "FUNCTION_BLOCK FB_Conveyor"
        xml_line, xml_col = vdoc.source_map.virtual_to_xml_position(virt_line, 1)

        # Verify XML line points to declaration CDATA in raw XML
        xml_lines = SAMPLE_POU_XML.splitlines()
        assert "FUNCTION_BLOCK FB_Conveyor" in xml_lines[xml_line - 1] or "FUNCTION_BLOCK" in xml_lines[xml_line - 1] or "<Declaration>" in xml_lines[xml_line - 2]

        # Reverse map XML line back to virtual line
        back_virt_line, _ = vdoc.source_map.xml_to_virtual_position(xml_line, 1)
        assert back_virt_line == virt_line

    def test_bidirectional_sync_st_to_xml_pou_edit(self):
        vdoc = project_to_virtual_st(SAMPLE_POU_XML)

        # Modify something in the method implementation section
        edited_st = vdoc.virtual_st.replace("M_Stop := TRUE;", "M_Stop := TRUE;\n_nCycles := 0;")
        # And add a variable to the POU declaration
        edited_st = edited_st.replace("fSpeed : REAL := 1.5;", "fSpeed : REAL := 2.5;\n    bAlarm : BOOL := FALSE;")

        new_xml = vdoc.apply_virtual_st_changes(edited_st)

        # Verify XML structure and GUIDs are 100% preserved
        assert 'Id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}"' in new_xml
        assert 'Id="{11111111-2222-3333-4444-555555555555}"' in new_xml
        assert '<POU Name="FB_Conveyor"' in new_xml
        assert '<Method Name="M_Stop"' in new_xml

        # Verify edited ST appears inside the CDATA blocks
        assert "fSpeed : REAL := 2.5;" in new_xml
        assert "bAlarm : BOOL := FALSE;" in new_xml
        assert "_nCycles := 0;" in new_xml

    def test_bidirectional_sync_dut_edit(self):
        vdoc = project_to_virtual_st(SAMPLE_DUT_XML)
        edited_st = vdoc.virtual_st.replace("Faulted := 99", "Faulted := 99,\n    EStop := 100")

        new_xml = vdoc.apply_virtual_st_changes(edited_st)
        assert 'Id="{99999999-8888-7777-6666-555555555555}"' in new_xml
        assert "EStop := 100" in new_xml
        assert "<DUT Name=\"E_MotorState\"" in new_xml
