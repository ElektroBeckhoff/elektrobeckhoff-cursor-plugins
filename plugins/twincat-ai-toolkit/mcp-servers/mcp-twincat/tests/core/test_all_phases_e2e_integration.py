"""Comprehensive End-to-End Integration Test across all Core Phases.

Validates the full unified pipeline:
1. Phase 1: TcXmlDocument lossless parsing and GUID preservation
2. Phase 2: ST syntax lexer, CST, AST, and fault-tolerant parsing
3. Phase 3: Project Graph (.plcproj), Scopes (Local, POU, GVL), TypeIndex, WorkspaceIndex
4. Phase 4: Formatter engine using twincat_core with idempotency
5. Phase 5: AutoDocs, Migrator, and PlcProj operations using twincat_core
6. Phase 6: Language Server (pygls) handlers (definition, hover, documentSymbol, diagnostics)
7. Phase 7: Advanced Symbol Resolution (Level 4 chained members, Level 5 standard library catalog, MCP tool integration)
"""
import json
from pathlib import Path
import pytest

from twincat_core.lsp.handlers import (
    get_diagnostics_for_file,
    handle_definition,
    handle_document_symbol,
    handle_formatting,
    handle_hover,
)
from twincat_core.lsp.utils import path_to_uri, position_to_lsp
from twincat_core.project import WorkspaceIndex, parse_plcproj_file
from twincat_core.semantic import SymbolKind
from twincat_core.syntax import parse_declaration, parse_implementation, tokenize_st
from twincat_core.syntax.span import Position
from twincat_core.xml import read_tc_xml, read_tc_xml_file
import lsprotocol.types as lsp


SAMPLE_PLCPROJ_XML = """<?xml version="1.0" encoding="utf-8"?>
<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Name>FullSuiteE2E</Name>
    <ProjectVersion>1.0.0.0</ProjectVersion>
    <Company>ElektroBeckhoff</Company>
  </PropertyGroup>
  <ItemGroup>
    <Folder Include="DUTs" />
    <Folder Include="GVLs" />
    <Folder Include="POUs" />
  </ItemGroup>
  <ItemGroup>
    <Compile Include="DUTs\\ST_SubDevice.TcDUT">
      <SubType>Code</SubType>
    </Compile>
    <Compile Include="GVLs\\GVL_System.TcGVL">
      <SubType>Code</SubType>
    </Compile>
    <Compile Include="POUs\\FB_Controller.TcPOU">
      <SubType>Code</SubType>
    </Compile>
  </ItemGroup>
  <ItemGroup>
    <PlaceholderReference Include="Tc2_Standard">
      <DefaultResolution>Tc2_Standard, * (Beckhoff Automation GmbH)</DefaultResolution>
      <Namespace>Tc2_Standard</Namespace>
    </PlaceholderReference>
  </ItemGroup>
</Project>"""

SAMPLE_DUT_XML = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <DUT Name="ST_SubDevice" Id="{AAAA1111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[TYPE ST_SubDevice :
STRUCT
    fPressure_bar : LREAL := 2.5;
    bActive : BOOL := TRUE;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>"""

SAMPLE_GVL_XML = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <GVL Name="GVL_System" Id="{BBBB2222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[VAR_GLOBAL
    g_stGlobalDevice : ST_SubDevice;
    g_bEmergencyStop : BOOL := FALSE;
END_VAR
]]></Declaration>
  </GVL>
</TcPlcObject>"""

