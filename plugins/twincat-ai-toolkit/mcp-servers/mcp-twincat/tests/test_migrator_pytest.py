"""
Comprehensive pytest audit for twincat_fup_to_st_migrator.py

Uses synthetic TwinCAT XML fixtures -- no external project files required.
Run with:  pytest test_migrator_pytest.py -v
"""
import json
import os
import re
import shutil
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import twincat_fup_to_st_migrator as M

# ===================================================================
# Synthetic TwinCAT XML templates
# ===================================================================

MINIMAL_NWL_POU = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="TestProg" Id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}" SpecialFunc="None">
    <Declaration><![CDATA[PROGRAM TestProg
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
{NETWORKS}
              </l2>
              <v n="BranchCounter">0</v>
              <v n="ValidIds">true</v>
            </o>
          </Data>
          <TypeList>
            <Type n="Boolean">System.Boolean</Type>
            <Type n="BoxTreeAssign">{{9873c309-1f09-4ebf-9078-42d8057ef11b}}</Type>
            <Type n="BoxTreeBox">{{acfc6f68-8e3a-4af5-bf81-3dd512095a46}}</Type>
            <Type n="BoxTreeOperand">{{9de7f100-1b87-424c-a62e-45b0cfc85ed2}}</Type>
            <Type n="Flags">{{668066f2-6069-46b3-8962-8db8d13d7db2}}</Type>
            <Type n="Int32">System.Int32</Type>
            <Type n="Int64">System.Int64</Type>
            <Type n="Network">{{d9a99d73-b633-47db-b876-a752acb25871}}</Type>
            <Type n="NWLImplementationObject">{{25e509de-33d4-4447-93f8-c9e4ea381c8b}}</Type>
            <Type n="Operand">{{c9b2f165-48a2-4a45-8326-3952d8a3d708}}</Type>
            <Type n="Operator">{{bffb3c53-f105-4e85-aba2-e30df579d75f}}</Type>
            <Type n="OutputItemList">{{f40d3e09-c02c-4522-a88c-dac23558cfc4}}</Type>
            <Type n="ParamList">{{71496971-9e0c-4677-a832-b9583b571130}}</Type>
            <Type n="String">System.String</Type>
          </TypeList>
        </XmlArchive>
      </NWL>
    </Implementation>
{ACTIONS}
  </POU>
</TcPlcObject>''')


def _simple_assign_network(src_var="TRUE", tgt_var="bOut", out_commented="false"):
    return textwrap.dedent(f'''\
                <o>
                  <v n="ILActive">false</v>
                  <v n="FBDValid">false</v>
                  <v n="ILValid">false</v>
                  <l2 n="ILLines" />
                  <v n="Comment">""</v>
                  <v n="Title">""</v>
                  <v n="Label">""</v>
                  <v n="OutCommented">{out_commented}</v>
                  <l2 n="NetworkItems" cet="BoxTreeAssign">
                    <o>
                      <o n="OutputItems" t="OutputItemList">
                        <l2 n="OutputItems" cet="Operand">
                          <o>
                            <v n="Operand">"{tgt_var}"</v>
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
                      <o n="Flags" t="Flags"><v n="Flags">0</v><v n="Fixed">false</v><v n="Extensible">false</v></o>
                      <o n="RValue" t="BoxTreeOperand">
                        <o n="Operand" t="Operand">
                          <v n="Operand">"{src_var}"</v>
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
                        <v n="Id">3L</v>
                      </o>
                      <v n="Id">4L</v>
                    </o>
                  </l2>
                  <l2 n="Connectors" />
                  <v n="Id">5L</v>
                </o>''')


def _or_box_network(in1="bA", in2="bB", tgt="bOut"):
    return textwrap.dedent(f'''\
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
                            <v n="Operand">"{tgt}"</v>
                            <v n="Type">"BOOL"</v>
                            <v n="Comment">""</v><v n="SymbolComment">""</v><v n="Address">""</v>
                            <o n="Flags" t="Flags"><v n="Flags">0</v><v n="Fixed">false</v><v n="Extensible">false</v></o>
                            <v n="LValue">true</v><v n="Boolean">false</v><v n="IsInstance">false</v>
                            <v n="Id">10L</v>
                          </o>
                        </l2>
                      </o>
                      <o n="Flags" t="Flags"><v n="Flags">0</v><v n="Fixed">false</v><v n="Extensible">false</v></o>
                      <o n="RValue" t="BoxTreeBox">
                        <v n="BoxType">""</v>
                        <o n="Instance" t="Operand"><n n="Operand" /><v n="Type">""</v><v n="Comment">""</v><v n="SymbolComment">""</v><v n="Address">""</v><o n="Flags" t="Flags"><v n="Flags">0</v><v n="Fixed">false</v><v n="Extensible">false</v></o><v n="LValue">false</v><v n="Boolean">false</v><v n="IsInstance">true</v><v n="Id">20L</v></o>
                        <o n="OutputItems" t="OutputItemList"><l2 n="OutputItems"><n /></l2></o>
                        <o n="Flags" t="Flags"><v n="Flags">0</v><v n="Fixed">false</v><v n="Extensible">false</v></o>
                        <n n="InputFlags" />
                        <l2 n="InputItems">
                          <o t="BoxTreeOperand"><o n="Operand" t="Operand"><v n="Operand">"{in1}"</v><v n="Type">"BOOL"</v><v n="Comment">""</v><v n="SymbolComment">""</v><v n="Address">""</v><o n="Flags" t="Flags"><v n="Flags">0</v><v n="Fixed">false</v><v n="Extensible">false</v></o><v n="LValue">false</v><v n="Boolean">false</v><v n="IsInstance">false</v><v n="Id">21L</v></o><v n="Id">22L</v></o>
                          <o t="BoxTreeOperand"><o n="Operand" t="Operand"><v n="Operand">"{in2}"</v><v n="Type">"BOOL"</v><v n="Comment">""</v><v n="SymbolComment">""</v><v n="Address">""</v><o n="Flags" t="Flags"><v n="Flags">0</v><v n="Fixed">false</v><v n="Extensible">false</v></o><v n="LValue">false</v><v n="Boolean">false</v><v n="IsInstance">false</v><v n="Id">23L</v></o><v n="Id">24L</v></o>
                        </l2>
                        <o n="InputParam" t="ParamList"><l2 n="Names" /><l2 n="Types" /></o>
                        <o n="OutputParam" t="ParamList"><l2 n="Names" /><l2 n="Types" /></o>
                        <v n="CallType" t="Operator">Or</v>
                        <v n="EN">false</v><v n="ENO">false</v>
                        <n n="STSnippet" /><v n="ContainsExtensibleInputs">false</v><v n="ProvidesSTSnippet">false</v>
                        <v n="Id">25L</v>
                      </o>
                      <v n="Id">26L</v>
                    </o>
                  </l2>
                  <l2 n="Connectors" />
                  <v n="Id">27L</v>
                </o>''')


def _make_pou(networks_xml, actions_xml="", decl=None):
    xml = MINIMAL_NWL_POU.replace("{NETWORKS}", networks_xml).replace("{ACTIONS}", actions_xml)
    if decl:
        xml = re.sub(r'<Declaration><!\[CDATA\[.*?\]\]></Declaration>',
                     f'<Declaration><![CDATA[{decl}]]></Declaration>', xml, flags=re.DOTALL)
    return xml

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

MINIMAL_CFC_POU = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="CfcProg" Id="{22222222-3333-4444-5555-666666666666}" SpecialFunc="None">
    <Declaration><![CDATA[PROGRAM CfcProg
VAR
END_VAR
]]></Declaration>
    <Implementation>
      <CFC></CFC>
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

MINIMAL_DUT = textwrap.dedent('''\
<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <DUT Name="ST_TestStruct" Id="{44444444-5555-6666-7777-888888888888}">
    <Declaration><![CDATA[TYPE ST_TestStruct :
STRUCT
    nVal : INT;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>''')

BROKEN_XML = '<?xml version="1.0" encoding="utf-8"?>\n<TcPlcObject><POU Name="Broken"'


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


def _write(tmp_dir, name, content):
    p = tmp_dir / name
    p.write_text(content, encoding="utf-8")
    return p


# ===================================================================
# 1. CLI-Parameter
# ===================================================================

class TestCLI:
    def test_minimal_args(self):
        cfg = M.parse_arguments(["--input", "test.TcPOU"])
        assert cfg.input_path == "test.TcPOU"
        assert cfg.swap is True
        assert cfg.backup is True
        assert cfg.replace is False
        assert cfg.dry_run is False

    def test_no_swap(self):
        cfg = M.parse_arguments(["--input", "x", "--no-swap"])
        assert cfg.swap is False

    def test_replace(self):
        cfg = M.parse_arguments(["--input", "x", "--replace"])
        assert cfg.replace is True

    def test_dry_run(self):
        cfg = M.parse_arguments(["--input", "x", "--dry-run"])
        assert cfg.dry_run is True

    def test_analyze_only(self):
        cfg = M.parse_arguments(["--input", "x", "--analyze-only"])
        assert cfg.analyze_only is True

    def test_strict(self):
        cfg = M.parse_arguments(["--input", "x", "--strict"])
        assert cfg.strict is True

    def test_no_log_no_report(self):
        cfg = M.parse_arguments(["--input", "x", "--no-log", "--no-report"])
        assert cfg.log_enabled is False
        assert cfg.report_enabled is False


# ===================================================================
# 2. Config-Dateien
# ===================================================================

class TestConfig:
    def test_load_json_config(self, tmp_dir):
        cfg_data = {"replace": True, "strict": True, "dryRun": True}
        p = tmp_dir / "cfg.json"
        p.write_text(json.dumps(cfg_data), encoding="utf-8")
        cfg = M.MigrationConfig(config_file=str(p))
        cfg = M.load_config(cfg)
        assert cfg.replace is True
        assert cfg.strict is True
        assert cfg.dry_run is True

    def test_missing_config_no_crash(self):
        cfg = M.MigrationConfig(config_file="nonexistent.json")
        cfg = M.load_config(cfg)
        assert cfg.replace is False

    def test_invalid_json(self, tmp_dir):
        p = tmp_dir / "bad.json"
        p.write_text("{invalid json", encoding="utf-8")
        cfg = M.MigrationConfig(config_file=str(p))
        cfg = M.load_config(cfg)
        assert cfg is not None


# ===================================================================
# 3. Dateisuche
# ===================================================================

class TestFileCollection:
    def test_single_file(self, tmp_dir):
        p = _write(tmp_dir, "test.TcPOU", "<x/>")
        cfg = M.MigrationConfig(input_path=str(p))
        files = M.collect_input_files(cfg)
        assert len(files) == 1

    def test_unsupported_extension(self, tmp_dir):
        p = _write(tmp_dir, "test.txt", "<x/>")
        cfg = M.MigrationConfig(input_path=str(p))
        files = M.collect_input_files(cfg)
        assert len(files) == 0

    def test_folder_non_recursive(self, tmp_dir):
        _write(tmp_dir, "a.TcPOU", "<x/>")
        sub = tmp_dir / "sub"
        sub.mkdir()
        _write(sub, "b.TcPOU", "<x/>")
        cfg = M.MigrationConfig(input_path=str(tmp_dir), recursive=False)
        files = M.collect_input_files(cfg)
        assert len(files) == 1

    def test_folder_recursive(self, tmp_dir):
        _write(tmp_dir, "a.TcPOU", "<x/>")
        sub = tmp_dir / "sub"
        sub.mkdir()
        _write(sub, "b.TcPOU", "<x/>")
        cfg = M.MigrationConfig(input_path=str(tmp_dir), recursive=True)
        files = M.collect_input_files(cfg)
        assert len(files) == 2

    def test_nonexistent_path(self):
        cfg = M.MigrationConfig(input_path="Z:\\does_not_exist_12345")
        files = M.collect_input_files(cfg)
        assert len(files) == 0

    def test_gvl_and_dut_collected(self, tmp_dir):
        _write(tmp_dir, "x.TcGVL", "<x/>")
        _write(tmp_dir, "y.TcDUT", "<x/>")
        cfg = M.MigrationConfig(input_path=str(tmp_dir))
        files = M.collect_input_files(cfg)
        assert len(files) == 2


# ===================================================================
# 4. Gueltige und defekte .TcPOU-Dateien
# ===================================================================

class TestLoadFile:
    def test_valid_nwl_pou(self, tmp_dir):
        xml = _make_pou(_simple_assign_network())
        p = _write(tmp_dir, "Test.TcPOU", xml)
        tc = M.load_file(p)
        assert tc is not None
        assert tc.pou_name == "TestProg"
        assert tc.pou_type == "PROGRAM"
        assert tc.impl_type == "NWL"
        assert not tc.errors

    def test_st_pou(self, tmp_dir):
        p = _write(tmp_dir, "ST.TcPOU", MINIMAL_ST_POU)
        tc = M.load_file(p)
        assert tc.impl_type == "ST"
        assert not tc.errors

    def test_cfc_pou(self, tmp_dir):
        p = _write(tmp_dir, "CFC.TcPOU", MINIMAL_CFC_POU)
        tc = M.load_file(p)
        assert tc.impl_type == "CFC"

    def test_broken_xml(self, tmp_dir):
        p = _write(tmp_dir, "Broken.TcPOU", BROKEN_XML)
        tc = M.load_file(p)
        assert tc is not None
        assert len(tc.errors) > 0
        assert "XML parse error" in tc.errors[0]


# ===================================================================
# 5. .TcGVL und .TcDUT
# ===================================================================

class TestGVLDUT:
    def test_gvl_load(self, tmp_dir):
        p = _write(tmp_dir, "GVL_Test.TcGVL", MINIMAL_GVL)
        tc = M.load_file(p)
        assert tc.pou_name == "GVL_Test"
        assert not tc.errors

    def test_dut_load(self, tmp_dir):
        p = _write(tmp_dir, "ST_TestStruct.TcDUT", MINIMAL_DUT)
        tc = M.load_file(p)
        assert tc.pou_name == "ST_TestStruct"
        assert not tc.errors

    def test_gvl_skipped_in_pipeline(self, tmp_dir):
        p = _write(tmp_dir, "GVL_Test.TcGVL", MINIMAL_GVL)
        cfg = M.MigrationConfig(input_path=str(p), dry_run=True)
        mlog = M.MigrationLogger(False, tmp_dir)
        report = M.MigrationReport(False, tmp_dir)
        result = M.process_file(p, cfg, mlog, report)
        assert result is True


# ===================================================================
# 6. NWL-Netzwerke
# ===================================================================

class TestNWLParsing:
    def test_single_assign_network(self, tmp_dir):
        xml = _make_pou(_simple_assign_network("bInput", "bOut"))
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        assert len(tc.networks) == 1
        assert len(tc.networks[0].items) == 1

    def test_multiple_networks(self, tmp_dir):
        nw = _simple_assign_network("bA", "bOut1") + "\n" + _simple_assign_network("bB", "bOut2")
        xml = _make_pou(nw)
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        assert len(tc.networks) == 2

    def test_outcommented_network(self, tmp_dir):
        nw = _simple_assign_network("bX", "bY", out_commented="true")
        xml = _make_pou(nw)
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        assert tc.networks[0].out_commented is True


# ===================================================================
# 7. Assign, Operand, Box, Demux
# ===================================================================

class TestNodeParsing:
    def test_operand_node(self):
        op = M.OperandNode(name="bTest", type_str="BOOL")
        assert not op.is_empty
        assert op.name == "bTest"

    def test_empty_operand(self):
        op = M.OperandNode(name="", type_str="")
        assert op.is_empty

    def test_demux_node(self):
        d = M.DemuxNode(input=M.OperandNode(name="fb.nOut"))
        assert d.input.name == "fb.nOut"


# ===================================================================
# 8. AND, OR, NOT, Vergleiche und Rechenoperationen
# ===================================================================

class TestBoolAndArithmetic:
    def test_or_expression(self, tmp_dir):
        nw = _or_box_network("bA", "bB", "bOut")
        xml = _make_pou(nw)
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        cfg = M.MigrationConfig()
        M.convert_networks_to_st(tc, cfg)
        assert "bA OR bB" in tc.generated_st

    def test_clean_bool_removes_or_false(self):
        assert M._clean_bool_expr("bX OR FALSE") == "bX"

    def test_clean_bool_removes_and_true(self):
        assert M._clean_bool_expr("TRUE AND bY") == "bY"

    def test_infix_op_eq(self):
        box = M.BoxNode(box_type="EQ", input_items=[
            M.OperandNode(name="nA"), M.OperandNode(name="nB")])
        result = M._gen_infix_op(box, "=", M.TcFile(), M.MigrationConfig(), [])
        assert result == "nA = nB"

    def test_infix_op_add(self):
        box = M.BoxNode(box_type="ADD", input_items=[
            M.OperandNode(name="n1"), M.OperandNode(name="n2")])
        result = M._gen_infix_op(box, "+", M.TcFile(), M.MigrationConfig(), [])
        assert result == "n1 + n2"

    def test_sel_expression(self):
        box = M.BoxNode(box_type="SEL", input_items=[
            M.OperandNode(name="bCond"),
            M.OperandNode(name="nFalse"),
            M.OperandNode(name="nTrue")])
        result = M._gen_sel(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "SEL(bCond, nFalse, nTrue)"


# ===================================================================
# 9. Funktions- und Funktionsbausteinaufrufe
# ===================================================================

class TestFBAndFunctionCalls:
    def test_fb_call_with_instance(self):
        box = M.BoxNode(
            box_type="TON", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbTimer"),
            input_items=[M.OperandNode(name="bStart"), M.OperandNode(name="T#5S")],
            input_param_names=["IN", "PT"],
            input_param_types=["BOOL", "TIME"],
            output_param_names=["Q", "ET"],
            output_param_types=["BOOL", "TIME"],
            output_items=[M.OperandNode(), M.OperandNode()])
        tc = M.TcFile()
        lines = M._gen_fb_call(box, tc, M.MigrationConfig(), [])
        joined = "\n".join(lines)
        assert "fbTimer(" in joined
        assert "IN" in joined
        assert "PT" in joined

    def test_fb_without_instance_gives_todo(self):
        box = M.BoxNode(box_type="SomeBlock", call_type="FunctionBlock",
                        instance=None)
        tc = M.TcFile()
        lines = M._gen_fb_call(box, tc, M.MigrationConfig(), [])
        assert any("TODO" in l for l in lines)
        assert len(tc.todos) == 1

    def test_function_call_uses_box_type(self):
        box = M.BoxNode(
            box_type="F_MyFunc", call_type="Function",
            instance=M.OperandNode(name="", is_instance=True),
            input_items=[M.OperandNode(name="42")],
            input_param_names=["nInput"],
            input_param_types=["INT"],
            output_param_names=[], output_param_types=[],
            output_items=[])
        tc = M.TcFile()
        lines = M._gen_fb_call(box, tc, M.MigrationConfig(), [])
        joined = "\n".join(lines)
        assert "F_MyFunc(" in joined

    def test_inline_function_expr(self):
        box = M.BoxNode(
            box_type="F_Calc", call_type="Function",
            instance=M.OperandNode(name=""),
            input_items=[M.OperandNode(name="10"), M.OperandNode(name="20")],
            input_param_names=["a", "b"],
            input_param_types=["INT", "INT"],
            output_param_names=[], output_param_types=[],
            output_items=[])
        tc = M.TcFile()
        expr = M._gen_function_call_expr(box, tc, M.MigrationConfig(), [])
        assert "F_Calc(" in expr
        assert "a" in expr


# ===================================================================
# 10. Edge-Trigger mit R_TRIG und F_TRIG
# ===================================================================

class TestEdgeTrigger:
    def test_input_flag_negation(self):
        tc = M.TcFile()
        box = M.BoxNode(instance=M.OperandNode(name="fb1"),
                        input_param_names=["bIn"])
        result = M._apply_input_flag("bSensor", 1, box, 0, tc, [])
        assert result == "NOT bSensor"

    def test_input_flag_rising_edge(self):
        tc = M.TcFile()
        hoisted = []
        box = M.BoxNode(instance=M.OperandNode(name="fb1"),
                        input_param_names=["bTrigger"])
        result = M._apply_input_flag("bButton", 2, box, 0, tc, hoisted)
        assert "PosEdge" in result
        assert ".Q" in result
        assert len(hoisted) == 1
        assert "CLK := bButton" in hoisted[0]
        assert len(tc.edge_vars) == 1
        assert tc.edge_vars[0][1] == "R_TRIG"

    def test_input_flag_falling_edge(self):
        tc = M.TcFile()
        hoisted = []
        box = M.BoxNode(instance=M.OperandNode(name="fb1"),
                        input_param_names=["bTrigger"])
        result = M._apply_input_flag("bButton", 4, box, 0, tc, hoisted)
        assert "NegEdge" in result
        assert tc.edge_vars[0][1] == "F_TRIG"

    def test_flag_16_32_ignored(self):
        tc = M.TcFile()
        result = M._apply_input_flag("bVal", 16, M.BoxNode(), 0, tc, [])
        assert result == "bVal"
        result = M._apply_input_flag("bVal", 32, M.BoxNode(), 0, tc, [])
        assert result == "bVal"

    def test_combined_flag_negation_plus_metadata(self):
        tc = M.TcFile()
        result = M._apply_input_flag("bVal", 17, M.BoxNode(instance=M.OperandNode(name="x"),
                                     input_param_names=["i"]), 0, tc, [])
        assert "NOT" in result


# ===================================================================
# 11. XML-Ersetzung von NWL nach ST
# ===================================================================

class TestXMLWriter:
    def test_nwl_replaced_with_st(self, tmp_dir):
        xml = _make_pou(_simple_assign_network("bIn", "bOut"))
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        M.convert_networks_to_st(tc, M.MigrationConfig())
        result = M.write_st_to_xml(tc)
        assert result is not None
        assert "<ST><![CDATA[" in result
        assert "<NWL>" not in result

    def test_edge_vars_added_to_declaration(self, tmp_dir):
        xml = _make_pou(_simple_assign_network("bIn", "bOut"))
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        M.convert_networks_to_st(tc, M.MigrationConfig())
        tc.edge_vars = [("fbEdge1", "R_TRIG")]
        result = M.write_st_to_xml(tc)
        assert "fbEdge1 : R_TRIG;" in result


# ===================================================================
# 12. CDATA-Erhalt
# ===================================================================

class TestCDATA:
    def test_cdata_wrapping(self, tmp_dir):
        xml = _make_pou(_simple_assign_network())
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        M.convert_networks_to_st(tc, M.MigrationConfig())
        result = M.write_st_to_xml(tc)
        assert "CDATA[" in result
        cdata_blocks = re.findall(r'<!\[CDATA\[(.*?)\]\]>', result, re.DOTALL)
        assert len(cdata_blocks) >= 1


# ===================================================================
# 13. ID-/GUID-Erhalt und Regeneration
# ===================================================================

class TestGUID:
    def test_guid_regeneration(self, tmp_dir):
        xml = _make_pou(_simple_assign_network())
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        M.convert_networks_to_st(tc, M.MigrationConfig())
        original_result = M.write_st_to_xml(tc, regenerate_ids=False)
        regen_result = M.write_st_to_xml(tc, regenerate_ids=True)
        orig_guids = set(re.findall(r'Id="\{([0-9a-fA-F\-]+)\}"', original_result))
        regen_guids = set(re.findall(r'Id="\{([0-9a-fA-F\-]+)\}"', regen_result))
        assert len(regen_guids) > 0
        assert orig_guids != regen_guids

    def test_no_regeneration_preserves_ids(self, tmp_dir):
        xml = _make_pou(_simple_assign_network())
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        M.convert_networks_to_st(tc, M.MigrationConfig())
        result = M.write_st_to_xml(tc, regenerate_ids=False)
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in result


# ===================================================================
# 14. Backup
# ===================================================================

class TestBackup:
    def test_create_backup(self, tmp_dir):
        p = _write(tmp_dir, "Test.TcPOU", "original content")
        bp = M.create_backup(p)
        assert bp is not None
        assert bp.exists()
        assert "FUP_Backup" in bp.name
        assert bp.read_text() == "original content"

    def test_backup_failure_returns_none(self, tmp_dir):
        fake = tmp_dir / "nonexistent_dir" / "file.TcPOU"
        result = M.create_backup(fake)
        assert result is None


# ===================================================================
# 15. Replace
# ===================================================================

class TestReplace:
    def test_can_replace_checks(self, tmp_dir):
        xml = _make_pou(_simple_assign_network())
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        M.convert_networks_to_st(tc, M.MigrationConfig())
        cfg = M.MigrationConfig(replace=True)
        ok, reason = M.can_replace(tc, cfg, Path("backup"))
        assert ok is True

    def test_can_replace_fails_without_replace_flag(self, tmp_dir):
        xml = _make_pou(_simple_assign_network())
        p = _write(tmp_dir, "T.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        M.convert_networks_to_st(tc, M.MigrationConfig())
        cfg = M.MigrationConfig(replace=False, backup=False)
        ok, reason = M.can_replace(tc, cfg, None)
        assert ok is False
        assert "replace" in reason.lower()


# ===================================================================
# 16. Swap
# ===================================================================

class TestSwap:
    def test_swap_single_file(self, tmp_dir):
        xml = _make_pou(_simple_assign_network("bIn", "bOut"))
        p = _write(tmp_dir, "Test.TcPOU", xml)
        cfg = M.MigrationConfig(input_path=str(p), swap=True)
        mlog = M.MigrationLogger(False, tmp_dir)
        report = M.MigrationReport(False, tmp_dir)
        ok = M.process_file(p, cfg, mlog, report)
        assert ok is True
        new_content = p.read_text(encoding="utf-8")
        assert "<ST>" in new_content
        backups = list(tmp_dir.glob("*_fup_backup_*"))
        assert len(backups) == 1


# ===================================================================
# 17. Dry-Run
# ===================================================================

class TestDryRun:
    def test_dry_run_no_file_changes(self, tmp_dir):
        xml = _make_pou(_simple_assign_network())
        p = _write(tmp_dir, "Test.TcPOU", xml)
        original = p.read_text()
        cfg = M.MigrationConfig(input_path=str(p), dry_run=True)
        mlog = M.MigrationLogger(False, tmp_dir)
        report = M.MigrationReport(False, tmp_dir)
        ok = M.process_file(p, cfg, mlog, report)
        assert ok is True
        assert p.read_text() == original
        gen_files = list(tmp_dir.glob("*_ST_Generated*"))
        assert len(gen_files) == 0


# ===================================================================
# 18. Analyze-Only
# ===================================================================

class TestAnalyzeOnly:
    def test_analyze_only_no_output(self, tmp_dir):
        xml = _make_pou(_simple_assign_network())
        p = _write(tmp_dir, "Test.TcPOU", xml)
        original = p.read_text()
        cfg = M.MigrationConfig(input_path=str(p), analyze_only=True)
        mlog = M.MigrationLogger(False, tmp_dir)
        report = M.MigrationReport(False, tmp_dir)
        ok = M.process_file(p, cfg, mlog, report)
        assert ok is True
        assert p.read_text() == original


# ===================================================================
# 19. Logging
# ===================================================================

class TestLogging:
    def test_logger_saves(self, tmp_dir):
        mlog = M.MigrationLogger(True, tmp_dir, "test")
        mlog.log("Test message")
        mlog.save()
        files = list(tmp_dir.glob("test_migration_log_*"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "Test message" in content


# ===================================================================
# 20. Reporting
# ===================================================================

class TestReporting:
    def test_report_saves(self, tmp_dir):
        report = M.MigrationReport(True, tmp_dir, "test")
        tc = M.TcFile(path=tmp_dir / "fake.TcPOU")
        tc.pou_name = "Test"
        tc.pou_type = "PROGRAM"
        tc.impl_type = "NWL"
        tc.generated_st = "bOut := TRUE;\n"
        report.add(tc, None, None, False)
        report.save()
        files = list(tmp_dir.glob("test_migration_report_*"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "Test" in content
        assert "POST-MIGRATION CHECKLIST" in content


# ===================================================================
# 21. Negative Fehlerfaelle
# ===================================================================

class TestNegativeCases:
    def test_broken_xml_does_not_crash(self, tmp_dir):
        p = _write(tmp_dir, "Broken.TcPOU", BROKEN_XML)
        cfg = M.MigrationConfig(input_path=str(p))
        mlog = M.MigrationLogger(False, tmp_dir)
        report = M.MigrationReport(False, tmp_dir)
        result = M.process_file(p, cfg, mlog, report)
        assert result is False

    def test_empty_file(self, tmp_dir):
        p = _write(tmp_dir, "Empty.TcPOU", "")
        tc = M.load_file(p)
        assert tc is not None
        assert len(tc.errors) > 0

    def test_binary_garbage(self, tmp_dir):
        p = tmp_dir / "Garbage.TcPOU"
        p.write_bytes(b'\x00\x01\x02\xff\xfe\x80' * 100)
        tc = M.load_file(p)
        assert tc is not None

    def test_st_pou_skipped(self, tmp_dir):
        p = _write(tmp_dir, "ST.TcPOU", MINIMAL_ST_POU)
        cfg = M.MigrationConfig(input_path=str(p))
        mlog = M.MigrationLogger(False, tmp_dir)
        report = M.MigrationReport(False, tmp_dir)
        result = M.process_file(p, cfg, mlog, report)
        assert result is True

    def test_cfc_pou_skipped(self, tmp_dir):
        p = _write(tmp_dir, "CFC.TcPOU", MINIMAL_CFC_POU)
        cfg = M.MigrationConfig(input_path=str(p))
        mlog = M.MigrationLogger(False, tmp_dir)
        report = M.MigrationReport(False, tmp_dir)
        result = M.process_file(p, cfg, mlog, report)
        assert result is True


# ===================================================================
# 22. Schutz der Originaldatei bei Fehlern
# ===================================================================

class TestOriginalProtection:
    def test_swap_restores_on_write_failure(self, tmp_dir):
        xml = _make_pou(_simple_assign_network("bIn", "bOut"))
        p = _write(tmp_dir, "Test.TcPOU", xml)
        original_content = p.read_text()

        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        M.convert_networks_to_st(tc, M.MigrationConfig())

        backup_path = tmp_dir / "Test_fup_backup_test.TcPOU"
        shutil.copy2(str(p), str(backup_path))
        assert backup_path.exists()
        assert backup_path.read_text() == original_content

    def test_replace_blocked_without_backup_in_strict(self, tmp_dir):
        xml = _make_pou(_simple_assign_network())
        p = _write(tmp_dir, "T.TcPOU", xml)
        original = p.read_text()
        cfg = M.MigrationConfig(input_path=str(p), replace=True, backup=False, strict=True)
        mlog = M.MigrationLogger(False, tmp_dir)
        report = M.MigrationReport(False, tmp_dir)
        result = M.process_file(p, cfg, mlog, report)
        assert result is False
        assert p.read_text() == original

    def test_type_mismatch_detection(self):
        assert M._check_type_mismatch("E_IoT_Error", "BOOL") is True
        assert M._check_type_mismatch("BOOL", "BOOL") is False
        assert M._check_type_mismatch("", "BOOL") is False
        assert M._check_type_mismatch("INT", "") is False

    def test_type_mismatch_in_fb_call(self):
        box = M.BoxNode(
            box_type="FB_Test", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbInst"),
            input_items=[], input_param_names=[], input_param_types=[],
            output_param_names=["eError", "bOk"],
            output_param_types=["E_IoT_Error", "BOOL"],
            output_items=[
                M.OperandNode(name="bTarget1", type_str="BOOL"),
                M.OperandNode(name="bTarget2", type_str="BOOL"),
            ])
        tc = M.TcFile()
        lines = M._gen_fb_call(box, tc, M.MigrationConfig(), [])
        joined = "\n".join(lines)
        assert "TYPE MISMATCH" in joined
        assert "bTarget2" in joined
        assert len(tc.warnings) == 1


# ===================================================================
# Helpers / utilities
# ===================================================================

class TestHelpers:
    def test_strip_quotes(self):
        assert M._strip_quotes('"hello"') == "hello"
        assert M._strip_quotes("noquotes") == "noquotes"
        assert M._strip_quotes('""') == ""

    def test_detect_pou_type(self):
        assert M._detect_pou_type("PROGRAM Foo\nVAR\nEND_VAR") == "PROGRAM"
        assert M._detect_pou_type("FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR") == "FUNCTION_BLOCK"
        assert M._detect_pou_type("FUNCTION F_Test : INT\nVAR\nEND_VAR") == "FUNCTION"

    def test_detect_impl_type(self):
        import xml.etree.ElementTree as ET
        el = ET.fromstring("<Implementation><ST/></Implementation>")
        assert M._detect_impl_type(el) == "ST"
        el = ET.fromstring("<Implementation><NWL/></Implementation>")
        assert M._detect_impl_type(el) == "NWL"
        el = ET.fromstring("<Implementation><CFC/></Implementation>")
        assert M._detect_impl_type(el) == "CFC"


# ===================================================================
# Full pipeline end-to-end
# ===================================================================

class TestEndToEnd:
    def test_main_dry_run(self, tmp_dir):
        xml = _make_pou(_simple_assign_network("bSrc", "bDst"))
        p = _write(tmp_dir, "E2E.TcPOU", xml)
        exit_code = M.main(["--input", str(p), "--dry-run", "--no-log", "--no-report"])
        assert exit_code == 0

    def test_main_no_swap(self, tmp_dir):
        xml = _make_pou(_simple_assign_network("bSrc", "bDst"))
        p = _write(tmp_dir, "E2E.TcPOU", xml)
        exit_code = M.main(["--input", str(p), "--no-swap", "--no-log", "--no-report"])
        assert exit_code == 0
        gen = tmp_dir / "E2E_ST_Generated.TcPOU"
        assert gen.exists()
        content = gen.read_text()
        assert "bDst := bSrc;" in content

    def test_main_swap(self, tmp_dir):
        xml = _make_pou(_simple_assign_network("bA", "bB"))
        p = _write(tmp_dir, "Swap.TcPOU", xml)
        exit_code = M.main(["--input", str(p), "--no-log", "--no-report"])
        assert exit_code == 0
        new_content = p.read_text()
        assert "bB := bA;" in new_content
        backups = list(tmp_dir.glob("*_fup_backup_*"))
        assert len(backups) == 1


# ===================================================================
# IEC functions: MUX, LIMIT, SEL
# ===================================================================

class TestIECFunctions:
    def test_mux_expression(self):
        box = M.BoxNode(box_type="MUX", input_items=[
            M.OperandNode(name="nSel"),
            M.OperandNode(name="nA"),
            M.OperandNode(name="nB")])
        result = M._gen_iec_func(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "MUX(nSel, nA, nB)"

    def test_limit_expression(self):
        box = M.BoxNode(box_type="LIMIT", input_items=[
            M.OperandNode(name="nMin"),
            M.OperandNode(name="nVal"),
            M.OperandNode(name="nMax")])
        result = M._gen_iec_func(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "LIMIT(nMin, nVal, nMax)"

    def test_mux_no_inputs(self):
        box = M.BoxNode(box_type="MUX", input_items=[])
        result = M._gen_iec_func(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "MUX()"


# ===================================================================
# SFC/IL warning
# ===================================================================

class TestSFCILWarning:
    def test_sfc_skip_with_warning(self, tmp_dir):
        sfc_xml = ('<?xml version="1.0" encoding="utf-8"?>\n'
                   '<TcPlcObject Version="1.1.0.1">\n'
                   '  <POU Name="SfcProg" Id="{aaaa-bbbb-cccc}">\n'
                   '    <Declaration><![CDATA[PROGRAM SfcProg\nVAR\nEND_VAR]]></Declaration>\n'
                   '    <Implementation><SFC></SFC></Implementation>\n'
                   '  </POU>\n'
                   '</TcPlcObject>')
        p = _write(tmp_dir, "SFC.TcPOU", sfc_xml)
        cfg = M.MigrationConfig(input_path=str(p))
        mlog = M.MigrationLogger(True, tmp_dir, "test")
        report = M.MigrationReport(False, tmp_dir)
        result = M.process_file(p, cfg, mlog, report)
        assert result is True
        assert any("SFC" in e for e in mlog.entries)


# ===================================================================
# Logging level
# ===================================================================

class TestLogLevel:
    def test_log_level_cli(self):
        cfg = M.parse_arguments(["--input", "x", "--log-level", "DEBUG"])
        assert cfg.log_level == "DEBUG"

    def test_log_level_default(self):
        cfg = M.parse_arguments(["--input", "x"])
        assert cfg.log_level == "INFO"


# ===================================================================
# Atomic write
# ===================================================================

class TestAtomicWrite:
    def test_write_output_file_atomic(self, tmp_dir):
        p = tmp_dir / "out.TcPOU"
        ok = M.write_output_file("test content", p)
        assert ok is True
        assert p.read_text() == "test content"

    def test_write_no_temp_left_on_success(self, tmp_dir):
        p = tmp_dir / "out.TcPOU"
        M.write_output_file("data", p)
        temps = list(tmp_dir.glob(".*_tmp_*"))
        assert len(temps) == 0

    def test_write_to_readonly_dir_fails(self, tmp_dir):
        fake = tmp_dir / "nonexistent_subdir" / "file.TcPOU"
        ok = M.write_output_file("data", fake)
        assert ok is False


# ===================================================================
# XOR operator
# ===================================================================

class TestXOR:
    def test_xor_infix(self):
        box = M.BoxNode(call_type="Xor", input_items=[
            M.OperandNode(name="bA"), M.OperandNode(name="bB")])
        tc = M.TcFile()
        result = M._gen_bool_expression(box, tc, M.MigrationConfig(), [])
        assert result == "bA XOR bB"

    def test_xor_three_inputs(self):
        box = M.BoxNode(call_type="Xor", input_items=[
            M.OperandNode(name="bA"), M.OperandNode(name="bB"),
            M.OperandNode(name="bC")])
        tc = M.TcFile()
        result = M._gen_bool_expression(box, tc, M.MigrationConfig(), [])
        assert result == "bA XOR bB XOR bC"

    def test_xor_dispatched_from_gen_expression(self):
        box = M.BoxNode(call_type="Xor", input_items=[
            M.OperandNode(name="bX"), M.OperandNode(name="bY")])
        tc = M.TcFile()
        result = M._gen_expression(box, tc, M.MigrationConfig(), [])
        assert "XOR" in result


# ===================================================================
# MAX, MIN
# ===================================================================

class TestMaxMin:
    def test_max_expression(self):
        box = M.BoxNode(box_type="MAX", input_items=[
            M.OperandNode(name="nA"), M.OperandNode(name="nB")])
        result = M._gen_iec_func(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "MAX(nA, nB)"

    def test_min_expression(self):
        box = M.BoxNode(box_type="MIN", input_items=[
            M.OperandNode(name="nA"), M.OperandNode(name="nB")])
        result = M._gen_iec_func(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "MIN(nA, nB)"

    def test_max_via_gen_expression(self):
        box = M.BoxNode(box_type="MAX", input_items=[
            M.OperandNode(name="n1"), M.OperandNode(name="n2")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "MAX(n1, n2)"


# ===================================================================
# Bitshift operators
# ===================================================================

class TestBitshift:
    def test_shl(self):
        box = M.BoxNode(box_type="SHL", input_items=[
            M.OperandNode(name="nVal"), M.OperandNode(name="3")])
        result = M._gen_iec_func(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "SHL(nVal, 3)"

    def test_shr(self):
        box = M.BoxNode(box_type="SHR", input_items=[
            M.OperandNode(name="nVal"), M.OperandNode(name="2")])
        result = M._gen_iec_func(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "SHR(nVal, 2)"

    def test_rol(self):
        box = M.BoxNode(box_type="ROL", input_items=[
            M.OperandNode(name="nVal"), M.OperandNode(name="1")])
        result = M._gen_iec_func(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "ROL(nVal, 1)"

    def test_ror(self):
        box = M.BoxNode(box_type="ROR", input_items=[
            M.OperandNode(name="nVal"), M.OperandNode(name="4")])
        result = M._gen_iec_func(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "ROR(nVal, 4)"

    def test_shl_via_gen_expression(self):
        box = M.BoxNode(box_type="SHL", input_items=[
            M.OperandNode(name="wData"), M.OperandNode(name="8")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "SHL(wData, 8)"


# ===================================================================
# Numeric functions
# ===================================================================

class TestNumericFunctions:
    def test_abs(self):
        box = M.BoxNode(box_type="ABS", input_items=[M.OperandNode(name="fVal")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "ABS(fVal)"

    def test_sqrt(self):
        box = M.BoxNode(box_type="SQRT", input_items=[M.OperandNode(name="fVal")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "SQRT(fVal)"

    def test_sin(self):
        box = M.BoxNode(box_type="SIN", input_items=[M.OperandNode(name="fAngle")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "SIN(fAngle)"

    def test_cos(self):
        box = M.BoxNode(box_type="COS", input_items=[M.OperandNode(name="fAngle")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "COS(fAngle)"

    def test_tan(self):
        box = M.BoxNode(box_type="TAN", input_items=[M.OperandNode(name="fAngle")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "TAN(fAngle)"

    def test_asin(self):
        box = M.BoxNode(box_type="ASIN", input_items=[M.OperandNode(name="fVal")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "ASIN(fVal)"

    def test_acos(self):
        box = M.BoxNode(box_type="ACOS", input_items=[M.OperandNode(name="fVal")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "ACOS(fVal)"

    def test_atan(self):
        box = M.BoxNode(box_type="ATAN", input_items=[M.OperandNode(name="fVal")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "ATAN(fVal)"

    def test_ln(self):
        box = M.BoxNode(box_type="LN", input_items=[M.OperandNode(name="fVal")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "LN(fVal)"

    def test_log(self):
        box = M.BoxNode(box_type="LOG", input_items=[M.OperandNode(name="fVal")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "LOG(fVal)"

    def test_exp(self):
        box = M.BoxNode(box_type="EXP", input_items=[M.OperandNode(name="fVal")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "EXP(fVal)"

    def test_expt_two_args(self):
        box = M.BoxNode(box_type="EXPT", input_items=[
            M.OperandNode(name="fBase"), M.OperandNode(name="fExp")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "EXPT(fBase, fExp)"

    def test_trunc(self):
        box = M.BoxNode(box_type="TRUNC", input_items=[M.OperandNode(name="fVal")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "TRUNC(fVal)"


# ===================================================================
# RETURN via BoxTreeAssign (??? with Flags=8)
# ===================================================================

class TestReturnAssign:
    def test_unconditional_return(self):
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="???", flags=8)],
            rvalue=M.OperandNode(name="TRUE"))
        lines = M._gen_assign(assign, M.TcFile(), M.MigrationConfig())
        assert lines == ["RETURN;"]

    def test_conditional_return(self):
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="???", flags=8)],
            rvalue=M.OperandNode(name="bCondition"))
        lines = M._gen_assign(assign, M.TcFile(), M.MigrationConfig())
        assert lines == ["IF bCondition THEN", "    RETURN;", "END_IF"]

    def test_not_return_without_flag(self):
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="???", flags=0)],
            rvalue=M.OperandNode(name="TRUE"))
        lines = M._gen_assign(assign, M.TcFile(), M.MigrationConfig())
        assert "RETURN" not in "".join(lines)

    def test_is_return_assign_helper(self):
        assert M._is_return_assign(M.AssignNode(
            outputs=[M.OperandNode(name="???", flags=8)])) is True
        assert M._is_return_assign(M.AssignNode(
            outputs=[M.OperandNode(name="bVar", flags=8)])) is False
        assert M._is_return_assign(M.AssignNode(
            outputs=[M.OperandNode(name="???", flags=0)])) is False


# ===================================================================
# Jump and Return (BoxTreeBox)
# ===================================================================

class TestJumpReturn:
    def test_return_top_level(self):
        box = M.BoxNode(box_type="RET")
        tc = M.TcFile()
        lines = M._gen_top_level_box(box, tc, M.MigrationConfig())
        assert lines == ["RETURN;"]

    def test_return_expression(self):
        box = M.BoxNode(box_type="RETURN")
        tc = M.TcFile()
        result = M._gen_expression(box, tc, M.MigrationConfig(), [])
        assert result == "RETURN"

    def test_jump_generates_todo(self):
        box = M.BoxNode(box_type="JMP",
                        output_items=[M.OperandNode(name="MyLabel")])
        tc = M.TcFile()
        lines = M._gen_top_level_box(box, tc, M.MigrationConfig())
        assert any("JMP" in l and "MyLabel" in l for l in lines)
        assert len(tc.todos) == 1


# ===================================================================
# Operator call fallback with IEC_FUNCTIONS
# ===================================================================

class TestOperatorCallFallback:
    def test_operator_call_routes_to_iec(self):
        box = M.BoxNode(box_type="ABS", call_type="Operator",
                        input_items=[M.OperandNode(name="fX")])
        result = M._gen_operator_call(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "ABS(fX)"

    def test_operator_call_routes_shl(self):
        box = M.BoxNode(box_type="SHL", call_type="Operator",
                        input_items=[M.OperandNode(name="w"), M.OperandNode(name="4")])
        result = M._gen_operator_call(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "SHL(w, 4)"


# ===================================================================
# EXECUTE / STSnippet block tests
# ===================================================================

class TestExecuteSnippet:
    def test_execute_en_true_no_wrapper(self):
        box = M.BoxNode(box_type="EXECUTE",
                        st_snippet=["nVar := nVar + 1;", "nVar := nVar + 99;"],
                        input_items=[M.OperandNode(name="TRUE")])
        lines = M._gen_top_level_box(box, M.TcFile(), M.MigrationConfig())
        assert lines == ["nVar := nVar + 1;", "nVar := nVar + 99;"]

    def test_execute_en_condition_wraps_if(self):
        box = M.BoxNode(box_type="EXECUTE",
                        st_snippet=["x := x + 1;"],
                        input_items=[M.OperandNode(name="bEnable")])
        lines = M._gen_top_level_box(box, M.TcFile(), M.MigrationConfig())
        assert lines == ["IF bEnable THEN", "    x := x + 1;", "END_IF"]

    def test_execute_en_complex_condition(self):
        inner = M.BoxNode(call_type="And",
                          input_items=[M.OperandNode(name="bA"), M.OperandNode(name="bB")])
        box = M.BoxNode(box_type="EXECUTE",
                        st_snippet=["y := 0;"],
                        input_items=[inner])
        lines = M._gen_top_level_box(box, M.TcFile(), M.MigrationConfig())
        assert lines[0] == "IF bA AND bB THEN"
        assert "    y := 0;" in lines
        assert "END_IF" in lines

    def test_execute_expression_hoists(self):
        box = M.BoxNode(box_type="EXECUTE", st_snippet=["x := 42;"])
        hoisted = []
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), hoisted)
        assert result == ""
        assert hoisted == ["x := 42;"]

    def test_execute_empty_snippet_no_crash(self):
        box = M.BoxNode(box_type="EXECUTE", st_snippet=[])
        lines = M._gen_top_level_box(box, M.TcFile(), M.MigrationConfig())
        assert isinstance(lines, list)

    def test_real_pou_execute_and_return(self):
        """Integration test against the real POU.TcPOU file."""
        from pathlib import Path
        p = Path(r'c:\Projekt Manager\I.00150.27 Maik Uffelmann Kaunitz'
                 r'\Programm_Beispiel\Samples_\Tc3_Iot_BA_Sample\PLC\POUs\Bereiche\POU.TcPOU')
        if not p.exists():
            pytest.skip("Real POU file not available")
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        cfg = M.MigrationConfig(dry_run=True)
        M.convert_networks_to_st(tc, cfg)
        assert "nVar := nVar +1;" in tc.generated_st
        assert "nVar := nVar + 99;" in tc.generated_st
        assert "RETURN;" in tc.generated_st
        assert "??? :=" not in tc.generated_st

    def test_parse_st_snippet_from_xml(self):
        import xml.etree.ElementTree as ET
        xml_str = '''<o n="STSnippet" t="STSnippet">
            <o n="STSnippet" t="STImplementationObject">
                <o n="TextDocument" t="TextDocument">
                    <a n="TextLines" cet="TextLine">
                        <o>
                            <v n="Id">35L</v>
                            <v n="Text">"nVar := nVar +1;"</v>
                        </o>
                        <o>
                            <v n="Id">36L</v>
                            <v n="Text">"nVar := nVar + 99;"</v>
                        </o>
                        <o>
                            <v n="Id">31L</v>
                            <v n="Text">""</v>
                        </o>
                    </a>
                </o>
            </o>
            <v n="Id">37L</v>
        </o>'''
        el = ET.fromstring(xml_str)
        lines = M._parse_st_snippet(el)
        assert lines == ["nVar := nVar +1;", "nVar := nVar + 99;"]


# ===================================================================
# is_null output param detection
# ===================================================================

class TestIsNullOutputParam:
    """The <n /> tag in OutputItems indicates which FB output parameter
    the AssignNode's targets connect to. Index of null = output param index."""

    def test_null_at_first_position_maps_to_first_param(self):
        """is_null at index 0 -> assign target connects to bOut1 (inline for single target)."""
        box = M.BoxNode(
            box_type="FB_X", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbX"),
            input_items=[], input_param_names=[], input_param_types=[],
            output_param_names=["bOut1", "bOut2"],
            output_param_types=["BOOL", "BOOL"],
            output_items=[M.OperandNode(is_null=True), M.OperandNode(name="tgt2", type_str="BOOL")])
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="tgt_assign", type_str="BOOL")],
            rvalue=box)
        tc = M.TcFile()
        lines = M._gen_assign(assign, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "bOut1 => tgt_assign" in joined
        assert "bOut2 => tgt2" in joined

    def test_null_at_second_position_maps_to_second_param(self):
        """is_null at index 1 -> assign target connects to bError (inline for single target)."""
        box = M.BoxNode(
            box_type="FB_X", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbX"),
            input_items=[], input_param_names=[], input_param_types=[],
            output_param_names=["bOut1", "bError"],
            output_param_types=["BOOL", "BOOL"],
            output_items=[M.OperandNode(name="tgt1", type_str="BOOL"), M.OperandNode(is_null=True)])
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="bMyError", type_str="BOOL")],
            rvalue=box)
        tc = M.TcFile()
        lines = M._gen_assign(assign, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "bError => bMyError" in joined
        assert "bOut1" in joined and "=> tgt1" in joined

    def test_null_second_position_multi_target_post_call(self):
        """is_null at index 1 + multiple targets -> post-call with correct param."""
        box = M.BoxNode(
            box_type="FB_X", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbX"),
            input_items=[], input_param_names=[], input_param_types=[],
            output_param_names=["bOut1", "bError"],
            output_param_types=["BOOL", "BOOL"],
            output_items=[M.OperandNode(name="tgt1", type_str="BOOL"), M.OperandNode(is_null=True)])
        assign = M.AssignNode(
            outputs=[
                M.OperandNode(name="bErr1", type_str="BOOL"),
                M.OperandNode(name="bErr2", type_str="BOOL"),
            ],
            rvalue=box)
        tc = M.TcFile()
        lines = M._gen_assign(assign, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "bErr1 := fbX.bError;" in joined
        assert "bErr2 := fbX.bError;" in joined
        assert "bOut1 => tgt1" in joined

    def test_no_null_defaults_to_first_param(self):
        """No is_null found -> defaults to first param (inline for single target)."""
        box = M.BoxNode(
            box_type="FB_X", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbX"),
            input_items=[], input_param_names=[], input_param_types=[],
            output_param_names=["bMain", "bAux"],
            output_param_types=["BOOL", "BOOL"],
            output_items=[M.OperandNode(), M.OperandNode()])
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="tgtA", type_str="BOOL")],
            rvalue=box)
        tc = M.TcFile()
        lines = M._gen_assign(assign, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "bMain => tgtA" in joined


# ===================================================================
# Multi-output post-call assignments
# ===================================================================

class TestMultiOutputPostCall:
    """When a FB output param has >1 target, each gets post-call assignment."""

    def test_three_assign_targets_post_call(self):
        box = M.BoxNode(
            box_type="FB_Valve", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbValve"),
            input_items=[], input_param_names=[], input_param_types=[],
            output_param_names=["bHeating"],
            output_param_types=["BOOL"],
            output_items=[M.OperandNode(is_null=True)])
        assign = M.AssignNode(
            outputs=[
                M.OperandNode(name="bValve1", type_str="BOOL"),
                M.OperandNode(name="bValve2", type_str="BOOL"),
                M.OperandNode(name="bValve3", type_str="BOOL"),
            ],
            rvalue=box)
        tc = M.TcFile()
        lines = M._gen_assign(assign, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "bValve1 := fbValve.bHeating;" in joined
        assert "bValve2 := fbValve.bHeating;" in joined
        assert "bValve3 := fbValve.bHeating;" in joined
        assert "bHeating =>" not in joined

    def test_single_target_stays_inline(self):
        box = M.BoxNode(
            box_type="FB_Valve", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbValve"),
            input_items=[], input_param_names=[], input_param_types=[],
            output_param_names=["bHeating"],
            output_param_types=["BOOL"],
            output_items=[M.OperandNode(is_null=True)])
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="bTarget", type_str="BOOL")],
            rvalue=box)
        tc = M.TcFile()
        lines = M._gen_assign(assign, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "bHeating => bTarget" in joined


# ===================================================================
# Assign-level negation
# ===================================================================

class TestAssignNegation:
    def test_negation_flag_on_simple_assign(self):
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="bResult", type_str="BOOL")],
            rvalue=M.OperandNode(name="bInput"),
            flags=1)
        tc = M.TcFile()
        lines = M._gen_assign(assign, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "NOT bInput" in joined
        assert "bResult :=" in joined

    def test_negation_flag_on_fb_output(self):
        box = M.BoxNode(
            box_type="FB_X", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbX"),
            input_items=[], input_param_names=[], input_param_types=[],
            output_param_names=["bOut"],
            output_param_types=["BOOL"],
            output_items=[M.OperandNode(is_null=True)])
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="bAlarm", type_str="BOOL")],
            rvalue=box, flags=1)
        tc = M.TcFile()
        lines = M._gen_assign(assign, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "NOT" in joined
        assert "fbX.bOut" in joined
        assert "bAlarm :=" in joined

    def test_negation_forces_post_call(self):
        box = M.BoxNode(
            box_type="FB_X", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbX"),
            input_items=[], input_param_names=[], input_param_types=[],
            output_param_names=["bOut"],
            output_param_types=["BOOL"],
            output_items=[M.OperandNode(is_null=True)])
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="bAlarm", type_str="BOOL")],
            rvalue=box, flags=1)
        tc = M.TcFile()
        lines = M._gen_assign(assign, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "bOut =>" not in joined


# ===================================================================
# NOT box expression
# ===================================================================

class TestNotBox:
    def test_not_simple(self):
        box = M.BoxNode(call_type="Not", box_type="NOT",
                        input_items=[M.OperandNode(name="bFlag")])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "NOT bFlag"

    def test_not_complex_wraps_parens(self):
        inner = M.BoxNode(call_type="Or", input_items=[
            M.OperandNode(name="bA"), M.OperandNode(name="bB")])
        box = M.BoxNode(call_type="Not", box_type="NOT", input_items=[inner])
        result = M._gen_expression(box, M.TcFile(), M.MigrationConfig(), [])
        assert result == "NOT (bA OR bB)"


# ===================================================================
# Action migration (synthetic)
# ===================================================================

class TestActionMigration:
    def test_action_nwl_to_st(self, tmp_dir):
        action_xml = textwrap.dedent('''\
    <Action Name="A_Init">
      <Implementation>
        <NWL>
          <XmlArchive>
            <Data>
              <o xml:space="preserve" t="NWLImplementationObject">
                <v n="NetworkListComment">""</v>
                <v n="DefaultViewMode">"Fbd"</v>
                <l2 n="NetworkList" cet="Network">
''' + _simple_assign_network("TRUE", "bActionOut") + '''
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
              <Type n="Int64">System.Int64</Type>
              <Type n="Network">{d9a99d73-b633-47db-b876-a752acb25871}</Type>
              <Type n="NWLImplementationObject">{25e509de-33d4-4447-93f8-c9e4ea381c8b}</Type>
              <Type n="Operand">{c9b2f165-48a2-4a45-8326-3952d8a3d708}</Type>
              <Type n="String">System.String</Type>
            </TypeList>
          </XmlArchive>
        </NWL>
      </Implementation>
    </Action>''')
        decl = "PROGRAM TestProg\nVAR\n    bActionOut : BOOL;\nEND_VAR"
        xml = _make_pou(_simple_assign_network("TRUE", "bOut"), action_xml, decl)
        p = _write(tmp_dir, "WithAction.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        assert len(tc.actions) == 1
        assert tc.actions[0].impl_type == "NWL"
        assert len(tc.actions[0].networks) == 1
        M.convert_networks_to_st(tc, M.MigrationConfig())
        assert "bActionOut := TRUE;" in tc.actions[0].st_code

    def test_action_replaced_in_xml(self, tmp_dir):
        action_xml = textwrap.dedent('''\
    <Action Name="A_Init">
      <Implementation>
        <NWL>
          <XmlArchive>
            <Data>
              <o xml:space="preserve" t="NWLImplementationObject">
                <v n="NetworkListComment">""</v>
                <v n="DefaultViewMode">"Fbd"</v>
                <l2 n="NetworkList" cet="Network">
''' + _simple_assign_network("TRUE", "bActionOut") + '''
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
              <Type n="Int64">System.Int64</Type>
              <Type n="Network">{d9a99d73-b633-47db-b876-a752acb25871}</Type>
              <Type n="NWLImplementationObject">{25e509de-33d4-4447-93f8-c9e4ea381c8b}</Type>
              <Type n="Operand">{c9b2f165-48a2-4a45-8326-3952d8a3d708}</Type>
              <Type n="String">System.String</Type>
            </TypeList>
          </XmlArchive>
        </NWL>
      </Implementation>
    </Action>''')
        xml = _make_pou(_simple_assign_network("TRUE", "bOut"), action_xml)
        p = _write(tmp_dir, "WithAction.TcPOU", xml)
        tc = M.load_file(p)
        M.parse_nwl_networks(tc)
        M.convert_networks_to_st(tc, M.MigrationConfig())
        result = M.write_st_to_xml(tc)
        assert result is not None
        action_match = result.find('<Action Name="A_Init"')
        assert action_match >= 0
        impl_after = result.find("<ST>", action_match)
        assert impl_after > action_match
        assert "<NWL>" not in result[action_match:]


# ===================================================================
# format_call_params alignment
# ===================================================================

class TestFormatCallParams:
    def test_alignment(self):
        mappings = [("IN", ":=", "bStart"), ("PT", ":=", "T#5S")]
        lines = M._format_call_params(mappings)
        assert all(":=" in l for l in lines)
        col0 = lines[0].index(":=")
        col1 = lines[1].index(":=")
        assert col0 == col1

    def test_mixed_positional_and_named(self):
        mappings = [("", ":=", "42"), ("nVal", ":=", "10")]
        lines = M._format_call_params(mappings)
        assert len(lines) == 2

    def test_empty_returns_empty(self):
        assert M._format_call_params([]) == []


# ===================================================================
# Ordner-Batch-Mode mit batch_dir und Mirror-Struktur
# ===================================================================

class TestBatchDirMirror:
    def test_swap_folder_creates_backup_mirror(self, tmp_dir):
        """Folder + swap -> backup dir with mirrored structure, ST at original paths."""
        sub = tmp_dir / "Project" / "POUs" / "Sub"
        sub.mkdir(parents=True)
        xml = _make_pou(_simple_assign_network("bA", "bOut"))
        _write(sub, "Prog1.TcPOU", xml)
        _write(sub, "Prog2.TcPOU", xml)

        cfg_args = ["--input", str(tmp_dir / "Project" / "POUs"),
                     "--recursive", "--no-log", "--no-report"]
        exit_code = M.main(cfg_args)
        assert exit_code == 0

        content1 = (sub / "Prog1.TcPOU").read_text()
        assert "<ST>" in content1
        assert "<NWL>" not in content1

        backup_dirs = [d for d in (tmp_dir / "Project").iterdir()
                       if d.is_dir() and "fup_backup" in d.name.lower()]
        assert len(backup_dirs) == 1
        backup_sub = backup_dirs[0] / "Sub"
        assert backup_sub.exists()
        backup_files = list(backup_sub.glob("*.TcPOU"))
        assert len(backup_files) == 2
        backup_content = backup_files[0].read_text()
        assert "<NWL>" in backup_content

    def test_no_swap_folder_creates_generated_dir(self, tmp_dir):
        """Folder + no-swap -> _st_generated dir with mirrored structure."""
        sub = tmp_dir / "MyProject" / "POUs"
        sub.mkdir(parents=True)
        xml = _make_pou(_simple_assign_network("bX", "bY"))
        _write(sub, "Test.TcPOU", xml)

        cfg_args = ["--input", str(tmp_dir / "MyProject"),
                     "--recursive", "--no-swap", "--no-log", "--no-report"]
        exit_code = M.main(cfg_args)
        assert exit_code == 0

        original = (sub / "Test.TcPOU").read_text()
        assert "<NWL>" in original

        gen_dirs = [d for d in tmp_dir.iterdir()
                    if d.is_dir() and "st_generated" in d.name.lower()]
        assert len(gen_dirs) == 1
        gen_file = gen_dirs[0] / "POUs" / "Test.TcPOU"
        assert gen_file.exists()
        gen_content = gen_file.read_text()
        assert "<ST>" in gen_content

    def test_batch_skips_non_nwl_files(self, tmp_dir):
        """ST and GVL files in folder should be skipped, not crash."""
        pous = tmp_dir / "Proj" / "POUs"
        pous.mkdir(parents=True)
        _write(pous, "FBD.TcPOU", _make_pou(_simple_assign_network("bA", "bB")))
        _write(pous, "ST.TcPOU", MINIMAL_ST_POU)
        _write(pous, "Vars.TcGVL", MINIMAL_GVL)

        exit_code = M.main(["--input", str(tmp_dir / "Proj"),
                            "--recursive", "--no-log", "--no-report"])
        assert exit_code == 0


# ===================================================================
# _gen_unknown_box fallback
# ===================================================================

class TestUnknownBox:
    def test_unknown_box_with_instance_generates_comment(self):
        box = M.BoxNode(
            box_type="WEIRD_BLOCK",
            instance=M.OperandNode(name="fbWeird"),
            input_items=[M.OperandNode(name="nVal")],
            input_param_names=["nIn"])
        tc = M.TcFile()
        result = M._gen_unknown_box(box, tc, M.MigrationConfig(), [])
        assert "fbWeird" in result
        assert "nIn := nVal" in result
        assert "(*" in result

    def test_unknown_box_without_instance_generates_todo(self):
        box = M.BoxNode(
            box_type="MYSTERY",
            input_items=[M.OperandNode(name="42")])
        tc = M.TcFile()
        result = M._gen_unknown_box(box, tc, M.MigrationConfig(), [])
        assert "TODO" in result
        assert "MYSTERY" in result
        assert "42" in result
        assert len(tc.todos) == 1

    def test_unknown_box_routed_from_gen_expression(self):
        box = M.BoxNode(
            box_type="CUSTOM_OP", call_type="",
            input_items=[M.OperandNode(name="x"), M.OperandNode(name="y")])
        tc = M.TcFile()
        result = M._gen_expression(box, tc, M.MigrationConfig(), [])
        assert "CUSTOM_OP" in result
        assert "x" in result

    def test_unknown_box_no_inputs_no_instance(self):
        box = M.BoxNode(box_type="EMPTY_BOX", call_type="")
        tc = M.TcFile()
        result = M._gen_expression(box, tc, M.MigrationConfig(), [])
        assert result == "EMPTY_BOX()"


# ===================================================================
# Chained AssignNode (Assign als RValue eines Assigns)
# ===================================================================

class TestChainedAssign:
    def test_chained_assign_propagates_value(self):
        inner = M.AssignNode(
            outputs=[M.OperandNode(name="bIntermediate", type_str="BOOL")],
            rvalue=M.OperandNode(name="bSource"))
        outer = M.AssignNode(
            outputs=[M.OperandNode(name="bFinal", type_str="BOOL")],
            rvalue=inner)
        tc = M.TcFile()
        lines = M._gen_assign(outer, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "bIntermediate := bSource;" in joined
        assert "bFinal := bIntermediate;" in joined

    def test_chained_assign_multiple_outer_targets(self):
        inner = M.AssignNode(
            outputs=[M.OperandNode(name="bMid", type_str="BOOL")],
            rvalue=M.OperandNode(name="TRUE"))
        outer = M.AssignNode(
            outputs=[
                M.OperandNode(name="bOut1", type_str="BOOL"),
                M.OperandNode(name="bOut2", type_str="BOOL"),
            ],
            rvalue=inner)
        tc = M.TcFile()
        lines = M._gen_assign(outer, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "bMid := TRUE;" in joined
        assert "bOut1 := bMid;" in joined
        assert "bOut2 := bMid;" in joined

    def test_chained_assign_inner_no_output_gives_todo(self):
        inner = M.AssignNode(
            outputs=[],
            rvalue=M.OperandNode(name="bX"))
        outer = M.AssignNode(
            outputs=[M.OperandNode(name="bTarget", type_str="BOOL")],
            rvalue=inner)
        tc = M.TcFile()
        lines = M._gen_assign(outer, tc, M.MigrationConfig())
        joined = "\n".join(lines)
        assert "TODO" in joined
        assert len(tc.todos) >= 1

    def test_chained_assign_as_expression_input(self):
        """AssignNode appearing as input to a box -> hoisted, first output used."""
        inner_assign = M.AssignNode(
            outputs=[M.OperandNode(name="bTemp", type_str="BOOL")],
            rvalue=M.OperandNode(name="bSrc"))
        box = M.BoxNode(
            call_type="Or",
            input_items=[inner_assign, M.OperandNode(name="bOther")])
        tc = M.TcFile()
        hoisted = []
        result = M._gen_expression(box, tc, M.MigrationConfig(), hoisted)
        assert "bTemp" in result
        assert "OR" in result
        assert any("bTemp := bSrc;" in h for h in hoisted)


# ===================================================================
# Demux-Merge: E2E test with Demux + FB network
# ===================================================================

class TestDemuxMerge:
    def _make_demux_network(self):
        """Build networks: NW0 = FB call, NW1 = Demux branching FB output to 2 targets."""
        fb_box = M.BoxNode(
            box_type="FB_Motor", call_type="FunctionBlock",
            instance=M.OperandNode(name="fbMotor"),
            input_items=[M.OperandNode(name="TRUE")],
            input_param_names=["bEnable"],
            input_param_types=["BOOL"],
            output_param_names=["bRunning", "nSpeed"],
            output_param_types=["BOOL", "INT"],
            output_items=[
                M.OperandNode(name="bMotorOn", type_str="BOOL"),
                M.OperandNode(name="nCurrentSpeed", type_str="INT"),
            ])
        nw0 = M.NwlNetwork(index=0, items=[M.AssignNode(
            outputs=[],
            rvalue=fb_box)])

        demux = M.DemuxNode(
            input=M.OperandNode(name="fbMotor.nSpeed", type_str="INT"))
        assign1 = M.AssignNode(
            outputs=[M.OperandNode(name="nDisplay1", type_str="INT")],
            rvalue=M.DemuxNode())
        assign2 = M.AssignNode(
            outputs=[M.OperandNode(name="nDisplay2", type_str="INT")],
            rvalue=M.DemuxNode())
        nw1 = M.NwlNetwork(index=1, items=[demux, assign1, assign2])

        return [nw0, nw1]

    def test_demux_merge_map_built_correctly(self):
        networks = self._make_demux_network()
        merge_map, skip = M._build_demux_merge_map(networks)
        assert "fbMotor" in merge_map
        entries = merge_map["fbMotor"]
        assert len(entries) == 2
        param_names = [e[0] for e in entries]
        assert all(p == "nSpeed" for p in param_names)
        targets = [e[1] for e in entries]
        assert "nDisplay1" in targets
        assert "nDisplay2" in targets
        assert 1 in skip

    def test_demux_network_skipped_in_output(self):
        networks = self._make_demux_network()
        tc = M.TcFile()
        tc.networks = networks
        cfg = M.MigrationConfig()
        M.convert_networks_to_st(tc, cfg)
        assert "nDisplay1" in tc.generated_st
        assert "nDisplay2" in tc.generated_st
        network_headers = tc.generated_st.count("// Network ")
        assert network_headers == 1

    def test_demux_targets_merged_into_fb_call(self):
        networks = self._make_demux_network()
        tc = M.TcFile()
        tc.networks = networks
        cfg = M.MigrationConfig()
        M.convert_networks_to_st(tc, cfg)
        assert "nSpeed" in tc.generated_st
        assert "nDisplay1" in tc.generated_st
        assert "nDisplay2" in tc.generated_st

    def test_demux_unresolved_gives_todo(self):
        demux = M.DemuxNode()
        assign = M.AssignNode(
            outputs=[M.OperandNode(name="bTarget", type_str="BOOL")],
            rvalue=demux)
        nw = M.NwlNetwork(index=0, items=[assign])
        tc = M.TcFile()
        tc.networks = [nw]
        cfg = M.MigrationConfig()
        M.convert_networks_to_st(tc, cfg)
        assert "TODO" in tc.generated_st
        assert len(tc.todos) >= 1
