"""Tests for twincat_core.project and twincat_core.semantic (Scopes, TypeIndex, Resolution, and WorkspaceIndex)."""
from pathlib import Path
import pytest

from twincat_core.project import (
    PlcProject,
    WorkspaceIndex,
    parse_plcproj_file,
)
from twincat_core.semantic import (
    Scope,
    ScopeKind,
    Symbol,
    SymbolKind,
    SymbolResolver,
    SymbolTable,
    TypeDescriptor,
    TypeIndex,
)
from twincat_core.semantic.diagnostics import run_semantic_analysis
from twincat_core.syntax import (
    BinaryExpr,
    CallArg,
    CallExpr,
    IdentifierExpr,
    LiteralExpr,
    MemberAccessExpr,
    SourceSpan,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
SOLUTION_PLCPROJ = REPO_ROOT / "solution" / "twincat3-solution" / "twincat3-solution" / "plc-project" / "plc-project.plcproj"


# =========================================================================
# 1. PlcProject Parser Tests
# =========================================================================

class TestPlcProjParser:
    def test_parse_real_plcproj(self):
        assert SOLUTION_PLCPROJ.is_file(), f"Plcproj not found at {SOLUTION_PLCPROJ}"
        proj = parse_plcproj_file(SOLUTION_PLCPROJ)

        assert proj.project_name == "plc_project"
        assert len(proj.compile_items) > 30
        assert len(proj.folders) >= 2
        assert len(proj.library_references) >= 3

        # Check specific items
        plc_task = proj.get_compile_item("PlcTask.TcTTO")
        assert plc_task is not None
        assert plc_task.item_type.lower() == "tctto"

        sample_fb = proj.get_compile_item("samples/FB_Sample_StateMachineController.TcPOU")
        assert sample_fb is not None
        assert sample_fb.abs_path.is_file()

        # Check library references
        lib_names = [l.name for l in proj.library_references]
        assert "Tc2_Standard" in lib_names
        assert "Tc3_Module" in lib_names


# =========================================================================
# 2. Scope & Resolution Tests (Level 1, Level 2, Level 3)
# =========================================================================

class TestSemanticResolution:
    def test_level_1_local_scope_and_shadowing(self):
        sym_table = SymbolTable()
        type_index = TypeIndex()
        resolver = SymbolResolver(sym_table, type_index)

        dummy_span = SourceSpan.from_bounds(1, 1, 0, 1, 1, 0)

        # Global variable
        g_var = Symbol(name="nCounter", kind=SymbolKind.VARIABLE, span=dummy_span, type_ref="INT")
        sym_table.define_global(g_var)

        # POU Symbol and Scope
        pou_sym = Symbol(name="FB_Motor", kind=SymbolKind.FUNCTION_BLOCK, span=dummy_span)
        sym_table.define_global(pou_sym)
        pou_scope = sym_table.create_pou_scope(pou_sym, Path("dummy/FB_Motor.TcPOU"))

        # POU-level variable (shadows global nCounter)
        pou_var = Symbol(name="nCounter", kind=SymbolKind.VARIABLE, span=dummy_span, type_ref="DINT")
        pou_scope.define(pou_var)

        # Method Symbol and Scope
        method_sym = Symbol(name="M_Step", kind=SymbolKind.METHOD, span=dummy_span, type_ref="BOOL")
        method_scope = sym_table.create_method_scope(method_sym, pou_scope, Path("dummy/FB_Motor.TcPOU"))

        # Method local variable (shadows POU nCounter)
        method_var = Symbol(name="nCounter", kind=SymbolKind.VARIABLE, span=dummy_span, type_ref="LREAL")
        method_scope.define(method_var)

        local_temp = Symbol(name="bLocalFlag", kind=SymbolKind.VARIABLE, span=dummy_span, type_ref="BOOL")
        method_scope.define(local_temp)

        # Inside Method: nCounter must resolve to method_var (LREAL)
        res1 = resolver.resolve_identifier("nCounter", method_scope)
        assert res1 is not None
        assert res1.type_ref == "LREAL"

        # Inside Method: bLocalFlag resolves to local_temp
        res_flag = resolver.resolve_identifier("bLocalFlag", method_scope)
        assert res_flag is not None
        assert res_flag.type_ref == "BOOL"

        # Inside POU: nCounter must resolve to pou_var (DINT)
        res2 = resolver.resolve_identifier("nCounter", pou_scope)
        assert res2 is not None
        assert res2.type_ref == "DINT"

        # Global scope: nCounter must resolve to g_var (INT)
        res3 = resolver.resolve_identifier("nCounter", sym_table.global_scope)
        assert res3 is not None
        assert res3.type_ref == "INT"

    def test_level_2_oop_inheritance_and_member_access(self):
        sym_table = SymbolTable()
        type_index = TypeIndex()
        resolver = SymbolResolver(sym_table, type_index)

        dummy_span = SourceSpan.from_bounds(1, 1, 0, 1, 1, 0)

        # Base FB
        base_sym = Symbol(name="FB_BaseAxis", kind=SymbolKind.FUNCTION_BLOCK, span=dummy_span)
        base_desc = TypeDescriptor(name="FB_BaseAxis", kind=SymbolKind.FUNCTION_BLOCK)
        base_field = Symbol(name="_fPosition", kind=SymbolKind.VARIABLE, span=dummy_span, type_ref="LREAL")
        base_method = Symbol(name="M_Reset", kind=SymbolKind.METHOD, span=dummy_span, type_ref="BOOL")
        base_desc.add_field(base_field)
        base_desc.add_method(base_method)
        type_index.register_type(base_desc)

        # Derived FB
        derived_sym = Symbol(name="FB_ServoAxis", kind=SymbolKind.FUNCTION_BLOCK, span=dummy_span)
        derived_desc = TypeDescriptor(name="FB_ServoAxis", kind=SymbolKind.FUNCTION_BLOCK, extends_name="FB_BaseAxis")
        derived_field = Symbol(name="_fTorque", kind=SymbolKind.VARIABLE, span=dummy_span, type_ref="REAL")
        derived_method = Symbol(name="M_MoveAbsolute", kind=SymbolKind.METHOD, span=dummy_span, type_ref="BOOL")
        derived_desc.add_field(derived_field)
        derived_desc.add_method(derived_method)
        type_index.register_type(derived_desc)

        # Struct Type
        st_desc = TypeDescriptor(name="ST_Config", kind=SymbolKind.STRUCT)
        st_field = Symbol(name="nTimeout_ms", kind=SymbolKind.STRUCT_FIELD, span=dummy_span, type_ref="UDINT")
        st_desc.add_field(st_field)
        type_index.register_type(st_desc)

        # Enum Type
        e_desc = TypeDescriptor(name="E_DriveState", kind=SymbolKind.ENUM)
        e_member = Symbol(name="Ready", kind=SymbolKind.ENUM_MEMBER, span=dummy_span, type_ref="E_DriveState")
        e_desc.add_enum_member(e_member)
        type_index.register_type(e_desc)

        # 1. Resolve derived method on FB_ServoAxis
        res_m1 = resolver.resolve_member_access("FB_ServoAxis", "M_MoveAbsolute")
        assert res_m1 is not None
        assert res_m1.name == "M_MoveAbsolute"

        # 2. Resolve inherited method from FB_BaseAxis
        res_m2 = resolver.resolve_member_access("FB_ServoAxis", "M_Reset")
        assert res_m2 is not None
        assert res_m2.name == "M_Reset"

        # 3. Resolve inherited field from FB_BaseAxis
        res_f1 = resolver.resolve_member_access("FB_ServoAxis", "_fPosition")
        assert res_f1 is not None
        assert res_f1.type_ref == "LREAL"

        # 4. Resolve struct field
        res_st = resolver.resolve_member_access("ST_Config", "nTimeout_ms")
        assert res_st is not None
        assert res_st.type_ref == "UDINT"

        # 5. Resolve Enum member
        res_e = resolver.resolve_member_access("E_DriveState", "Ready")
        assert res_e is not None
        assert res_e.name == "Ready"

    def test_level_3_gvl_resolution(self):
        sym_table = SymbolTable()
        type_index = TypeIndex()
        resolver = SymbolResolver(sym_table, type_index)

        dummy_span = SourceSpan.from_bounds(1, 1, 0, 1, 1, 0)

        # GVL 1: Normal GVL (unqualified access allowed)
        gvl1_sym = Symbol(name="GVL_Config", kind=SymbolKind.GVL, span=dummy_span, qualified_only=False)
        sym_table.define_global(gvl1_sym)
        gvl1_scope = sym_table.create_gvl_scope(gvl1_sym, Path("dummy/GVL_Config.TcGVL"))
        gvl1_var = Symbol(name="g_fMaxSpeed", kind=SymbolKind.VARIABLE, span=dummy_span, type_ref="LREAL")
        gvl1_scope.define(gvl1_var)

        # GVL 2: Qualified only GVL
        gvl2_sym = Symbol(name="Param_Drive", kind=SymbolKind.GVL, span=dummy_span, qualified_only=True)
        sym_table.define_global(gvl2_sym)
        gvl2_scope = sym_table.create_gvl_scope(gvl2_sym, Path("dummy/Param_Drive.TcGVL"))
        gvl2_var = Symbol(name="cMotorPoles", kind=SymbolKind.CONSTANT, span=dummy_span, type_ref="UINT")
        gvl2_scope.define(gvl2_var)

        # Test 1: Unqualified access to g_fMaxSpeed should find gvl1_var
        res1 = resolver.resolve_identifier("g_fMaxSpeed", sym_table.global_scope)
        assert res1 is not None
        assert res1.type_ref == "LREAL"

        # Test 2: Unqualified access to cMotorPoles should NOT resolve directly (qualified_only=True)
        res2 = resolver.resolve_identifier("cMotorPoles", sym_table.global_scope)
        assert res2 is None

        # Test 3: Qualified access to Param_Drive.cMotorPoles should resolve
        res3 = resolver.resolve_member_access("Param_Drive", "cMotorPoles")
        assert res3 is not None
        assert res3.type_ref == "UINT"

    def test_type_inference_expressions(self):
        sym_table = SymbolTable()
        type_index = TypeIndex()
        resolver = SymbolResolver(sym_table, type_index)

        dummy_span = SourceSpan.from_bounds(1, 1, 0, 1, 1, 0)

        # FB and Instance
        fb_desc = TypeDescriptor(name="FB_Sensor", kind=SymbolKind.FUNCTION_BLOCK)
        f_meas = Symbol(name="fMeasurement", kind=SymbolKind.VARIABLE, span=dummy_span, type_ref="REAL")
        m_calc = Symbol(name="M_GetAvg", kind=SymbolKind.METHOD, span=dummy_span, type_ref="LREAL")
        fb_desc.add_field(f_meas)
        fb_desc.add_method(m_calc)
        type_index.register_type(fb_desc)

        fb_inst = Symbol(name="fbSensor1", kind=SymbolKind.VARIABLE, span=dummy_span, type_ref="FB_Sensor")
        sym_table.define_global(fb_inst)

        # 1. Literal expression
        lit_int = LiteralExpr(span=dummy_span, value="42", literal_type="INT_LITERAL")
        assert resolver.infer_expression_type(lit_int, sym_table.global_scope) == "ANY_INT"

        # 2. Instance member access (fbSensor1.fMeasurement)
        access_expr = MemberAccessExpr(
            span=dummy_span,
            target=IdentifierExpr(span=dummy_span, name="fbSensor1"),
            member_name="fMeasurement",
        )
        assert resolver.infer_expression_type(access_expr, sym_table.global_scope) == "REAL"

        # 3. Method call (fbSensor1.M_GetAvg())
        method_access = MemberAccessExpr(
            span=dummy_span,
            target=IdentifierExpr(span=dummy_span, name="fbSensor1"),
            member_name="M_GetAvg",
        )
        call_expr = CallExpr(span=dummy_span, callee=method_access)
        assert resolver.infer_expression_type(call_expr, sym_table.global_scope) == "LREAL"

        # 4. Binary comparison (fbSensor1.fMeasurement > 10.0) -> BOOL
        cmp_expr = BinaryExpr(
            span=dummy_span,
            op=">",
            left=access_expr,
            right=LiteralExpr(span=dummy_span, value="10.0", literal_type="REAL_LITERAL"),
        )
        assert resolver.infer_expression_type(cmp_expr, sym_table.global_scope) == "BOOL"

        # 5. Standard built-ins and ExST type inferences
        sizeof_call = CallExpr(
            span=dummy_span,
            callee=IdentifierExpr(span=dummy_span, name="SIZEOF"),
            args=[],
        )
        assert resolver.infer_expression_type(sizeof_call, sym_table.global_scope) == "UDINT"

        bound_call = CallExpr(
            span=dummy_span,
            callee=IdentifierExpr(span=dummy_span, name="UPPER_BOUND"),
            args=[],
        )
        assert resolver.infer_expression_type(bound_call, sym_table.global_scope) == "DINT"

        query_itf_call = CallExpr(
            span=dummy_span,
            callee=IdentifierExpr(span=dummy_span, name="__QUERYINTERFACE"),
            args=[],
        )
        assert resolver.infer_expression_type(query_itf_call, sym_table.global_scope) == "BOOL"

        is_valid_ref_call = CallExpr(
            span=dummy_span,
            callee=IdentifierExpr(span=dummy_span, name="__ISVALIDREF"),
            args=[],
        )
        assert resolver.infer_expression_type(is_valid_ref_call, sym_table.global_scope) == "BOOL"

        # 6. Variadic MIN, MAX, MUX with 2, 3, 5+ arguments
        min_multi_call = CallExpr(
            span=dummy_span,
            callee=IdentifierExpr(span=dummy_span, name="MIN"),
            args=[
                CallArg(span=dummy_span, value=LiteralExpr(span=dummy_span, value="10", literal_type="INT_LITERAL")),
                CallArg(span=dummy_span, value=LiteralExpr(span=dummy_span, value="20", literal_type="INT_LITERAL")),
                CallArg(span=dummy_span, value=LiteralExpr(span=dummy_span, value="3.14", literal_type="REAL_LITERAL")),
                CallArg(span=dummy_span, value=LiteralExpr(span=dummy_span, value="5", literal_type="INT_LITERAL")),
            ],
        )
        assert resolver.infer_expression_type(min_multi_call, sym_table.global_scope) == "ANY_REAL"

        max_multi_call = CallExpr(
            span=dummy_span,
            callee=IdentifierExpr(span=dummy_span, name="MAX"),
            args=[
                CallArg(span=dummy_span, value=access_expr),  # REAL
                CallArg(span=dummy_span, value=LiteralExpr(span=dummy_span, value="0.0", literal_type="REAL_LITERAL")),
                CallArg(span=dummy_span, value=LiteralExpr(span=dummy_span, value="100.0", literal_type="REAL_LITERAL")),
            ],
        )
        assert resolver.infer_expression_type(max_multi_call, sym_table.global_scope) == "REAL"

        mux_multi_call = CallExpr(
            span=dummy_span,
            callee=IdentifierExpr(span=dummy_span, name="MUX"),
            args=[
                CallArg(span=dummy_span, value=LiteralExpr(span=dummy_span, value="0", literal_type="INT_LITERAL")),
                CallArg(span=dummy_span, value=LiteralExpr(span=dummy_span, value="10", literal_type="INT_LITERAL")),
                CallArg(span=dummy_span, value=LiteralExpr(span=dummy_span, value="20", literal_type="INT_LITERAL")),
                CallArg(span=dummy_span, value=LiteralExpr(span=dummy_span, value="30", literal_type="INT_LITERAL")),
            ],
        )
        assert resolver.infer_expression_type(mux_multi_call, sym_table.global_scope) == "ANY_INT"


# =========================================================================
# 3. Incremental WorkspaceIndex Tests
# =========================================================================

class TestWorkspaceIndex:
    def test_workspace_index_from_project(self):
        ws = WorkspaceIndex.from_plcproj(SOLUTION_PLCPROJ)

        # Check that files have been indexed
        assert len(ws.indexed_files) > 20

        # Verify global types populated in type_index
        all_types = ws.type_index.get_all_user_types()
        type_names = [t.name.lower() for t in all_types]
        assert "fb_sample_statemachinecontroller" in type_names
        assert "e_sample_largeenum" in type_names
        assert "st_sample_diagnosticsstruct" in type_names
        assert "i_sample_widgetinterface" in type_names

        # Verify symbol table populated
        sm_pou = ws.symbol_table.find_pou_scope("fb_sample_statemachinecontroller")
        assert sm_pou is not None
        assert len(sm_pou.get_all_symbols()) > 0

    def test_incremental_file_update_and_removal(self):
        ws = WorkspaceIndex()

        file_a = Path("C:/project/FB_Motor.TcPOU")
        xml_v1 = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Motor" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Motor
VAR
    _nSpeed : INT := 0;
END_VAR
]]></Declaration>
    <Method Name="M_Start" Id="{22222222-2222-2222-2222-222222222222}">
      <Declaration><![CDATA[METHOD M_Start : BOOL
VAR_INPUT
    bFast : BOOL;
END_VAR
]]></Declaration>
    </Method>
  </POU>
