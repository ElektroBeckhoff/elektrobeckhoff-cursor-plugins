"""Deep Edge-Cases, Syntax Error-Recovery, and Robustness Verification for twincat_core."""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from twincat_core.xml import (
    read_tc_xml,
    read_tc_xml_file,
    patch_declaration,
    patch_implementation,
    patch_method,
    patch_action,
    patch_by_filter,
    CdataKind,
)
from twincat_core.syntax import (
    parse_declaration,
    parse_implementation,
    tokenize_st,
    PouDecl,
    TypeDecl,
    VarBlock,
    BinaryExpr,
    MemberAccessExpr,
    DerefExpr,
    CallExpr,
)
from twincat_core.project import WorkspaceIndex
from twincat_core.semantic import (
    SymbolTable,
    TypeIndex,
    TypeDescriptor,
    Symbol,
    SymbolKind,
    SymbolResolver,
    Scope,
)
from twincat_core.projection.virtual_st import project_to_virtual_st, sync_virtual_st_to_xml
from twincat_core.projection.source_map import SourceMap


class TestDeepInheritanceAndShadowing:
    """Tests 3+ level OOP inheritance, method overrides, and variable shadowing."""

    def test_multi_level_inheritance_resolution(self):
        type_index = TypeIndex()
        symbol_table = SymbolTable()
        resolver = SymbolResolver(symbol_table, type_index)

        # Level 0: Base
        desc_base = TypeDescriptor(name="FB_Base", kind=SymbolKind.FUNCTION_BLOCK)
        sym_base_field = Symbol(name="fBaseParam", kind=SymbolKind.VARIABLE, span=None, type_ref="LREAL")
        sym_base_method = Symbol(name="M_BaseAction", kind=SymbolKind.METHOD, span=None, type_ref="BOOL")
        desc_base.add_field(sym_base_field)
        desc_base.add_method(sym_base_method)
        type_index.register_type(desc_base)

        # Level 1: Level1 EXTENDS Base
        desc_l1 = TypeDescriptor(name="FB_Level1", kind=SymbolKind.FUNCTION_BLOCK, extends_name="FB_Base")
        sym_l1_field = Symbol(name="nLevel1Count", kind=SymbolKind.VARIABLE, span=None, type_ref="INT")
        desc_l1.add_field(sym_l1_field)
        type_index.register_type(desc_l1)

        # Level 2: Level2 EXTENDS Level1
        desc_l2 = TypeDescriptor(name="FB_Level2", kind=SymbolKind.FUNCTION_BLOCK, extends_name="FB_Level1")
        sym_l2_field = Symbol(name="sLevel2Name", kind=SymbolKind.VARIABLE, span=None, type_ref="STRING")
        desc_l2.add_field(sym_l2_field)
        type_index.register_type(desc_l2)

        # Level 3: Level3 EXTENDS Level2
        desc_l3 = TypeDescriptor(name="FB_Level3", kind=SymbolKind.FUNCTION_BLOCK, extends_name="FB_Level2")
        sym_l3_field = Symbol(name="bLevel3Active", kind=SymbolKind.VARIABLE, span=None, type_ref="BOOL")
        desc_l3.add_field(sym_l3_field)
        type_index.register_type(desc_l3)

        # Verify inheritance chain
        chain = type_index.get_inheritance_chain("FB_Level3")
        assert chain == ["FB_Level2", "FB_Level1", "FB_Base"]

        # Resolve members across entire 4-deep inheritance stack
        assert resolver.resolve_member_access("FB_Level3", "bLevel3Active") == sym_l3_field
        assert resolver.resolve_member_access("FB_Level3", "sLevel2Name") == sym_l2_field
        assert resolver.resolve_member_access("FB_Level3", "nLevel1Count") == sym_l1_field
        assert resolver.resolve_member_access("FB_Level3", "fBaseParam") == sym_base_field
        assert resolver.resolve_member_access("FB_Level3", "M_BaseAction") == sym_base_method

    def test_local_variable_shadowing_global(self):
        symbol_table = SymbolTable()
        type_index = TypeIndex()
        resolver = SymbolResolver(symbol_table, type_index)

        # Global symbol
        sym_global = Symbol(name="nTargetSpeed", kind=SymbolKind.VARIABLE, span=None, type_ref="DINT")
        symbol_table.define_global(sym_global)

        # POU Scope with local shadow
        pou_sym = Symbol(name="FB_Drive", kind=SymbolKind.FUNCTION_BLOCK, span=None)
        pou_scope = symbol_table.create_pou_scope(pou_sym)
        sym_local = Symbol(name="nTargetSpeed", kind=SymbolKind.VARIABLE, span=None, type_ref="REAL")
        pou_scope.define(sym_local)

        # In Global scope, resolves to global
        assert resolver.resolve_identifier("nTargetSpeed", symbol_table.global_scope) == sym_global
        # In Local POU scope, resolves to local shadow
        assert resolver.resolve_identifier("nTargetSpeed", pou_scope) == sym_local


