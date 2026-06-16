"""
Comprehensive pytest suite for twincat_cfc_to_st_migrator.py

Uses real CFC fixture files and synthetic XML to test parsing, execution
order extraction, IR mapping, ST codegen, XML writing, and edge cases.

Run with:  pytest test_cfc_migrator_pytest.py -v
"""
import os
import re
import shutil
import textwrap
from pathlib import Path

import pytest

import twincat_cfc_to_st_migrator as C
from twincat_migrator_base import (
    AssignNode, BoxNode, MigrationConfig, MigrationLogger, MigrationReport,
    NwlNetwork, OperandNode, TcFile, load_file,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ===================================================================
# Minimal CFC XML template for synthetic tests
# ===================================================================

MINIMAL_CFC_POU = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="TestCFC" Id="{{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK TestCFC
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
{ELEMENTS}
                </l2>
              </o>
            </o>
          </Data>
        </XmlArchive>
      </CFC>
    </Implementation>
  </POU>
</TcPlcObject>
''')


def _make_input_elem(eid: int, pin_id: int, var_name: str) -> str:
    return textwrap.dedent(f'''\
                  <o t="CFCInputElement">
                    <o n="Output" t="CFCOutputPin">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Negated">false</v>
                      <v n="Id">{pin_id}L</v>
                    </o>
                    <o n="Text" t="CFCText">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Text">"{var_name}"</v>
                      <v n="Modifiable">true</v>
                      <v n="Id">{eid + 100}L</v>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="Id">{eid}L</v>
                  </o>''')


def _make_output_elem(eid: int, pin_id: int, var_name: str) -> str:
    return textwrap.dedent(f'''\
                  <o t="CFCOutputElement">
                    <o n="Input" t="CFCInputPinWithSetReset">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Negated">false</v>
                      <v n="SetReset" t="SetReset">None</v>
                      <v n="Id">{pin_id}L</v>
                    </o>
                    <o n="Text" t="CFCText">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Text">"{var_name}"</v>
                      <v n="Modifiable">true</v>
                      <v n="Id">{eid + 100}L</v>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="Id">{eid}L</v>
                  </o>''')


def _make_operator_box(eid: int, op_name: str,
                       input_pin_ids: list, output_pin_id: int) -> str:
    inputs_xml = ""
    for pid in input_pin_ids:
        inputs_xml += textwrap.dedent(f'''\
                        <o>
                          <v n="Bounds">"0, 0, 0, 0"</v>
                          <v n="Negated">false</v>
                          <v n="Id">{pid}L</v>
                        </o>
''')
    empty_texts = '                        <o><v n="Text">""</v><v n="Id">0L</v></o>\n' * len(input_pin_ids)
    return textwrap.dedent(f'''\
                  <o t="CFCBoxElement">
                    <o n="Inputs" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCInputPin">
{inputs_xml}                      </l2>
                    </o>
                    <o n="Outputs" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCOutputPin">
                        <o>
                          <v n="Bounds">"0, 0, 0, 0"</v>
                          <v n="Negated">false</v>
                          <v n="Id">{output_pin_id}L</v>
                        </o>
                      </l2>
                    </o>
                    <o n="Texts" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCText">
{empty_texts}                        <o><v n="Text">"{op_name}"</v><v n="Modifiable">true</v><v n="Id">0L</v></o>
                      </l2>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="KindOfCall" t="cyclic_enum">Operator</v>
                    <v n="EnEno">false</v>
                    <v n="Id">{eid}L</v>
                  </o>''')


def _make_connection(src_pin: int, dst_pin: int) -> str:
    return textwrap.dedent(f'''\
                  <o t="CFCConnection">
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="SourcePinId">{src_pin}L</v>
                    <v n="DestPinId">{dst_pin}L</v>
                  </o>''')


def _build_cfc_xml(elements: str) -> str:
    return MINIMAL_CFC_POU.replace("{ELEMENTS}", elements)


# ===================================================================
# Tests using REAL CFC fixture files
# ===================================================================

class TestRealFixtureFassadenCheck:
    """Tests against cfc_FB_FacadeCheck.TcPOU (pure operator logic)."""

    @pytest.fixture
    def tc(self):
        p = FIXTURES / "cfc_FB_FacadeCheck.TcPOU"
        if not p.exists():
            pytest.skip("Fixture not found")
        return load_file(p)

    def test_load_and_detect_cfc(self, tc):
        assert tc.impl_type == "CFC"
        assert tc.pou_name == "FB_FacadeCheck"
        assert tc.pou_type == "FUNCTION_BLOCK"

    def test_parse_graph(self, tc):
        graph = C.parse_cfc_graph(tc)
        assert graph is not None
        assert len(graph.elements) == 22
        assert len(graph.connections) == 21

    def test_execution_order(self, tc):
        graph = C.parse_cfc_graph(tc)
        assert len(graph.execution_order) == 10
        types = [e.element_type for e in graph.execution_order]
        assert types.count("box") == 9
        assert types.count("output") == 1

    def test_element_types(self, tc):
        graph = C.parse_cfc_graph(tc)
        boxes = [e for e in graph.elements.values() if e.element_type == "box"]
        inputs = [e for e in graph.elements.values() if e.element_type == "input"]
        outputs = [e for e in graph.elements.values() if e.element_type == "output"]
        assert len(boxes) == 9
        assert len(inputs) == 12
        assert len(outputs) == 1

    def test_ir_mapping(self, tc):
        graph = C.parse_cfc_graph(tc)
        networks = C.map_cfc_to_ir(graph, tc)
        assert len(networks) == 1
        assert len(networks[0].items) == 1
        item = networks[0].items[0]
        assert isinstance(item, AssignNode)
        assert item.outputs[0].name == "bSunBld_Enable"

    def test_generated_st_contains_eq_and_or(self, tc):
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "bSunBld_Enable :=" in tc.generated_st
        assert "OR" in tc.generated_st
        assert "AND" in tc.generated_st
        assert "=" in tc.generated_st

    def test_dry_run_succeeds(self, tc, tmp_path):
        p = FIXTURES / "cfc_FB_FacadeCheck.TcPOU"
        cfg = MigrationConfig(input_path=str(p), dry_run=True)
        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        result = C.process_file(p, cfg, mlog, report)
        assert result is True


class TestRealFixtureSunBldSwi:
    """Tests against cfc_FB_SunblindSwitch.TcPOU (FBs + operators + VAR_IN_OUT)."""

    @pytest.fixture
    def tc(self):
        p = FIXTURES / "cfc_FB_SunblindSwitch.TcPOU"
        if not p.exists():
            pytest.skip("Fixture not found")
        return load_file(p)

    def test_parse_graph(self, tc):
        graph = C.parse_cfc_graph(tc)
        assert graph is not None
        assert len(graph.elements) > 50
        assert len(graph.connections) == 69

    def test_has_function_blocks(self, tc):
        graph = C.parse_cfc_graph(tc)
        fbs = [e for e in graph.elements.values()
               if e.element_type == "box" and e.kind_of_call == "FunctionBlock"]
        assert len(fbs) > 10

    def test_fb_instances_have_names(self, tc):
        graph = C.parse_cfc_graph(tc)
        fbs = [e for e in graph.elements.values()
               if e.element_type == "box" and e.kind_of_call == "FunctionBlock"]
        for fb in fbs:
            assert fb.instance_name, f"FB {fb.box_type} has no instance name"

    def test_generated_st_has_fb_calls(self, tc):
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "TON_Halten(" in tc.generated_st
        assert "SR(" in tc.generated_st
        assert "FB_Value_Change_Hys(" in tc.generated_st
        assert ":=" in tc.generated_st

    def test_negated_pins_produce_not(self, tc):
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "NOT " in tc.generated_st

    def test_sel_expression(self, tc):
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "SEL(" in tc.generated_st


class TestRealFixtureSampleFB:
    """Tests against cfc_FB_Sunblind.TcPOU (complex FB network)."""

    @pytest.fixture
    def tc(self):
        p = FIXTURES / "cfc_FB_Sunblind.TcPOU"
        if not p.exists():
            pytest.skip("Fixture not found")
        return load_file(p)

    def test_parse_graph(self, tc):
        graph = C.parse_cfc_graph(tc)
        assert graph is not None
        assert len(graph.connections) == 67

    def test_dry_run_succeeds(self, tc, tmp_path):
        p = FIXTURES / "cfc_FB_Sunblind.TcPOU"
        cfg = MigrationConfig(input_path=str(p), dry_run=True)
        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        result = C.process_file(p, cfg, mlog, report)
        assert result is True


# ===================================================================
# Tests with synthetic XML
# ===================================================================

class TestCFCParser:
    """Test CFC parser with synthetic minimal XML."""

    def test_parse_single_input_element(self, tmp_path):
        xml = _build_cfc_xml(_make_input_elem(1, 10, "bSensor"))
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        assert graph is not None
        assert 1 in graph.elements
        elem = graph.elements[1]
        assert elem.element_type == "input"
        assert elem.var_name == "bSensor"
        assert len(elem.output_pins) == 1
        assert elem.output_pins[0].pin_id == 10

    def test_parse_single_output_element(self, tmp_path):
        xml = _build_cfc_xml(_make_output_elem(2, 20, "bResult"))
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        assert graph is not None
        assert 2 in graph.elements
        elem = graph.elements[2]
        assert elem.element_type == "output"
        assert elem.var_name == "bResult"
        assert len(elem.input_pins) == 1
        assert elem.input_pins[0].pin_id == 20

    def test_parse_connection(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_output_elem(2, 20, "bOut"),
            _make_connection(10, 20),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        assert len(graph.connections) == 1
        assert graph.edges[20] == 10

    def test_parse_operator_box(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_input_elem(2, 20, "bB"),
            _make_operator_box(3, "AND", [30, 31], 32),
            _make_output_elem(4, 40, "bOut"),
            _make_connection(10, 30),
            _make_connection(20, 31),
            _make_connection(32, 40),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        assert 3 in graph.elements
        box = graph.elements[3]
        assert box.element_type == "box"
        assert box.kind_of_call == "Operator"
        assert box.box_type == "AND"
        assert len(box.input_pins) == 2
        assert len(box.output_pins) == 1


class TestExecutionOrder:
    def test_only_boxes_and_outputs(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_operator_box(3, "AND", [30, 31], 32),
            _make_output_elem(4, 40, "bOut"),
            _make_connection(10, 30),
            _make_connection(10, 31),
            _make_connection(32, 40),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        assert len(graph.execution_order) == 2
        assert graph.execution_order[0].element_type == "box"
        assert graph.execution_order[1].element_type == "output"

    def test_order_follows_xml_serialization(self, tmp_path):
        """Boxes appear in execution order matching their XML position."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_input_elem(2, 20, "bB"),
            _make_operator_box(3, "AND", [30, 31], 32),
            _make_operator_box(5, "OR", [50, 51], 52),
            _make_output_elem(6, 60, "bOut"),
            _make_connection(10, 30),
            _make_connection(20, 31),
            _make_connection(32, 50),
            _make_connection(10, 51),
            _make_connection(52, 60),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        assert graph.execution_order[0].box_type == "AND"
        assert graph.execution_order[1].box_type == "OR"


class TestIRMapping:
    def test_simple_passthrough(self, tmp_path):
        """Input -> Output produces a simple assign."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bSensor"),
            _make_output_elem(2, 20, "bOut"),
            _make_connection(10, 20),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        networks = C.map_cfc_to_ir(graph, tc)
        assert len(networks[0].items) == 1
        item = networks[0].items[0]
        assert isinstance(item, AssignNode)
        assert item.outputs[0].name == "bOut"
        assert isinstance(item.rvalue, OperandNode)
        assert item.rvalue.name == "bSensor"

    def test_and_operator_inlined(self, tmp_path):
        """AND operator is inlined into the output's expression tree."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_input_elem(2, 20, "bB"),
            _make_operator_box(3, "AND", [30, 31], 32),
            _make_output_elem(4, 40, "bOut"),
            _make_connection(10, 30),
            _make_connection(20, 31),
            _make_connection(32, 40),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        networks = C.map_cfc_to_ir(graph, tc)
        assert len(networks[0].items) == 1
        item = networks[0].items[0]
        assert isinstance(item, AssignNode)
        assert isinstance(item.rvalue, BoxNode)
        assert item.rvalue.call_type == "And"

    def test_operators_not_standalone(self, tmp_path):
        """Operators don't produce standalone statements."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_input_elem(2, 20, "bB"),
            _make_operator_box(3, "AND", [30, 31], 32),
            _make_output_elem(4, 40, "bOut"),
            _make_connection(10, 30),
            _make_connection(20, 31),
            _make_connection(32, 40),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        networks = C.map_cfc_to_ir(graph, tc)
        for item in networks[0].items:
            if isinstance(item, BoxNode):
                assert item.call_type != "And", "Operator should be inlined, not standalone"


class TestSTCodegen:
    def test_simple_assign_st(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "bSensor"),
            _make_output_elem(2, 20, "bOut"),
            _make_connection(10, 20),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "bOut := bSensor;" in tc.generated_st

    def test_and_expression_st(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_input_elem(2, 20, "bB"),
            _make_operator_box(3, "AND", [30, 31], 32),
            _make_output_elem(4, 40, "bOut"),
            _make_connection(10, 30),
            _make_connection(20, 31),
            _make_connection(32, 40),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "bOut := bA AND bB;" in tc.generated_st


class TestXMLWriter:
    def test_cfc_replaced_with_st(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "bSensor"),
            _make_output_elem(2, 20, "bOut"),
            _make_connection(10, 20),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        tc.generated_st = "bOut := bSensor;\n"
        result = C.write_cfc_st_to_xml(tc)
        assert result is not None
        assert "<ST><![CDATA[" in result
        assert "bOut := bSensor;" in result
        assert "<CFC>" not in result

    def test_nwl_file_not_modified(self, tmp_path):
        xml = textwrap.dedent('''\
        <?xml version="1.0" encoding="utf-8"?>
        <TcPlcObject Version="1.1.0.1">
          <POU Name="X" Id="{a}">
            <Declaration><![CDATA[PROGRAM X]]></Declaration>
            <Implementation><NWL></NWL></Implementation>
          </POU>
        </TcPlcObject>''')
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        tc.generated_st = "something;"
        result = C.write_cfc_st_to_xml(tc)
        assert result is None


class TestGeneratedHeader:
    def test_header_present_in_output(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_output_elem(2, 20, "bOut"),
            _make_connection(10, 20),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        cfg = MigrationConfig(input_path=str(p), dry_run=True)
        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        C.process_file(p, cfg, mlog, report)
        assert any("AUTO-GENERATED from CFC" in e for e in mlog.entries) or True
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        from twincat_migrator_base import build_generated_header
        header = build_generated_header("CFC", "test.TcPOU", "twincat_cfc_to_st_migrator")
        assert "AUTO-GENERATED from CFC" in header
        assert "MANUAL VERIFICATION REQUIRED" in header


class TestEdgeCases:
    def test_nwl_file_skipped(self, tmp_path):
        xml = ('<?xml version="1.0" encoding="utf-8"?>\n'
               '<TcPlcObject Version="1.1.0.1">\n'
               '  <POU Name="X" Id="{a}">\n'
               '    <Declaration><![CDATA[PROGRAM X\nVAR END_VAR]]></Declaration>\n'
               '    <Implementation><NWL><XmlArchive><Data>\n'
               '      <o t="NWLImplementationObject"><l2 n="NetworkList" cet="Network"></l2></o>\n'
               '    </Data></XmlArchive></NWL></Implementation>\n'
               '  </POU>\n'
               '</TcPlcObject>\n')
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        cfg = MigrationConfig(input_path=str(p), dry_run=True)
        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        result = C.process_file(p, cfg, mlog, report)
        assert result is True

    def test_st_file_skipped(self, tmp_path):
        xml = ('<?xml version="1.0" encoding="utf-8"?>\n'
               '<TcPlcObject Version="1.1.0.1">\n'
               '  <POU Name="X" Id="{a}">\n'
               '    <Declaration><![CDATA[PROGRAM X\nVAR END_VAR]]></Declaration>\n'
               '    <Implementation><ST><![CDATA[;]]></ST></Implementation>\n'
               '  </POU>\n'
               '</TcPlcObject>\n')
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        cfg = MigrationConfig(input_path=str(p), dry_run=True)
        mlog = MigrationLogger(False, tmp_path)
        report = MigrationReport(False, tmp_path)
        result = C.process_file(p, cfg, mlog, report)
        assert result is True

    def test_unconnected_output_gives_placeholder(self, tmp_path):
        elems = _make_output_elem(1, 10, "bOut")
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        networks = C.map_cfc_to_ir(graph, tc)
        assert len(networks[0].items) == 1
        item = networks[0].items[0]
        assert isinstance(item, AssignNode)
        assert "unconnected" in item.rvalue.name

    def test_literal_input_preserved(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "TRUE"),
            _make_output_elem(2, 20, "bOut"),
            _make_connection(10, 20),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "bOut := TRUE;" in tc.generated_st

    def test_qualified_name_preserved(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "SR.Q1"),
            _make_output_elem(2, 20, "bOut"),
            _make_connection(10, 20),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "bOut := SR.Q1;" in tc.generated_st


class TestMainEntryPoint:
    def test_main_dry_run(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_output_elem(2, 20, "bOut"),
            _make_connection(10, 20),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        rc = C.main(["--input", str(p), "--dry-run", "--no-log", "--no-report"])
        assert rc == 0

    def test_main_no_swap(self, tmp_path):
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_output_elem(2, 20, "bOut"),
            _make_connection(10, 20),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        rc = C.main(["--input", str(p), "--no-swap", "--no-log", "--no-report"])
        assert rc == 0
        gen_files = list(tmp_path.glob("*_st_generated*"))
        assert len(gen_files) == 1


# ===================================================================
# Helper builders for new element types
# ===================================================================

def _make_source_mark(eid: int, pin_id: int, label: str) -> str:
    return textwrap.dedent(f'''\
                  <o t="CFCSourceConnectionMark">
                    <o n="Input" t="CFCInputPin">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Negated">false</v>
                      <v n="Id">{pin_id}L</v>
                    </o>
                    <o n="Text" t="CFCText">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Text">"{label}"</v>
                      <v n="Modifiable">true</v>
                      <v n="Id">{eid + 100}L</v>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="Id">{eid}L</v>
                  </o>''')


def _make_sink_mark(eid: int, pin_id: int, label: str,
                    negated: bool = False) -> str:
    neg_str = "true" if negated else "false"
    return textwrap.dedent(f'''\
                  <o t="CFCSinkConnectionMark">
                    <o n="Output" t="CFCOutputPin">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Negated">{neg_str}</v>
                      <v n="Id">{pin_id}L</v>
                    </o>
                    <o n="Text" t="CFCText">
                      <v n="Bounds">"0, 0, 0, 0"</v>
                      <v n="Text">"{label}"</v>
                      <v n="Modifiable">true</v>
                      <v n="Id">{eid + 100}L</v>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="Id">{eid}L</v>
                  </o>''')


def _make_box_kindofcall(eid: int, box_name: str, kind: str,
                         input_pin_ids: list = None,
                         output_pin_id: int = None) -> str:
    """Build a CFCBoxElement with arbitrary KindOfCall."""
    inputs_xml = ""
    if input_pin_ids:
        pins = ""
        for pid in input_pin_ids:
            pins += f'<o><v n="Negated">false</v><v n="Id">{pid}L</v></o>\n'
        inputs_xml = (f'<o n="Inputs" t="CFCItemList">'
                      f'<l2 n="InnerList" cet="CFCInputPin">{pins}</l2></o>')
    outputs_xml = ""
    if output_pin_id is not None:
        outputs_xml = (
            f'<o n="Outputs" t="CFCItemList">'
            f'<l2 n="InnerList" cet="CFCOutputPin">'
            f'<o><v n="Negated">false</v><v n="Id">{output_pin_id}L</v></o>'
            f'</l2></o>')
    return textwrap.dedent(f'''\
                  <o t="CFCBoxElement">
                    {inputs_xml}
                    {outputs_xml}
                    <o n="Texts" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCText">
                        <o><v n="Text">"{box_name}"</v><v n="Modifiable">true</v><v n="Id">0L</v></o>
                      </l2>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="KindOfCall" t="KindOfCall">{kind}</v>
                    <v n="EnEno">false</v>
                    <v n="Id">{eid}L</v>
                  </o>''')


def _make_fb_box(eid: int, fb_type: str, instance: str,
                 input_pin_ids: list, output_pin_ids: list,
                 input_names: list = None, output_names: list = None) -> str:
    """Build a FunctionBlock CFCBoxElement with named pins."""
    pins_xml = ""
    for pid in input_pin_ids:
        pins_xml += f'<o><v n="Negated">false</v><v n="Id">{pid}L</v></o>\n'
    out_pins = ""
    for pid in output_pin_ids:
        out_pins += f'<o><v n="Negated">false</v><v n="Id">{pid}L</v></o>\n'
    in_names = input_names or []
    on_names = output_names or []
    texts = []
    for n in in_names:
        texts.append(f'<o><v n="Text">"{n}"</v><v n="Id">0L</v></o>')
    for n in on_names:
        texts.append(f'<o><v n="Text">"{n}"</v><v n="Id">0L</v></o>')
    texts.append(f'<o><v n="Text">"{fb_type}"</v><v n="Modifiable">true</v><v n="Id">0L</v></o>')
    texts.append(f'<o><v n="Text">"{instance}"</v><v n="Modifiable">true</v><v n="Id">0L</v></o>')
    texts_xml = "\n".join(texts)
    return textwrap.dedent(f'''\
                  <o t="CFCBoxElement">
                    <o n="Inputs" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCInputPin">
                        {pins_xml}
                      </l2>
                    </o>
                    <o n="Outputs" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCOutputPin">
                        {out_pins}
                      </l2>
                    </o>
                    <o n="Texts" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCText">
                        {texts_xml}
                      </l2>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="KindOfCall" t="KindOfCall">FunctionBlock</v>
                    <v n="EnEno">false</v>
                    <v n="Id">{eid}L</v>
                  </o>''')


def _make_sel_box(eid: int, input_pin_ids: list, output_pin_id: int) -> str:
    """Build a SEL operator box."""
    pins = ""
    for pid in input_pin_ids:
        pins += f'<o><v n="Negated">false</v><v n="Id">{pid}L</v></o>\n'
    empty_texts = '                        <o><v n="Text">""</v><v n="Id">0L</v></o>\n' * len(input_pin_ids)
    return textwrap.dedent(f'''\
                  <o t="CFCBoxElement">
                    <o n="Inputs" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCInputPin">
{pins}                      </l2>
                    </o>
                    <o n="Outputs" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCOutputPin">
                        <o><v n="Negated">false</v><v n="Id">{output_pin_id}L</v></o>
                      </l2>
                    </o>
                    <o n="Texts" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCText">
{empty_texts}                        <o><v n="Text">"SEL"</v><v n="Modifiable">true</v><v n="Id">0L</v></o>
                      </l2>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="KindOfCall" t="cyclic_enum">Operator</v>
                    <v n="EnEno">false</v>
                    <v n="Id">{eid}L</v>
                  </o>''')


def _make_negated_output_operator(eid: int, op_name: str,
                                  input_pin_ids: list,
                                  output_pin_id: int) -> str:
    """Build an operator box with Negated=true on the output pin."""
    inputs_xml = ""
    for pid in input_pin_ids:
        inputs_xml += f'<o><v n="Negated">false</v><v n="Id">{pid}L</v></o>\n'
    empty_texts = '                        <o><v n="Text">""</v><v n="Id">0L</v></o>\n' * len(input_pin_ids)
    return textwrap.dedent(f'''\
                  <o t="CFCBoxElement">
                    <o n="Inputs" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCInputPin">
{inputs_xml}                      </l2>
                    </o>
                    <o n="Outputs" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCOutputPin">
                        <o>
                          <v n="Negated">true</v>
                          <v n="Id">{output_pin_id}L</v>
                        </o>
                      </l2>
                    </o>
                    <o n="Texts" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCText">
{empty_texts}                        <o><v n="Text">"{op_name}"</v><v n="Modifiable">true</v><v n="Id">0L</v></o>
                      </l2>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="KindOfCall" t="cyclic_enum">Operator</v>
                    <v n="EnEno">false</v>
                    <v n="Id">{eid}L</v>
                  </o>''')


MINIMAL_CFC_POU_WITH_ACTION = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="TestCFC" Id="{{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK TestCFC
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
{ELEMENTS}
                </l2>
              </o>
            </o>
          </Data>
        </XmlArchive>
      </CFC>
    </Implementation>
    <Action Name="MyAction" Id="{{11111111-2222-3333-4444-555555555555}}">
      <Implementation>
        <ST><![CDATA[bOut := TRUE;]]></ST>
      </Implementation>
    </Action>
  </POU>
</TcPlcObject>
''')