</TcPlcObject>"""

        # 1. First index
        idx_v1 = ws.update_file(file_a, text=xml_v1)
        assert idx_v1.top_level_ast is not None

        # Verify resolution
        t_motor = ws.type_index.get_type("FB_Motor")
        assert t_motor is not None
        assert "m_start" in t_motor.methods
        assert "_nspeed" in t_motor.fields

        res_speed = ws.resolver.resolve_member_access("FB_Motor", "_nSpeed")
        assert res_speed is not None
        assert res_speed.type_ref == "INT"

        # 2. Incremental Update with new field and new return type
        xml_v2 = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Motor" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Motor
VAR
    _nSpeed : LREAL := 0.0;
    _bRunning : BOOL;
END_VAR
]]></Declaration>
    <Method Name="M_Stop" Id="{33333333-3333-3333-3333-333333333333}">
      <Declaration><![CDATA[METHOD M_Stop : BOOL]]></Declaration>
    </Method>
  </POU>
</TcPlcObject>"""

        idx_v2 = ws.update_file(file_a, text=xml_v2)
        assert idx_v2.content_hash != idx_v1.content_hash

        # Verify updated resolution
        res_speed_updated = ws.resolver.resolve_member_access("FB_Motor", "_nSpeed")
        assert res_speed_updated is not None
        assert res_speed_updated.type_ref == "LREAL"

        res_running = ws.resolver.resolve_member_access("FB_Motor", "_bRunning")
        assert res_running is not None
        assert res_running.type_ref == "BOOL"

        # Old method M_Start should no longer exist, new method M_Stop should exist
        assert ws.resolver.resolve_member_access("FB_Motor", "M_Start") is None
        assert ws.resolver.resolve_member_access("FB_Motor", "M_Stop") is not None

        # 3. File Removal
        ws.remove_file(file_a)
        assert ws.type_index.get_type("FB_Motor") is None
        assert ws.symbol_table.find_pou_scope("FB_Motor") is None
        assert ws.get_file(file_a) is None

    def test_hierarchical_proximity_and_file_isolation(self, tmp_path):
        """Verify that symbols in a fixture folder resolve to sibling fixture files rather than solution files."""
        folder_sol = tmp_path / "solution" / "plc_proj"
        folder_sol.mkdir(parents=True)
        folder_fix = tmp_path / "tests" / "fixtures" / "oneline"
        folder_fix.mkdir(parents=True)

        dut_sol = folder_sol / "ST_Config.TcDUT"
        dut_sol.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_Config" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[TYPE ST_Config :