class TestSyntaxErrorRecoveryAndEdgeCases:
    """Tests parser resilience against syntax errors, recovery points, and complex expressions."""

    def test_syntax_recovery_on_malformed_statement(self):
        source = """
        nCount := nCount + 1;
        ??? malformed garbage token here @@@@ ;
        bFinished := TRUE;
        """
        stmts, cst_nodes, diags = parse_implementation(source)
        # Parser should recover to the next semicolon and parse bFinished := TRUE
        stmt_types = [type(s).__name__ for s in stmts]
        assert "AssignStmt" in stmt_types
        assert len(diags) > 0  # Diagnostics recorded
        # bFinished assignment was parsed despite previous error
        assigned_vars = [s.target.name for s in stmts if hasattr(s, "target") and hasattr(s.target, "name")]
        assert "bFinished" in assigned_vars

    def test_pointer_dereference_chained_access(self):
        source = """
        pDevice^.fbMotor.stConfig^.fSpeed := 1500.0;
        """
        stmts, cst, diags = parse_implementation(source)
        assert len(stmts) == 1
        assign = stmts[0]
        # Target should be MemberAccessExpr with dereferences
        assert isinstance(assign.target, MemberAccessExpr)
        assert assign.target.member_name == "fSpeed"

    def test_multi_variable_declaration_with_comments_and_addresses(self):
        source = """
        VAR_INPUT
            (* Sensor input bits *)
            bSensor1 AT %IX0.0, bSensor2 AT %IX0.1 : BOOL := TRUE;
            nSpeed1, nSpeed2 : INT := 0;
        END_VAR
        """
        ast_node, cst, diags = parse_declaration(source)
        assert not diags
        assert isinstance(ast_node, VarBlock)
        vars = ast_node.variables
        assert len(vars) == 4
        assert vars[0].name == "bSensor1"
        assert vars[0].address == "%IX0.0"
        assert vars[1].name == "bSensor2"
        assert vars[1].address == "%IX0.1"
        assert vars[2].name == "nSpeed1"
        assert vars[3].name == "nSpeed2"


class TestComplexXmlAndVirtualStOperations:
    """Tests XML surgical patching and Virtual ST on complex multi-member POUs."""

    SAMPLE_COMPLEX_POU = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="FB_ComplexMachine" Id="{11111111-2222-3333-4444-555555555555}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_ComplexMachine
VAR
    _nState : INT := 0;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[// Main machine cycle
CASE _nState OF
    0: _nState := 1;
END_CASE
]]></ST>
    </Implementation>
    <Action Name="A_Reset" Id="{66666666-7777-8888-9999-000000000000}">
      <Implementation>
        <ST><![CDATA[_nState := 0;
]]></ST>
      </Implementation>
    </Action>
    <Method Name="M_Start" Id="{77777777-8888-9999-0000-111111111111}">
      <Declaration><![CDATA[METHOD PUBLIC M_Start : BOOL
VAR_INPUT
    bForce : BOOL;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[_nState := 1;
M_Start := TRUE;
]]></ST>
      </Implementation>
    </Method>
    <Property Name="P_IsBusy" Id="{88888888-9999-0000-1111-222222222222}">
      <Declaration><![CDATA[PROPERTY PUBLIC P_IsBusy : BOOL
]]></Declaration>
      <Get Name="Get" Id="{99999999-0000-1111-2222-333333333333}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[P_IsBusy := (_nState <> 0);
]]></ST>
        </Implementation>
      </Get>
    </Property>
  </POU>