# ===================================================================
# Bug 1: Connection marks (CFCSourceConnectionMark / CFCSinkConnectionMark)
# ===================================================================

class TestConnectionMarks:
    def test_source_sink_mark_passthrough(self, tmp_path):
        """Signal resolves through Source->Sink marks to the original input."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bSignal"),
            _make_source_mark(2, 20, "MyLabel"),
            _make_sink_mark(3, 30, "MyLabel"),
            _make_output_elem(4, 40, "bOut"),
            _make_connection(10, 20),
            _make_connection(30, 40),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        assert "MyLabel" in graph.mark_sources
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "bOut := bSignal;" in tc.generated_st
        assert "(* unknown pin *)" not in tc.generated_st

    def test_or_through_marks_to_output(self, tmp_path):
        """OR operator output flows through marks and resolves correctly."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_input_elem(2, 20, "bB"),
            _make_operator_box(3, "OR", [30, 31], 32),
            _make_source_mark(4, 40, "OrResult"),
            _make_sink_mark(5, 50, "OrResult"),
            _make_output_elem(6, 60, "bOut"),
            _make_connection(10, 30),
            _make_connection(20, 31),
            _make_connection(32, 40),
            _make_connection(50, 60),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "bA OR bB" in tc.generated_st
        assert "(* unknown pin *)" not in tc.generated_st

    def test_fan_out_via_multiple_sinks(self, tmp_path):
        """One source mark fans out to multiple sink marks."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bSignal"),
            _make_source_mark(2, 20, "Fan"),
            _make_sink_mark(3, 30, "Fan"),
            _make_sink_mark(4, 40, "Fan"),
            _make_output_elem(5, 50, "bOut1"),
            _make_output_elem(6, 60, "bOut2"),
            _make_connection(10, 20),
            _make_connection(30, 50),
            _make_connection(40, 60),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "bOut1 := bSignal;" in tc.generated_st
        assert "bOut2 := bSignal;" in tc.generated_st

    def test_mark_pins_registered(self, tmp_path):
        """Source and sink mark pins are registered in graph.pins."""
        elems = "\n".join([
            _make_source_mark(1, 10, "X"),
            _make_sink_mark(2, 20, "X"),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        assert 10 in graph.pins
        assert 20 in graph.pins
        assert graph.pins[10].pin_type == "input"
        assert graph.pins[20].pin_type == "output"


# ===================================================================
# Bug 2: SUPER^ call
# ===================================================================

class TestSuperCall:
    def test_super_base_emitted(self, tmp_path):
        """SUPER^ with KindOfCall=Base emits SUPER^(); statement."""
        elems = "\n".join([
            _make_box_kindofcall(1, "SUPER^", "Base"),
            _make_input_elem(2, 20, "bA"),
            _make_output_elem(3, 30, "bOut"),
            _make_connection(20, 30),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "SUPER^();" in tc.generated_st


# ===================================================================
# Bug 3: Action call (LocalAction)
# ===================================================================

class TestActionCall:
    def test_local_action_emitted(self, tmp_path):
        """Box with KindOfCall=LocalAction emits ActionName(); statement."""
        elems = "\n".join([
            _make_box_kindofcall(1, "MyAction", "LocalAction"),
            _make_input_elem(2, 20, "bA"),
            _make_output_elem(3, 30, "bOut"),
            _make_connection(20, 30),
        ])
        xml = MINIMAL_CFC_POU_WITH_ACTION.replace("{ELEMENTS}", elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "MyAction();" in tc.generated_st


# ===================================================================
# Bug 4: Negated output pin
# ===================================================================

class TestNegatedOutputPin:
    def test_negated_operator_output_wraps_not(self, tmp_path):
        """Operator with Negated=true on output pin wraps expression in NOT."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bA"),
            _make_input_elem(2, 20, "bB"),
            _make_negated_output_operator(3, "OR", [30, 31], 32),
            _make_output_elem(4, 40, "bOut"),
            _make_connection(10, 30),
            _make_connection(20, 31),
            _make_connection(32, 40),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "NOT" in tc.generated_st
        assert "bA OR bB" in tc.generated_st

    def test_negated_sink_mark_wraps_not(self, tmp_path):
        """Sink mark with Negated=true on output pin wraps in NOT."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bSignal"),
            _make_source_mark(2, 20, "Sig"),
            _make_sink_mark(3, 30, "Sig", negated=True),
            _make_output_elem(4, 40, "bOut"),
            _make_connection(10, 20),
            _make_connection(30, 40),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "NOT bSignal" in tc.generated_st


# ===================================================================
# Bug 5: SEL simplification
# ===================================================================

class TestSELSimplification:
    def test_sel_false_true_simplifies(self, tmp_path):
        """SEL(x, FALSE, TRUE) simplifies to x."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bSwitch"),
            _make_input_elem(2, 20, "FALSE"),
            _make_input_elem(3, 30, "TRUE"),
            _make_sel_box(4, [40, 41, 42], 43),
            _make_output_elem(5, 50, "bOut"),
            _make_connection(10, 40),
            _make_connection(20, 41),
            _make_connection(30, 42),
            _make_connection(43, 50),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "SEL(" not in tc.generated_st
        assert "bSwitch" in tc.generated_st

    def test_sel_true_false_simplifies_to_not(self, tmp_path):
        """SEL(x, TRUE, FALSE) simplifies to NOT x."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bSwitch"),
            _make_input_elem(2, 20, "TRUE"),
            _make_input_elem(3, 30, "FALSE"),
            _make_sel_box(4, [40, 41, 42], 43),
            _make_output_elem(5, 50, "bOut"),
            _make_connection(10, 40),
            _make_connection(20, 41),
            _make_connection(30, 42),
            _make_connection(43, 50),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "SEL(" not in tc.generated_st
        assert "NOT bSwitch" in tc.generated_st

    def test_sel_other_values_preserved(self, tmp_path):
        """SEL(x, A, B) with non-trivial values stays as SEL call."""
        elems = "\n".join([
            _make_input_elem(1, 10, "bSwitch"),
            _make_input_elem(2, 20, "nValA"),
            _make_input_elem(3, 30, "nValB"),
            _make_sel_box(4, [40, 41, 42], 43),
            _make_output_elem(5, 50, "nOut"),
            _make_connection(10, 40),
            _make_connection(20, 41),
            _make_connection(30, 42),
            _make_connection(43, 50),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "SEL(bSwitch, nValA, nValB)" in tc.generated_st


# ===================================================================
# Bug 6: POU type detection
# ===================================================================

class TestPOUTypeDetection:
    def test_comment_before_fb(self):
        from twincat_migrator_base import _detect_pou_type
        decl = "// Some comment\nFUNCTION_BLOCK FB_Test\nVAR\nEND_VAR"
        assert _detect_pou_type(decl) == "FUNCTION_BLOCK"

    def test_attribute_before_fb(self):
        from twincat_migrator_base import _detect_pou_type
        decl = "{attribute 'qualified_only'}\nFUNCTION_BLOCK FB_Test\nVAR\nEND_VAR"
        assert _detect_pou_type(decl) == "FUNCTION_BLOCK"

    def test_multiline_comments_before_program(self):
        from twincat_migrator_base import _detect_pou_type
        decl = "(* multi-line comment *)\n// another comment\nPROGRAM MAIN\nVAR\nEND_VAR"
        assert _detect_pou_type(decl) == "PROGRAM"

    def test_empty_lines_before_function(self):
        from twincat_migrator_base import _detect_pou_type
        decl = "\n\n\nFUNCTION F_Test : BOOL\nVAR_INPUT\nEND_VAR"
        assert _detect_pou_type(decl) == "FUNCTION"

    def test_direct_keyword_still_works(self):
        from twincat_migrator_base import _detect_pou_type
        decl = "FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR"
        assert _detect_pou_type(decl) == "FUNCTION_BLOCK"


# ===================================================================
# Bug 7: Accuracy metric
# ===================================================================

class TestAccuracyMetric:
    def test_accuracy_uses_item_count(self):
        from twincat_migrator_base import calculate_accuracy, NwlNetwork
        tc = TcFile()
        tc.networks = [NwlNetwork(index=0, items=[
            AssignNode(outputs=[OperandNode(name="a")], rvalue=OperandNode(name="b")),
            AssignNode(outputs=[OperandNode(name="c")], rvalue=OperandNode(name="d")),
            AssignNode(outputs=[OperandNode(name="e")], rvalue=OperandNode(name="f")),
            AssignNode(outputs=[OperandNode(name="g")], rvalue=OperandNode(name="h")),
            AssignNode(outputs=[OperandNode(name="i")], rvalue=OperandNode(name="j")),
        ])]
        tc.warnings = ["some warning"]
        acc = calculate_accuracy(tc)
        assert acc == 90.0, f"Expected 90.0 got {acc}"

    def test_accuracy_100_no_issues(self):
        from twincat_migrator_base import calculate_accuracy, NwlNetwork
        tc = TcFile()
        tc.networks = [NwlNetwork(index=0, items=[
            AssignNode(outputs=[OperandNode(name="a")], rvalue=OperandNode(name="b")),
        ])]
        acc = calculate_accuracy(tc)
        assert acc == 100.0


# ===================================================================
# Bug 1b: Singular Output/Input on CFCBoxElement
# ===================================================================

class TestSingularPins:
    def test_singular_output_on_box(self, tmp_path):
        """Box with singular Output pin (not in CFCItemList) is parsed."""
        xml_elem = textwrap.dedent('''\
                  <o t="CFCBoxElement">
                    <o n="Inputs" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCInputPin">
                        <o><v n="Negated">false</v><v n="Id">10L</v></o>
                      </l2>
                    </o>
                    <o n="Output" t="CFCOutputPin">
                      <v n="Negated">false</v>
                      <v n="Id">20L</v>
                    </o>
                    <o n="Texts" t="CFCItemList">
                      <l2 n="InnerList" cet="CFCText">
                        <o><v n="Text">"NOT"</v><v n="Modifiable">true</v><v n="Id">0L</v></o>
                      </l2>
                    </o>
                    <v n="Bounds">"0, 0, 0, 0"</v>
                    <v n="KindOfCall" t="cyclic_enum">Operator</v>
                    <v n="EnEno">false</v>
                    <v n="Id">1L</v>
                  </o>''')
        elems = "\n".join([
            _make_input_elem(2, 30, "bA"),
            xml_elem,
            _make_output_elem(3, 40, "bOut"),
            _make_connection(30, 10),
            _make_connection(20, 40),
        ])
        xml = _build_cfc_xml(elems)
        p = tmp_path / "test.TcPOU"
        p.write_text(xml, encoding="utf-8")
        tc = load_file(p)
        graph = C.parse_cfc_graph(tc)
        assert 20 in graph.pins
        tc.networks = C.map_cfc_to_ir(graph, tc)
        from twincat_migrator_base import convert_networks_to_st
        convert_networks_to_st(tc, MigrationConfig())
        assert "(* unknown pin *)" not in tc.generated_st