STRUCT
    nSolVal : INT;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        pou_sol = folder_sol / "FB_Controller.TcPOU"
        pou_sol.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Controller" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Controller
VAR
    stCfg : ST_Config;
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        dut_fix = folder_fix / "ST_Config.TcDUT"
        dut_fix.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_Config" Id="{33333333-3333-3333-3333-333333333333}">
    <Declaration><![CDATA[TYPE ST_Config :
STRUCT
    nFixVal : DINT;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        pou_fix = folder_fix / "FB_Controller.TcPOU"
        pou_fix.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Controller" Id="{44444444-4444-4444-4444-444444444444}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Controller
VAR
    stCfg : ST_Config;
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        # Index solution first, then fixtures
        ws.update_file(dut_sol)
        ws.update_file(pou_sol)
        ws.update_file(dut_fix)
        ws.update_file(pou_fix)

        # 1. Look up ST_Config with fixture context -> must return fixture DUT
        scope_fix = ws.symbol_table.find_pou_scope("FB_Controller", context_path=pou_fix)
        assert scope_fix is not None
        assert scope_fix.owner_symbol.file_path == pou_fix.resolve()

        sym_fix_config = ws.resolver.resolve_identifier("ST_Config", scope_fix)
        assert sym_fix_config is not None
        assert sym_fix_config.file_path == dut_fix.resolve()

        # 2. Look up ST_Config with solution context -> must return solution DUT
        scope_sol = ws.symbol_table.find_pou_scope("FB_Controller", context_path=pou_sol)
        assert scope_sol is not None
        assert scope_sol.owner_symbol.file_path == pou_sol.resolve()

        sym_sol_config = ws.resolver.resolve_identifier("ST_Config", scope_sol)
        assert sym_sol_config is not None
        assert sym_sol_config.file_path == dut_sol.resolve()


# =========================================================================
# 5. Semantic Diagnostics Validation Tests
# =========================================================================

class TestSemanticDiagnostics:
    def test_semantic_analysis_unknown_type_deactivated(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_file = tmp_path / "FB_InvalidType.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_InvalidType" Id="{12345678-1234-1234-1234-123456789abc}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_InvalidType
VAR
    fbGoodTimer : TON;
    fbBadDevice : NonExistentCustomType_XYZ;
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        # TC-SEM-001 is deactivated so external compiled libraries do not trigger false positive errors
        assert len(diags) == 0

    def test_semantic_analysis_catches_duplicate_identifier(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_file = tmp_path / "FB_DuplicateVar.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_DuplicateVar" Id="{12345678-1234-1234-1234-123456789def}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_DuplicateVar
VAR
    nCounter : INT;
    nCounter : DINT;
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        assert len(diags) == 1
        assert diags[0].code == "TC-SEM-002"
        assert "Duplicate identifier 'nCounter'" in diags[0].message

    def test_semantic_analysis_accepts_system_types_and_fb_init_arrays(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_file = tmp_path / "FB_ValidAdvanced.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_ValidAdvanced" Id="{12345678-1234-1234-1234-123456789fff}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_ValidAdvanced
VAR
    stVarInfo    : __SYSTEM.VAR_INFO;
    arrTimers    : ARRAY[1..2] OF TON[(PT := T#1S), (PT := T#2S)];
    arrPointers  : ARRAY[1..5] OF POINTER TO DINT;
    arrStrings   : ARRAY[1..3] OF STRING(255);
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        assert len(diags) == 0, f"Expected 0 diagnostics but found: {diags}"

    def test_semantic_analysis_catches_missing_interface_method(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        itf_file = tmp_path / "I_Device.TcIO"
        itf_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_Device" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[INTERFACE I_Device
]]></Declaration>
    <Method Name="M_Reset" Id="{11111111-1111-1111-1111-111111111112}">
      <Declaration><![CDATA[METHOD M_Reset : BOOL
]]></Declaration>
    </Method>
  </Itf>
</TcPlcObject>""", encoding="utf-8")

        pou_file = tmp_path / "FB_IncompleteDevice.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_IncompleteDevice" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_IncompleteDevice IMPLEMENTS I_Device
VAR
    bFlag : BOOL;
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(itf_file)
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        assert any(d.code == "TC-SEM-003" and "M_Reset" in d.message for d in diags)

    def test_semantic_analysis_catches_cyclic_inheritance(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_a = tmp_path / "FB_A.TcPOU"
        pou_a.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_A" Id="{33333333-3333-3333-3333-333333333331}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_A EXTENDS FB_B
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        pou_b = tmp_path / "FB_B.TcPOU"
        pou_b.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_B" Id="{33333333-3333-3333-3333-333333333332}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_B EXTENDS FB_A
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_a)
        ws.update_file(pou_b)

        diags_a = run_semantic_analysis(ws, pou_a)
        assert any(d.code == "TC-SEM-004" for d in diags_a)

    def test_semantic_analysis_catches_abstract_fb_instantiation(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        abs_file = tmp_path / "FB_AbstractBase.TcPOU"
        abs_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_AbstractBase" Id="{44444444-4444-4444-4444-444444444441}">
    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_AbstractBase
VAR
    nId : INT;
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        pou_file = tmp_path / "FB_User.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_User" Id="{44444444-4444-4444-4444-444444444442}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_User
VAR
    fbInst : FB_AbstractBase;
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(abs_file)
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        assert any(d.code == "TC-SEM-005" and "FB_AbstractBase" in d.message for d in diags)

    def test_semantic_type_mismatch_assignment_error(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_file = tmp_path / "FB_TypeMismatch.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_TypeMismatch" Id="{55555555-5555-5555-5555-555555555551}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_TypeMismatch
VAR
    sName : STRING;
    nVal  : INT;
    bFlag : BOOL;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
sName := nVal;
bFlag := 'hello';
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        mismatch_diags = [d for d in diags if d.code == "TC-SEM-006"]
        assert len(mismatch_diags) == 2
        assert "Cannot convert" in mismatch_diags[0].message

    def test_semantic_implicit_narrowing_and_sign_change_warning(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis
        from twincat_core.syntax.diagnostics import DiagnosticSeverity

        pou_file = tmp_path / "FB_Narrowing.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Narrowing" Id="{66666666-6666-6666-6666-666666666661}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Narrowing
VAR
    nInt    : INT;
    nDint   : DINT;
    fReal   : REAL;
    fLReal  : LREAL;
    nUint   : UINT;
    sStr    : STRING;
    wsStr   : WSTRING;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
nInt := nDint;
fReal := fLReal;
nUint := nInt;
sStr := wsStr;
nInt := fReal;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        warnings = [d for d in diags if d.code == "TC-SEM-007" and d.severity == DiagnosticSeverity.WARNING]
        assert len(warnings) == 3
        assert any("possible loss of precision" in w.message for w in warnings)
        assert any("possible loss of non-ASCII characters" in w.message for w in warnings)
        assert any("fractional part will be truncated" in w.message for w in warnings)

    def test_semantic_condition_must_be_boolean(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_file = tmp_path / "FB_NonBoolCond.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_NonBoolCond" Id="{77777777-7777-7777-7777-777777777771}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_NonBoolCond
VAR
    sName : STRING;
    nVal  : INT;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
IF sName THEN
    nVal := 1;
END_IF;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        assert any(d.code == "TC-SEM-006" and "must be of type 'BOOL'" in d.message for d in diags)

    def test_semantic_valid_widening_and_conversions_zero_diagnostics(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_file = tmp_path / "FB_ValidConversions.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_ValidConversions" Id="{88888888-8888-8888-8888-888888888881}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_ValidConversions
VAR
    nInt   : INT := 10;
    nDint  : DINT;
    fReal  : REAL := 1.5;
    fLReal : LREAL;
    sStr   : STRING := 'Hello';
    wStr   : WSTRING;
    tTime  : TIME := T#1S;
    ltTime : LTIME;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
nDint := nInt;
fLReal := fReal;
wStr := sStr;
ltTime := tTime;
nInt := TO_INT(nDint);
fReal := TO_REAL(fLReal);
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        assert len(diags) == 0, f"Expected 0 diagnostics for valid widening, found: {diags}"

    def test_semantic_initial_value_mismatch_error(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_file = tmp_path / "FB_BadInit.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_BadInit" Id="{99999999-9999-9999-9999-999999999991}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_BadInit
VAR
    nVal : INT := 'invalid_string';
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        assert any(d.code == "TC-SEM-006" and "Initial value" in d.message for d in diags)

    def test_semantic_bitwise_operations_and_untyped_literals_zero_diagnostics(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_file = tmp_path / "FB_BitwiseAndLiterals.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_BitwiseAndLiterals" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_BitwiseAndLiterals
VAR
    dwMask     : DWORD := 16#0000_0000;
    nFreq_Hz   : UINT := 50;
    nBatches   : UDINT := 0;
    hrCode     : HRESULT := 16#8000_0000;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
dwMask := dwMask OR 16#0000_0001;
dwMask := dwMask AND 16#FFFF_FFFE;
nBatches := nBatches + 1;
hrCode := 0;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        assert len(diags) == 0, f"Expected 0 diagnostics for bitwise operations and untyped literals, found: {diags}"

    def test_semantic_interface_and_class_inheritance_conformance(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        # 1. Base interface
        itf_base = tmp_path / "I_Base.TcIO"
        itf_base.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_Base" Id="{10000000-0000-0000-0000-000000000001}">
    <Declaration><![CDATA[INTERFACE I_Base
METHOD M_Base : BOOL
END_METHOD]]></Declaration>
  </Itf>
</TcPlcObject>""", encoding="utf-8")

        # 2. Extended interface
        itf_ext = tmp_path / "I_Ext.TcIO"
        itf_ext.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_Ext" Id="{10000000-0000-0000-0000-000000000002}">
    <Declaration><![CDATA[INTERFACE I_Ext EXTENDS I_Base
METHOD M_Ext : BOOL
END_METHOD]]></Declaration>
  </Itf>
</TcPlcObject>""", encoding="utf-8")

        # 3. Base class implementing I_Base
        fb_base = tmp_path / "FB_Base.TcPOU"
        fb_base.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Base" Id="{10000000-0000-0000-0000-000000000003}">
    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_Base IMPLEMENTS I_Base]]></Declaration>
    <Method Name="M_Base" Id="{10000000-0000-0000-0000-000000000004}">
      <Declaration><![CDATA[METHOD M_Base : BOOL]]></Declaration>
      <Implementation><![CDATA[M_Base := TRUE;]]></Implementation>
    </Method>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        # 4. Derived class extending FB_Base and implementing I_Ext
        fb_derived = tmp_path / "FB_Derived.TcPOU"
        fb_derived.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Derived" Id="{10000000-0000-0000-0000-000000000005}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base IMPLEMENTS I_Ext]]></Declaration>
    <Method Name="M_Ext" Id="{10000000-0000-0000-0000-000000000006}">
      <Declaration><![CDATA[METHOD M_Ext : BOOL]]></Declaration>
      <Implementation><![CDATA[M_Ext := TRUE;]]></Implementation>
    </Method>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        # 5. Consumer testing polymorphic assignments and __QUERYINTERFACE
        fb_test = tmp_path / "FB_Test.TcPOU"
        fb_test.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Test" Id="{10000000-0000-0000-0000-000000000007}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test
VAR
    ipBase        : I_Base;
    ipExt         : I_Ext;
    fbDev         : FB_Derived;
    bQuerySuccess : BOOL;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
ipBase := fbDev;
ipBase := ipExt;
bQuerySuccess := __QUERYINTERFACE(ipBase, ipExt);
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(itf_base)
        ws.update_file(itf_ext)
        ws.update_file(fb_base)
        ws.update_file(fb_derived)
        ws.update_file(fb_test)

        diags = run_semantic_analysis(ws, fb_test)
        assert len(diags) == 0, f"Expected 0 diagnostics for polymorphic assignments and __QUERYINTERFACE, found: {diags}"

    def test_semantic_analysis_undeclared_identifier_deactivated(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_file = tmp_path / "FB_UndeclaredTest.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_UndeclaredTest" Id="{10000000-0000-0000-0000-000000000099}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_UndeclaredTest
VAR
    nSum : INT;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
nSum := nUnknownVar + 10;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)
        diags = run_semantic_analysis(ws, pou_file)
        # TC-SEM-008 is deactivated so external library enums/GVLs/symbols do not trigger false positive errors
        assert len(diags) == 0

    def test_multi_project_and_enum_dut_resolution(self, tmp_path):
        """Verify indexing multiple plcproj projects and resolving DUT enums and structs across projects."""
        lib_dir = tmp_path / "lib_project"
        lib_dir.mkdir()
        app_dir = tmp_path / "app_project"
        app_dir.mkdir()

        # 1. Create Enum DUT in lib_project
        enum_file = lib_dir / "E_EB_BA_BlindType.TcDUT"
        enum_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="E_EB_BA_BlindType" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_EB_BA_BlindType :
(
    VenetianBlind := 0,
    RollerShutter := 1,
    ZipScreen     := 2
) INT;
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        # 2. Create Struct DUT in lib_project
        struct_file = lib_dir / "ST_EB_BA_DeskCal_BlindTypeTransmission.TcDUT"
        struct_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_EB_BA_DeskCal_BlindTypeTransmission" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[TYPE ST_EB_BA_DeskCal_BlindTypeTransmission :
STRUCT
    fTransmissionFactor : LREAL := 1.0;
    eType               : E_EB_BA_BlindType := E_EB_BA_BlindType.VenetianBlind;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        lib_plcproj = lib_dir / "Tc3_EB_BA.plcproj"
        lib_plcproj.write_text("""<?xml version="1.0" encoding="utf-8"?>
<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Name>Tc3_EB_BA</Name>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="E_EB_BA_BlindType.TcDUT" />
    <Compile Include="ST_EB_BA_DeskCal_BlindTypeTransmission.TcDUT" />
  </ItemGroup>
</Project>""", encoding="utf-8")

        # 3. Create Function POU in app_project that references the DUTs
        pou_file = app_dir / "F_EB_BA_DeskCal_Transmission.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="F_EB_BA_DeskCal_Transmission" Id="{33333333-3333-3333-3333-333333333333}">
    <Declaration><![CDATA[FUNCTION F_EB_BA_DeskCal_Transmission : LREAL
VAR_INPUT
    eBlindType : E_EB_BA_BlindType;
END_VAR
VAR
    stConfig : ST_EB_BA_DeskCal_BlindTypeTransmission;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[
CASE eBlindType OF
    E_EB_BA_BlindType.VenetianBlind:
        F_EB_BA_DeskCal_Transmission := stConfig.fTransmissionFactor;
    E_EB_BA_BlindType#RollerShutter:
        F_EB_BA_DeskCal_Transmission := 0.5;
    ELSE
        F_EB_BA_DeskCal_Transmission := 0.0;
END_CASE;
]]></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        app_plcproj = app_dir / "Tc3_EB_BA_Sample.plcproj"
        app_plcproj.write_text("""<?xml version="1.0" encoding="utf-8"?>
<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Name>Tc3_EB_BA_Sample</Name>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="F_EB_BA_DeskCal_Transmission.TcPOU" />
  </ItemGroup>
</Project>""", encoding="utf-8")

        # Test index with both projects added
        ws = WorkspaceIndex()
        ws.add_plcproj(lib_plcproj)
        ws.add_plcproj(app_plcproj)

        # Verify TypeIndex registered the DUTs from lib_plcproj
        e_desc = ws.type_index.get_type("E_EB_BA_BlindType")
        assert e_desc is not None
        assert e_desc.kind == SymbolKind.ENUM
        assert "venetianblind" in e_desc.enum_members

        s_desc = ws.type_index.get_type("ST_EB_BA_DeskCal_BlindTypeTransmission")
        assert s_desc is not None
        assert s_desc.kind == SymbolKind.STRUCT
        assert "ftransmissionfactor" in s_desc.fields

        # Verify semantic resolution of the POU that references both DUTs
        scope = ws.symbol_table.find_pou_scope("F_EB_BA_DeskCal_Transmission")
        assert scope is not None

        # Resolve enum member access on type
        enum_member_sym = ws.resolver.resolve_member_access("E_EB_BA_BlindType", "VenetianBlind", scope)
        assert enum_member_sym is not None
        assert enum_member_sym.name == "VenetianBlind"

        # Resolve struct field access
        field_sym = ws.resolver.resolve_chain("stConfig.fTransmissionFactor", scope)
        assert field_sym is not None
        assert field_sym.name == "fTransmissionFactor"

    def test_interface_and_this_assignment_compatibility(self, tmp_path: Path) -> None:
        """Verify polymorphic assignment of FB instances, THIS^ references, and 0/NULL to INTERFACE variables."""
        itf_file = tmp_path / "I_Widget.TcIO"
        itf_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_Widget" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[INTERFACE I_Widget
]]></Declaration>
  </Itf>
</TcPlcObject>""", encoding="utf-8")

        pou_file = tmp_path / "FB_Main.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Main" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Main
VAR
    _ipWidget : I_Widget;
    _fbLight  : FB_Light;
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[
THIS^._ipWidget := THIS^._fbLight;
_ipWidget := 0;
_ipWidget := NULL;
]]></ST></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(itf_file)
        ws.update_file(pou_file, declaration_only=False)

        diags = run_semantic_analysis(ws, pou_file)
        # Should not report any TC-SEM-006 type mismatch errors for interface assignments
        type_mismatch_diags = [d for d in diags if d.code == "TC-SEM-006"]
        assert len(type_mismatch_diags) == 0

    def test_abstract_fb_and_inherited_interface_methods(self, tmp_path: Path) -> None:
        """Verify ABSTRACT FBs and FBs inheriting interface methods from base classes do not trigger TC-SEM-003."""
        parent_file = tmp_path / "FB_Parent.TcPOU"
        parent_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Parent" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_Parent
VAR_INPUT
    bParentInput : BOOL;
END_VAR
VAR
    _nParentCounter : INT;
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
    <Method Name="InitParentNode" Id="{11111111-1111-1111-1111-111111111112}">
      <Declaration><![CDATA[METHOD PUBLIC InitParentNode : BOOL
VAR_INPUT
    bForce : BOOL;
END_VAR]]></Declaration>
      <Implementation><ST><![CDATA[]]></ST></Implementation>
    </Method>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        itf_file = tmp_path / "I_Widget.TcIO"
        itf_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_Widget" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[INTERFACE I_Widget
]]></Declaration>
    <Method Name="InitParentNode" Id="{22222222-2222-2222-2222-222222222223}">
      <Declaration><![CDATA[METHOD InitParentNode : BOOL
VAR_INPUT
    bForce : BOOL;
END_VAR]]></Declaration>
    </Method>
  </Itf>
</TcPlcObject>""", encoding="utf-8")

        abstract_child_file = tmp_path / "FB_AbstractChild.TcPOU"
        abstract_child_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_AbstractChild" Id="{33333333-3333-3333-3333-333333333333}">
    <Declaration><![CDATA[FUNCTION_BLOCK ABSTRACT FB_AbstractChild EXTENDS FB_Parent IMPLEMENTS I_Widget
VAR_INPUT
    bEnable : BOOL := TRUE;
END_VAR
VAR
    _ipWidget : I_Widget;
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[
_nParentCounter := _nParentCounter + 1;
THIS^._nParentCounter := 10;
SUPER^.InitParentNode(bForce := TRUE);
InitParentNode(bForce := FALSE);
_ipWidget := THIS^;
]]></ST></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        concrete_child_file = tmp_path / "FB_ConcreteChild.TcPOU"
        concrete_child_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_ConcreteChild" Id="{44444444-4444-4444-4444-444444444444}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_ConcreteChild EXTENDS FB_Parent IMPLEMENTS I_Widget
VAR_INPUT
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        unimplemented_file = tmp_path / "FB_Unimplemented.TcPOU"
        unimplemented_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Unimplemented" Id="{55555555-5555-5555-5555-555555555555}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Unimplemented IMPLEMENTS I_Widget
VAR_INPUT
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(parent_file)
        ws.update_file(itf_file)
        ws.update_file(abstract_child_file, declaration_only=False)
        ws.update_file(concrete_child_file, declaration_only=False)
        ws.update_file(unimplemented_file, declaration_only=False)

        # 1. Abstract child FB should have 0 TC-SEM-003 errors
        diags_abstract = run_semantic_analysis(ws, abstract_child_file)
        sem_003_abstract = [d for d in diags_abstract if d.code == "TC-SEM-003"]
        assert len(sem_003_abstract) == 0

        # 2. Concrete child inheriting InitParentNode from FB_Parent should have 0 TC-SEM-003 errors
        diags_concrete = run_semantic_analysis(ws, concrete_child_file)
        sem_003_concrete = [d for d in diags_concrete if d.code == "TC-SEM-003"]
        assert len(sem_003_concrete) == 0

        # 3. Unimplemented concrete FB should report TC-SEM-003
        diags_unimpl = run_semantic_analysis(ws, unimplemented_file)
        sem_003_unimpl = [d for d in diags_unimpl if d.code == "TC-SEM-003"]
        assert len(sem_003_unimpl) == 1
        assert "InitParentNode" in sem_003_unimpl[0].message

    def test_var_in_out_constant_no_init_required(self, tmp_path):
        from twincat_core.syntax.parser_declarations import DeclarationParser

        cdata = """FUNCTION_BLOCK FB_Stream
VAR_IN_OUT CONSTANT
    sKey   : STRING;
    sValue : STRING;
END_VAR
"""
        parser = DeclarationParser.from_source(cdata)
        ast_node, cst_nodes = parser.parse_declaration_file()
        assert len(parser.diagnostics) == 0, f"Expected 0 diagnostics for VAR_IN_OUT CONSTANT without initial value, got: {parser.diagnostics}"

    def test_method_boolean_return_with_var_inst_state_machine(self, tmp_path):
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        pou_file = tmp_path / "FB_HttpClient.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_HttpClient" Id="{55555555-5555-5555-5555-555555555555}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_HttpClient
VAR
    bExecute : BOOL;
END_VAR
]]></Declaration>
    <Implementation><![CDATA[]]></Implementation>
    <Method Name="Execute" Id="{55555555-5555-5555-5555-555555555556}">
      <Declaration><![CDATA[METHOD PUBLIC Execute : BOOL
VAR_INST
    _nState : INT;
END_VAR
]]></Declaration>
      <Implementation><![CDATA[
IF Execute THEN
    _nState := 1;
END_IF;

IF _nState = 1 THEN
    Execute := TRUE;
END_IF;
]]></Implementation>
    </Method>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        ws = WorkspaceIndex()
        ws.update_file(pou_file)

        diags = run_semantic_analysis(ws, pou_file)
        assert len(diags) == 0, f"Expected 0 diagnostics for Method returning BOOL with VAR_INST, got: {diags}"