</TcPlcObject>"""

    def test_surgical_patch_all_member_types(self):
        doc = read_tc_xml(self.SAMPLE_COMPLEX_POU)

        # 1. Patch declaration
        new_decl = "FUNCTION_BLOCK FB_ComplexMachine\nVAR\n    _nState : INT := 10;\nEND_VAR\n"
        patched1 = patch_declaration(doc, new_decl)
        assert "_nState : INT := 10;" in patched1

        # 2. Patch action
        doc1 = read_tc_xml(patched1)
        new_action = "// Patched action\n_nState := -1;\n"
        patched2 = patch_action(doc1, "A_Reset", new_action)
        assert "_nState := -1;" in patched2

        # 3. Patch method
        doc2 = read_tc_xml(patched2)
        new_meth_impl = "// Patched start\nM_Start := FALSE;\n"
        patched3 = patch_method(doc2, "M_Start", new_implementation=new_meth_impl)
        assert "M_Start := FALSE;" in patched3

        # Confirm root GUID and all structure remained intact
        assert "{11111111-2222-3333-4444-555555555555}" in patched3
        assert "{66666666-7777-8888-9999-000000000000}" in patched3

    def test_virtual_st_projection_and_sync(self):
        virt_doc = project_to_virtual_st(self.SAMPLE_COMPLEX_POU)
        assert len(virt_doc.source_map.sections) >= 5

        # Modify virtual ST
        modified_virt_st = virt_doc.virtual_st.replace("CASE _nState OF", "CASE _nState OF // Modified in Virtual ST")
        synced_xml = sync_virtual_st_to_xml(self.SAMPLE_COMPLEX_POU, modified_virt_st)

        assert "Modified in Virtual ST" in synced_xml
        assert "A_Reset" in synced_xml
        assert "M_Start" in synced_xml
        assert "P_IsBusy" in synced_xml


class TestLspMethodLocalScopeResolution:
    """Verifies that LSP handler accurately prioritizes method-local variables over POU variables."""

    SAMPLE_POU_WITH_METHOD_LOCAL = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="FB_Worker" Id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Worker
VAR
    nVal : INT := 10;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <Method Name="M_Process" Id="{11111111-2222-3333-4444-555555555555}">
      <Declaration><![CDATA[METHOD PUBLIC M_Process : BOOL
VAR_INPUT
    nVal : LREAL;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[
nVal := 3.14159;
]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>"""

    def test_method_local_variable_resolution(self):
        import lsprotocol.types as lsp
        from twincat_core.lsp.handlers import handle_definition, handle_hover
        from twincat_core.lsp.utils import path_to_uri
        from twincat_core.syntax.span import Position

        ws = WorkspaceIndex()
        dummy_file = Path("FB_Worker.TcPOU")
        ws.update_file(dummy_file, text=self.SAMPLE_POU_WITH_METHOD_LOCAL)

        # Position inside M_Process implementation pointing at 'nVal' (0-based line 19, char 1)
        pos = lsp.Position(line=19, character=1)
        params_hover = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(dummy_file)),
            position=pos,
        )

        hover_res = handle_hover(ws, params_hover)
        assert hover_res is not None
        # Method-local nVal has type LREAL (shadowing POU INT)
        assert "LREAL" in hover_res.contents.value


class TestAdvancedLanguageConstructsAndEdgeCases:
    """Tests advanced IEC/TwinCAT constructs: enums with base types, nested comments, and chained method calls."""

    def test_enum_with_explicit_base_type(self):
        source = """
        TYPE E_OperationMode :
        (
            Init := 0,
            Auto := 10,
            Manual := 20,
            Error := 99
        ) DINT;
        END_TYPE
        """
        ast_node, cst, diags = parse_declaration(source)
        assert not diags
        assert isinstance(ast_node, TypeDecl)
        assert ast_node.name == "E_OperationMode"
        assert ast_node.definition.base_type == "DINT"
        assert len(ast_node.definition.members) == 4
        assert ast_node.definition.members[1].name == "Auto"
        assert ast_node.definition.members[1].value == "10"

    def test_nested_block_comments_tokenization(self):
        source = """
        (* Outer comment
            (* Nested level 1
                (* Nested level 2 *)
            still in level 1 *)
        back in outer *)
        nCount := nCount + 1;
        """
        tokens, diags = tokenize_st(source, include_trivia=True)
        assert not diags
        # First non-trivia token should be nCount
        semantic_tokens = [t for t in tokens if not t.is_trivia]
        assert len(semantic_tokens) >= 5
        assert semantic_tokens[0].value == "nCount"

    def test_chained_method_call_and_property_resolution(self):
        type_index = TypeIndex()
        symbol_table = SymbolTable()
        resolver = SymbolResolver(symbol_table, type_index)

        # FB_Child
        desc_child = TypeDescriptor(name="FB_Child", kind=SymbolKind.FUNCTION_BLOCK)
        sym_exec = Symbol(name="M_Execute", kind=SymbolKind.METHOD, span=None, type_ref="BOOL")
        desc_child.add_method(sym_exec)
        type_index.register_type(desc_child)

        # FB_Parent
        desc_parent = TypeDescriptor(name="FB_Parent", kind=SymbolKind.FUNCTION_BLOCK)
        sym_get_child = Symbol(name="M_GetChild", kind=SymbolKind.METHOD, span=None, type_ref="FB_Child")
        desc_parent.add_method(sym_get_child)
        type_index.register_type(desc_parent)

        # POU with instance of FB_Parent
        pou_sym = Symbol(name="MAIN", kind=SymbolKind.PROGRAM, span=None)
        pou_scope = symbol_table.create_pou_scope(pou_sym)
        sym_parent_inst = Symbol(name="fbParent", kind=SymbolKind.VARIABLE, span=None, type_ref="FB_Parent")
        pou_scope.define(sym_parent_inst)

        # Resolve chain: fbParent.M_GetChild().M_Execute
        resolved = resolver.resolve_chain("fbParent.M_GetChild().M_Execute", pou_scope)
        assert resolved is not None
        assert resolved.name == "M_Execute"
        assert resolved.kind == SymbolKind.METHOD