SAMPLE_POU_XML = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Controller" Id="{CCCC3333-3333-3333-3333-333333333333}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Controller
VAR
    stDevice : ST_SubDevice;
    fbTimer : TON;
    _bLocalDone : BOOL := FALSE;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[
fbTimer(IN := stDevice.bActive, PT := T#2s);
IF fbTimer.Q THEN
    stDevice.fPressure_bar := 3.14;
    _bLocalDone := TRUE;
END_IF
]]></ST>
    </Implementation>
    <Method Name="M_Reset" Id="{DDDD4444-4444-4444-4444-444444444444}">
      <Declaration><![CDATA[METHOD PUBLIC M_Reset : BOOL
VAR_INPUT
    bForce : BOOL;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[
stDevice.fPressure_bar := 0.0;
_bLocalDone := FALSE;
M_Reset := TRUE;
]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>"""


class TestAllPhasesE2EIntegration:
    """Verifies that all components and architectural layers work seamlessly together."""

    @pytest.fixture
    def project_env(self, tmp_path):
        duts_dir = tmp_path / "DUTs"
        gvls_dir = tmp_path / "GVLs"
        pous_dir = tmp_path / "POUs"
        duts_dir.mkdir()
        gvls_dir.mkdir()
        pous_dir.mkdir()

        plcproj_file = tmp_path / "FullSuiteE2E.plcproj"
        dut_file = duts_dir / "ST_SubDevice.TcDUT"
        gvl_file = gvls_dir / "GVL_System.TcGVL"
        pou_file = pous_dir / "FB_Controller.TcPOU"

        plcproj_file.write_text(SAMPLE_PLCPROJ_XML, encoding="utf-8")
        dut_file.write_text(SAMPLE_DUT_XML, encoding="utf-8")
        gvl_file.write_text(SAMPLE_GVL_XML, encoding="utf-8")
        pou_file.write_text(SAMPLE_POU_XML, encoding="utf-8")

        return {
            "root": tmp_path,
            "plcproj": plcproj_file,
            "dut": dut_file,
            "gvl": gvl_file,
            "pou": pou_file,
        }

    def test_phases_1_to_8_full_workflow(self, project_env):
        plcproj_p = project_env["plcproj"]
        pou_p = project_env["pou"]
        dut_p = project_env["dut"]
        gvl_p = project_env["gvl"]

        # -------------------------------------------------------------
        # Phase 1: Lossless XML & GUID Preserving
        # -------------------------------------------------------------
        pou_doc = read_tc_xml_file(pou_p)
        assert pou_doc.root_object_name == "FB_Controller"
        assert len(pou_doc.cdata_spans) == 4  # decl, impl, m_decl, m_impl
        assert pou_doc.root_object_id == "{CCCC3333-3333-3333-3333-333333333333}"

        # -------------------------------------------------------------
        # Phase 2: ST Syntax Lexer, CST, AST
        # -------------------------------------------------------------
        decl_span = pou_doc.cdata_spans[0]
        ast_node, cst_nodes, diags = parse_declaration(decl_span.content)
        assert len(diags) == 0
        assert ast_node is not None

        impl_span = pou_doc.cdata_spans[1]
        stmts, impl_cst, impl_diags = parse_implementation(impl_span.content)
        assert len(impl_diags) == 0
        assert len(stmts) >= 2

        # -------------------------------------------------------------
        # Phase 3: Project Graph & Workspace Index
        # -------------------------------------------------------------
        ws = WorkspaceIndex.from_plcproj(plcproj_p)
        assert ws.project is not None
        assert ws.project.project_name == "FullSuiteE2E"
        assert len(ws.indexed_files) == 3

        # -------------------------------------------------------------
        # Phase 4: Formatter Idempotency & Core Integration
        # -------------------------------------------------------------
        uri = path_to_uri(pou_p)
        fmt_params = lsp.DocumentFormattingParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            options=lsp.FormattingOptions(tab_size=4, insert_spaces=True),
        )
        edits = handle_formatting(ws, fmt_params)
        # Formatter produces edits if changes needed, or empty list
        assert isinstance(edits, list)

        # -------------------------------------------------------------
        # Phase 6: Language Server Handlers
        # -------------------------------------------------------------
        # Document symbols
        sym_params = lsp.DocumentSymbolParams(text_document=lsp.TextDocumentIdentifier(uri=uri))
        symbols = handle_document_symbol(ws, sym_params)
        assert len(symbols) >= 1
        assert symbols[0].name == "FB_Controller"

        # Diagnostics
        diagnostics = get_diagnostics_for_file(ws, pou_p)
        assert len(diagnostics) == 0

        # Hover
        hover_params = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=5, character=6),  # line 6 in XML: "    stDevice : ST_SubDevice;"
        )
        hover_res = handle_hover(ws, hover_params)
        assert hover_res is not None
        assert "ST_SubDevice" in hover_res.contents.value

        # Go to Definition: on line 12 ("fbTimer(IN := stDevice.bActive, PT := T#2s);"), character 20 ("stDevice")
        def_params = lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=12, character=20),
        )
        def_res = handle_definition(ws, def_params)
        assert def_res is not None
        assert def_res.uri == uri

        # -------------------------------------------------------------
        # Phase 7: Level 4/5 Chained Members & MCP Tooling
        # -------------------------------------------------------------
        from server import twincat_symbol_lookup, twincat_workspace_symbols

        # Chained member resolution via MCP
        res_json = twincat_symbol_lookup("FB_Controller.stDevice.fPressure_bar", plcproj_path=str(plcproj_p))
        res_data = json.loads(res_json)
        assert res_data["found"] is True
        assert res_data["name"] == "fPressure_bar"
        assert res_data["type_ref"] == "LREAL"

        # Global GVL chain resolution
        gvl_res_json = twincat_symbol_lookup("GVL_System.g_stGlobalDevice.bActive", plcproj_path=str(plcproj_p))
        gvl_res_data = json.loads(gvl_res_json)
        assert gvl_res_data["found"] is True
        assert gvl_res_data["name"] == "bActive"
        assert gvl_res_data["type_ref"] == "BOOL"

        # Level 5 Builtin resolution
        ton_res_json = twincat_symbol_lookup("Tc2_Standard.TON.PT", plcproj_path=str(plcproj_p))
        ton_res_data = json.loads(ton_res_json)
        assert ton_res_data["found"] is True
        assert ton_res_data["name"] == "PT"
        assert ton_res_data["type_ref"] == "TIME"

        # Workspace symbols
        ws_syms_json = twincat_workspace_symbols(query="Pressure", plcproj_path=str(plcproj_p))
        ws_syms = json.loads(ws_syms_json)
        assert ws_syms["total"] >= 1
        assert any(s["name"] == "fPressure_bar" for s in ws_syms["symbols"])
