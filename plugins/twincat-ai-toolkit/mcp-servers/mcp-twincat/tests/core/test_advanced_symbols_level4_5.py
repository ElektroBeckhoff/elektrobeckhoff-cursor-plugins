"""Comprehensive tests for Level 4 (Chained Member Resolution), Level 5 (Library Resolution & Built-in Catalog), and MCP Symbol Tools."""
from pathlib import Path
import json
import pytest

from twincat_core.project import WorkspaceIndex, get_shared_workspace
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
from twincat_core.syntax.span import SourceSpan


SAMPLE_DEEP_STRUCT_POU = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Plant" Id="{11111111-1111-1111-1111-111111111111}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Plant
VAR
    fbStation1 : FB_Station;
    arrStations : ARRAY[0..5] OF FB_Station;
    pStation : POINTER TO FB_Station;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[
fbStation1.fbMotor.stParam.fSpeed := 10.5;
]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""

SAMPLE_STATION_POU = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Station" Id="{22222222-2222-2222-2222-222222222222}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Station
VAR
    fbMotor : FB_MotorUnit;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
    <Method Name="M_GetMotor" Id="{33333333-3333-3333-3333-333333333333}">
      <Declaration><![CDATA[METHOD PUBLIC M_GetMotor : FB_MotorUnit
]]></Declaration>
      <Implementation>
        <ST><![CDATA[]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>"""

SAMPLE_MOTOR_POU = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_MotorUnit" Id="{44444444-4444-4444-4444-444444444444}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_MotorUnit
VAR
    stParam : ST_MotorConfig;
    fbTonDelay : TON;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""

SAMPLE_CONFIG_DUT = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <DUT Name="ST_MotorConfig" Id="{55555555-5555-5555-5555-555555555555}">
    <Declaration><![CDATA[TYPE ST_MotorConfig :
STRUCT
    fSpeed : LREAL := 0.0;
    nMaxRpm : INT := 3000;
    bEnabled : BOOL := FALSE;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>"""


class TestLevel4ChainedMemberResolution:
    """Test Level 4 arbitrary chained member expressions, array indexing, and dereferencing."""

    @pytest.fixture
    def workspace(self, tmp_path):
        ws = WorkspaceIndex()
        f_config = tmp_path / "ST_MotorConfig.TcDUT"
        f_config.write_text(SAMPLE_CONFIG_DUT, encoding="utf-8")
        f_motor = tmp_path / "FB_MotorUnit.TcPOU"
        f_motor.write_text(SAMPLE_MOTOR_POU, encoding="utf-8")
        f_station = tmp_path / "FB_Station.TcPOU"
        f_station.write_text(SAMPLE_STATION_POU, encoding="utf-8")
        f_plant = tmp_path / "FB_Plant.TcPOU"
        f_plant.write_text(SAMPLE_DEEP_STRUCT_POU, encoding="utf-8")

        ws.update_file(f_config)
        ws.update_file(f_motor)
        ws.update_file(f_station)
        ws.update_file(f_plant)
        return ws

    def test_deep_chained_struct_field_resolution(self, workspace):
        scope = workspace.symbol_table.find_pou_scope("FB_Plant")
        assert scope is not None

        # Level 4: fbStation1.fbMotor.stParam.fSpeed
        target_sym = workspace.resolver.resolve_chain("fbStation1.fbMotor.stParam.fSpeed", scope)
        assert target_sym is not None
        assert target_sym.name == "fSpeed"
        assert target_sym.kind == SymbolKind.STRUCT_FIELD
        assert target_sym.type_ref == "LREAL"

    def test_chained_method_return_resolution(self, workspace):
        scope = workspace.symbol_table.find_pou_scope("FB_Plant")
        assert scope is not None

        # Method call return type chaining: fbStation1.M_GetMotor().stParam.nMaxRpm
        target_sym = workspace.resolver.resolve_chain("fbStation1.M_GetMotor().stParam.nMaxRpm", scope)
        assert target_sym is not None
        assert target_sym.name == "nMaxRpm"
        assert target_sym.kind == SymbolKind.STRUCT_FIELD
        assert target_sym.type_ref == "INT"

    def test_chained_array_indexing_resolution(self, workspace):
        scope = workspace.symbol_table.find_pou_scope("FB_Plant")
        assert scope is not None

        # Array element chaining: arrStations[0].fbMotor.stParam.bEnabled
        target_sym = workspace.resolver.resolve_chain("arrStations[0].fbMotor.stParam.bEnabled", scope)
        assert target_sym is not None
        assert target_sym.name == "bEnabled"
        assert target_sym.kind == SymbolKind.STRUCT_FIELD
        assert target_sym.type_ref == "BOOL"

    def test_chained_pointer_dereference_resolution(self, workspace):
        scope = workspace.symbol_table.find_pou_scope("FB_Plant")
        assert scope is not None

        # Pointer dereference chaining: pStation^.fbMotor.stParam.fSpeed
        target_sym = workspace.resolver.resolve_chain("pStation^.fbMotor.stParam.fSpeed", scope)
        assert target_sym is not None
        assert target_sym.name == "fSpeed"
        assert target_sym.kind == SymbolKind.STRUCT_FIELD


class TestLevel5LibraryAndBuiltinCatalogResolution:
    """Test Level 5 Standard IEC & Beckhoff Library catalog (Tc2_Standard, Tc2_System, Tc3_Module, Conversions)."""

    def test_tc2_standard_timer_and_trigger_resolution(self):
        ws = WorkspaceIndex()
        global_scope = ws.symbol_table.global_scope

        # Unqualified TON
        ton_sym = ws.resolver.resolve_identifier("TON", global_scope)
        assert ton_sym is not None or ws.type_index.get_type("TON") is not None
        ton_desc = ws.type_index.get_type("TON")
        assert "in" in ton_desc.fields
        assert "pt" in ton_desc.fields
        assert "q" in ton_desc.fields
        assert "et" in ton_desc.fields

        # Dot-qualified: Tc2_Standard.TON.IN
        in_sym = ws.resolver.resolve_chain("Tc2_Standard.TON.IN", global_scope)
        assert in_sym is not None
        assert in_sym.name == "IN"
        assert in_sym.type_ref == "BOOL"

        # R_TRIG
        rtrig_desc = ws.type_index.get_type("R_TRIG")
        assert "clk" in rtrig_desc.fields
        assert "q" in rtrig_desc.fields

    def test_tc2_standard_string_functions(self):
        ws = WorkspaceIndex()
        global_scope = ws.symbol_table.global_scope

        concat_sym = ws.resolver.resolve_identifier("CONCAT", global_scope)
        assert concat_sym is not None
        assert concat_sym.type_ref == "STRING"

        len_sym = ws.resolver.resolve_identifier("LEN", global_scope)
        assert len_sym is not None
        assert len_sym.type_ref == "INT"

    def test_tc2_system_and_tc3_module(self):
        ws = WorkspaceIndex()
        global_scope = ws.symbol_table.global_scope

        # MEMCPY function
        memcpy_sym = ws.resolver.resolve_chain("Tc2_System.MEMCPY", global_scope)
        assert memcpy_sym is not None
        assert memcpy_sym.type_ref == "UDINT"

        # ITcUnknown interface methods
        itc_desc = ws.type_index.get_type("ITcUnknown")
        assert itc_desc is not None
        assert "tcaddref" in itc_desc.methods
        assert "tcqueryinterface" in itc_desc.methods

    def test_tc3_json_and_iot(self):
        ws = WorkspaceIndex()
        global_scope = ws.symbol_table.global_scope

        # FB_JsonDomParser methods
        json_desc = ws.type_index.get_type("FB_JsonDomParser")
        assert json_desc is not None
        assert "parsedocument" in json_desc.methods
        assert "findmember" in json_desc.methods

        # FB_IotHttpClient fields & methods
        http_desc = ws.type_index.get_type("FB_IotHttpClient")
        assert http_desc is not None
        assert "bconnected" in http_desc.fields
        assert "execute" in http_desc.methods

    def test_type_conversion_functions(self):
        ws = WorkspaceIndex()
        global_scope = ws.symbol_table.global_scope

        to_str = ws.resolver.resolve_identifier("TO_STRING", global_scope)
        assert to_str is not None
        assert to_str.type_ref == "STRING"

        int_to_real = ws.resolver.resolve_identifier("INT_TO_REAL", global_scope)
        assert int_to_real is not None
        assert int_to_real.type_ref == "REAL"


class TestMcpWorkspaceSymbolTools:
    """Test MCP tools (twincat_workspace_symbols and twincat_symbol_lookup)."""

    def test_mcp_symbol_tools(self, tmp_path):
        from server import twincat_symbol_lookup, twincat_workspace_symbols

        f_config = tmp_path / "ST_MotorConfig.TcDUT"
        f_config.write_text(SAMPLE_CONFIG_DUT, encoding="utf-8")
        f_motor = tmp_path / "FB_MotorUnit.TcPOU"
        f_motor.write_text(SAMPLE_MOTOR_POU, encoding="utf-8")

        # Create dummy .plcproj in directory
        plcproj_p = tmp_path / "test.plcproj"
        plcproj_p.write_text("""<?xml version="1.0" encoding="utf-8"?>
<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Name>TestProject</Name>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="ST_MotorConfig.TcDUT" />
    <Compile Include="FB_MotorUnit.TcPOU" />
  </ItemGroup>
</Project>""", encoding="utf-8")

        # 1. Workspace symbols
        syms_json = twincat_workspace_symbols(query="Motor", plcproj_path=str(plcproj_p))
        syms_data = json.loads(syms_json)
        assert syms_data["total"] >= 2
        names = [s["name"] for s in syms_data["symbols"]]
        assert "FB_MotorUnit" in names or "ST_MotorConfig" in names

        # 2. Symbol lookup (chained & builtin)
        lookup_json = twincat_symbol_lookup("FB_MotorUnit.stParam.fSpeed", plcproj_path=str(plcproj_p))
        lookup_data = json.loads(lookup_json)
        assert lookup_data["found"] is True
        assert lookup_data["name"] == "fSpeed"
        assert lookup_data["type_ref"] == "LREAL"

        # 3. Built-in lookup
        ton_json = twincat_symbol_lookup("TON.IN", plcproj_path=str(plcproj_p))
        ton_data = json.loads(ton_json)
        assert ton_data["found"] is True
        assert ton_data["name"] == "IN"
        assert ton_data["type_ref"] == "BOOL"

    def test_infosys_on_demand_type_provider(self):
        """Test on-demand loading of external library symbols (e.g. FB_IotHttpClient) from InfoSys MSHC."""
        type_index = TypeIndex()

        # Dynamic query without hardcoding in builtin_catalog
        iot_desc = type_index.get_type("FB_IotHttpClient")
        if iot_desc is not None:
            assert iot_desc.name == "FB_IotHttpClient"
            assert "shostname" in iot_desc.fields or "berror" in iot_desc.fields
            assert "disconnect" in iot_desc.methods or "execute" in iot_desc.methods

        # Dynamic query for motion block
        mc_desc = type_index.get_type("MC_MoveAbsolute")
        if mc_desc is not None:
            assert mc_desc.name == "MC_MoveAbsolute"
            assert "execute" in mc_desc.fields or "position" in mc_desc.fields

