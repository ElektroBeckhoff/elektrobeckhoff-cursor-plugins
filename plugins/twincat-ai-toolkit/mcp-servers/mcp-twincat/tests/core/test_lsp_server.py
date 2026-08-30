"""Comprehensive unit and integration tests for twincat_core.lsp (pygls adapter)."""
import tempfile
from pathlib import Path
import pytest
import lsprotocol.types as lsp

from twincat_core.lsp import (
    TwinCatLanguageServer,
    create_lsp_server,
    diagnostic_to_lsp,
    get_diagnostics_for_file,
    handle_completion,
    handle_definition,
    handle_document_symbol,
    handle_formatting,
    handle_hover,
    handle_implementation,
    path_to_uri,
    position_from_lsp,
    position_to_lsp,
    span_to_range,
    symbol_to_document_symbol,
    uri_to_path,
)
from twincat_core.project import WorkspaceIndex
from twincat_core.semantic import Symbol, SymbolKind
from twincat_core.syntax import DiagnosticSeverity, Position, SourceSpan, SyntaxDiagnostic


SAMPLE_POU_XML = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Motor" Id="{11111111-2222-3333-4444-555555555555}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Motor
VAR_INPUT
    bEnable : BOOL := FALSE;
    nSpeed  : INT  := 0;
END_VAR
VAR_OUTPUT
    bRunning : BOOL := FALSE;
END_VAR
VAR
    _nCounter : UDINT := 0;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[IF bEnable THEN
    bRunning := TRUE;
    _nCounter := _nCounter + 1;
ELSE
    bRunning := FALSE;
END_IF;
]]></ST>
    </Implementation>
    <Method Name="M_Reset" Id="{22222222-3333-4444-5555-666666666666}">
      <Declaration><![CDATA[METHOD PUBLIC M_Reset : BOOL
VAR_INPUT
    bForce : BOOL;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[_nCounter := 0;
bRunning := FALSE;
M_Reset := TRUE;
]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>"""


class TestLspUtils:
    """Test URI, Range, Span, and Type conversion helpers."""

    def test_uri_path_roundtrip(self, tmp_path):
        test_file = tmp_path / "test.TcPOU"
        uri = path_to_uri(test_file)
        assert uri.startswith("file://")
        resolved = uri_to_path(uri)
        assert resolved == test_file.resolve()

    def test_position_and_span_conversions(self):
        core_pos = Position(line=10, col=5, offset=120)
        lsp_pos = position_to_lsp(core_pos)
        assert lsp_pos.line == 9
        assert lsp_pos.character == 4

        back_core = position_from_lsp(lsp_pos)
        assert back_core.line == 10
        assert back_core.col == 5

        core_span = SourceSpan.from_bounds(2, 1, 10, 5, 20, 100)
        lsp_range = span_to_range(core_span)
        assert lsp_range.start.line == 1
        assert lsp_range.start.character == 0
        assert lsp_range.end.line == 4
        assert lsp_range.end.character == 19

    def test_diagnostic_and_symbol_conversion(self):
        span = SourceSpan.from_bounds(3, 5, 20, 3, 10, 25)
        diag = SyntaxDiagnostic(message="Syntax error", span=span, severity=DiagnosticSeverity.ERROR, code="E001")
        lsp_diag = diagnostic_to_lsp(diag)
        assert lsp_diag.message == "Syntax error"
        assert lsp_diag.severity == lsp.DiagnosticSeverity.Error
        assert lsp_diag.source == "twincat"

        sym = Symbol(name="bActive", kind=SymbolKind.VARIABLE, span=span, type_ref="BOOL")
        lsp_sym = symbol_to_document_symbol(sym)
        assert lsp_sym.name == "bActive"
        assert lsp_sym.kind == lsp.SymbolKind.Variable
        assert lsp_sym.detail == "BOOL"


class TestLspHandlers:
    """Test core LSP feature handlers (Document Symbols, Definition, Hover, Formatting)."""

    def test_document_symbols_handler(self, tmp_path):
        pou_file = tmp_path / "FB_Motor.TcPOU"
        pou_file.write_text(SAMPLE_POU_XML, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)

        params = lsp.DocumentSymbolParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file))
        )
        symbols = handle_document_symbol(index, params)
        assert len(symbols) >= 1

        pou_sym = symbols[0]
        assert pou_sym.name == "FB_Motor"
        assert pou_sym.kind == lsp.SymbolKind.Class
        # Nested symbols (inputs, outputs, internal vars, methods)
        child_names = [c.name for c in pou_sym.children]
        assert "bEnable" in child_names
        assert "bRunning" in child_names
        assert "M_Reset" in child_names

    def test_definition_handler_local_var(self, tmp_path):
        pou_file = tmp_path / "FB_Motor.TcPOU"
        pou_file.write_text(SAMPLE_POU_XML, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)

        # In SAMPLE_POU_XML, line 17 is "      <ST><![CDATA[IF bEnable THEN" -> "bEnable" is around char 21
        params = lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file)),
            position=lsp.Position(line=16, character=22),  # 0-based -> line 17 ("bEnable")
        )
        location = handle_definition(index, params)
        assert location is not None
        assert uri_to_path(location.uri) == pou_file.resolve()

    def test_definition_handler_method_action_property(self, tmp_path):
        pou_with_all = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Device" Id="{11111111-2222-3333-4444-555555555555}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Device
VAR
    fbTimer : TON;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[
fbTimer.IN := TRUE;
M_Execute();
A_Start();
]]></ST>
    </Implementation>
    <Method Name="M_Execute" Id="{22222222-3333-4444-5555-666666666666}">
      <Declaration><![CDATA[METHOD M_Execute : BOOL
VAR_INPUT
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[M_Execute := TRUE;]]></ST>
      </Implementation>
    </Method>
    <Action Name="A_Start" Id="{33333333-4444-5555-6666-777777777777}">
      <Implementation>
        <ST><![CDATA[// Action logic]]></ST>
      </Implementation>
    </Action>
    <Property Name="nSpeed" Id="{44444444-5555-6666-7777-888888888888}">
      <Declaration><![CDATA[PROPERTY nSpeed : INT]]></Declaration>
      <Get Name="Get" Id="{55555555-6666-7777-8888-999999999999}">
        <Declaration><![CDATA[VAR END_VAR]]></Declaration>
        <Implementation>
          <ST><![CDATA[nSpeed := 100;]]></ST>
        </Implementation>
      </Get>
    </Property>
  </POU>
</TcPlcObject>"""
        dev_file = tmp_path / "FB_Device.TcPOU"
        dev_file.write_text(pou_with_all, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(dev_file)
        uri = path_to_uri(dev_file)

        # 1. Definition on local variable fbTimer (line 11, char 2 -> 0-based line 10)
        params_timer = lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=10, character=2),
        )
        loc_timer = handle_definition(index, params_timer)
        assert loc_timer is not None
        assert uri_to_path(loc_timer.uri) == dev_file.resolve()

        # 2. Definition on M_Execute inside POU Implementation (line 12, char 2 -> 0-based line 11)
        params_m = lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=11, character=2),
        )
        loc_m = handle_definition(index, params_m)
        assert loc_m is not None
        assert uri_to_path(loc_m.uri) == dev_file.resolve()

        # 3. Definition on A_Start inside POU Implementation (line 13, char 2 -> 0-based line 12)
        params_a = lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=12, character=2),
        )
        loc_a = handle_definition(index, params_a)
        assert loc_a is not None
        assert uri_to_path(loc_a.uri) == dev_file.resolve()

        # 4. External Library FB: TON (Declaration line 6, char 15 -> 0-based line 5)
        params_ton = lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=5, character=15),
        )
        # Definition returns None because TON is in external/standard library (no source file on disk)
        loc_ton = handle_definition(index, params_ton)
        assert loc_ton is None

        # 5. Hover on external Library FB still returns rich type info:
        params_ton_hover = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=5, character=15),
        )
        hover_ton = handle_hover(index, params_ton_hover)
        assert hover_ton is not None
        assert "TON" in hover_ton.contents.value

    def test_hover_handler(self, tmp_path):
        pou_file = tmp_path / "FB_Motor.TcPOU"
        pou_file.write_text(SAMPLE_POU_XML, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)

        # Hover over "nSpeed" on line 7 ("    nSpeed  : INT  := 0;") -> 0-based line 6, col 6
        params = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file)),
            position=lsp.Position(line=6, character=6),
        )
        hover = handle_hover(index, params)
        assert hover is not None
        assert "nSpeed" in hover.contents.value
        assert "INT" in hover.contents.value

    def test_rich_hover_handler_types_and_members(self, tmp_path):
        """Verify rich structured hover rendering for Function Blocks, Variables, and InfoSys entities."""
        pou_file = tmp_path / "FB_Motor.TcPOU"
        pou_file.write_text(SAMPLE_POU_XML, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)

        # 1. Hover on FB_Motor type declaration (line 4 in XML, col 45) -> 0-based line 3, char 45
        params_fb = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file)),
            position=lsp.Position(line=3, character=45),
        )
        hover_fb = handle_hover(index, params_fb)
        assert hover_fb is not None
        assert "FUNCTION_BLOCK FB_Motor" in hover_fb.contents.value
        assert "bEnable" in hover_fb.contents.value
        assert "bRunning" in hover_fb.contents.value

        # 2. Hover on M_Reset method (line 26 in XML, col 45) -> 0-based line 25, char 45
        params_m = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file)),
            position=lsp.Position(line=25, character=45),
        )
        hover_m = handle_hover(index, params_m)
        assert hover_m is not None
        assert "METHOD M_Reset : BOOL" in hover_m.contents.value

    def test_completion_member_access_and_scope(self, tmp_path):
        """Verify IntelliSense auto-completion for member access (.) and scope."""
        dut_file = tmp_path / "ST_Param.TcDUT"
        dut_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_Param" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[TYPE ST_Param :
STRUCT
    fSpeed : LREAL;
    bActive : BOOL;
END_STRUCT
END_TYPE]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        pou_file = tmp_path / "FB_Device.TcPOU"
        pou_text = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Device" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Device
VAR
    stConfig : ST_Param;
    _fbTimer : TON;
    _nCounter : INT;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[stConfig.
_fbTimer.

]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""
        pou_file.write_text(pou_text, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(dut_file)
        index.update_file(pou_file)

        uri = path_to_uri(pou_file)

        # 1. Completion on "stConfig." (line 12 in XML, col 28) -> 0-based line 11, col 28
        params_st = lsp.CompletionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=11, character=28),
        )
        comp_st = handle_completion(index, params_st)
        assert comp_st is not None
        labels_st = [item.label for item in comp_st.items]
        assert "fSpeed" in labels_st
        assert "bActive" in labels_st

        # 2. Completion on "_fbTimer." (line 13 in XML, col 9) -> 0-based line 12, col 9
        params_ton = lsp.CompletionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=12, character=9),
        )
        comp_ton = handle_completion(index, params_ton)
        assert comp_ton is not None
        labels_ton = [item.label.upper() for item in comp_ton.items]
        assert "IN" in labels_ton
        assert "PT" in labels_ton
        assert "Q" in labels_ton
        assert "ET" in labels_ton

        # 3. Scope completion (free typing, line 14, char 0) -> 0-based line 13, col 0
        params_scope = lsp.CompletionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=13, character=0),
        )
        comp_scope = handle_completion(index, params_scope)
        assert comp_scope is not None
        labels_scope = [item.label for item in comp_scope.items]
        assert "stConfig" in labels_scope
        assert "_nCounter" in labels_scope
        assert "IF" in labels_scope
        assert "CASE" in labels_scope
        assert "ST_Param" in labels_scope

    def test_semantic_diagnostics_handler(self, tmp_path):
        """Verify semantic diagnostics reporting unknown types and duplicate identifiers."""
        # POU with an unknown type and a duplicate variable
        pou_file = tmp_path / "FB_Invalid.TcPOU"
        pou_text = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Invalid" Id="{33333333-3333-3333-3333-333333333333}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Invalid
VAR
    _nVal : INT;
    _nVal : BOOL;
    _stBad : UNKNOWN_NON_EXISTENT_DUT;
    _fbClient : FB_IotHttpClient;
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>"""
        pou_file.write_text(pou_text, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)

        diags = get_diagnostics_for_file(index, pou_file)
        assert len(diags) >= 2

        messages = [d.message for d in diags]
        assert any("Duplicate identifier '_nVal'" in m for m in messages)
        assert any("Unknown type 'UNKNOWN_NON_EXISTENT_DUT'" in m for m in messages)
        # FB_IotHttpClient is a known Beckhoff type via InfoSys, so it must not trigger an error
        assert not any("FB_IotHttpClient" in m for m in messages)

    def test_implementation_handler_pou_and_methods(self, tmp_path):
        """Verify Go to Implementation navigates to implementation bodies instead of declaration headers."""
        pou_file = tmp_path / "FB_Motor.TcPOU"
        pou_file.write_text(SAMPLE_POU_XML, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)
        uri = path_to_uri(pou_file)

        # 1. Definition vs Implementation on FB_Motor (line 4 in XML, col 45) -> 0-based line 3, col 45
        params_fb = lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=3, character=45),
        )
        def_loc = handle_definition(index, params_fb)
        impl_loc = handle_implementation(index, params_fb)

        assert def_loc is not None
        assert impl_loc is not None
        # Implementation is in Implementation ST CDATA (line 15+)
        assert impl_loc.range.start.line > def_loc.range.start.line

        # 2. Implementation on Method M_Reset (line 26 in XML, col 45) -> 0-based line 25, col 45
        params_m = lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=25, character=45),
        )
        impl_m = handle_implementation(index, params_m)
        assert impl_m is not None
        # Method Implementation is inside the Method's Implementation CDATA body
        assert impl_m.range.start.line > 25

    def test_implementation_handler_interfaces(self, tmp_path):
        """Verify Go to Implementation on Interface navigates to implementing Function Blocks."""
        itf_file = tmp_path / "I_Device.TcIO"
        itf_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_Device" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[INTERFACE I_Device
]]></Declaration>
    <Method Name="M_Run" Id="{22222222-2222-2222-2222-222222222222}">
      <Declaration><![CDATA[METHOD M_Run : BOOL
]]></Declaration>
    </Method>
  </Itf>
</TcPlcObject>""", encoding="utf-8")

        pou_file = tmp_path / "FB_DeviceImpl.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_DeviceImpl" Id="{33333333-3333-3333-3333-333333333333}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_DeviceImpl IMPLEMENTS I_Device
VAR
    _nState : INT;
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[_nState := 1;]]></ST></Implementation>
    <Method Name="M_Run" Id="{44444444-4444-4444-4444-444444444444}">
      <Declaration><![CDATA[METHOD M_Run : BOOL
]]></Declaration>
      <Implementation><ST><![CDATA[M_Run := TRUE;]]></ST></Implementation>
    </Method>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(itf_file)
        index.update_file(pou_file)

        # 1. Implementation on I_Device in I_Device.TcIO (line 4 in XML, col 38) -> 0-based line 3, col 37
        params_itf = lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(itf_file)),
            position=lsp.Position(line=3, character=37),
        )
        impl_itf = handle_implementation(index, params_itf)
        assert impl_itf is not None
        assert uri_to_path(impl_itf.uri) == pou_file.resolve()

        # 2. Implementation on Method M_Run in I_Device.TcIO (line 7 in XML, col 36) -> 0-based line 6, col 35
        params_m = lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(itf_file)),
            position=lsp.Position(line=6, character=35),
        )
        impl_m = handle_implementation(index, params_m)
        assert impl_m is not None
        assert uri_to_path(impl_m.uri) == pou_file.resolve()
        assert impl_m is not None
        assert uri_to_path(impl_m.uri) == pou_file.resolve()

    def test_implementation_external_symbols_returns_none(self, tmp_path):
        """Verify Go to Implementation on external library symbols returns None gracefully."""
        pou_file = tmp_path / "FB_ExtTest.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_ExtTest" Id="{55555555-5555-5555-5555-555555555555}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_ExtTest
VAR
    fbTimer : TON;
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[fbTimer(IN := TRUE);]]></ST></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)

        # Implementation on external TON (line 4 in XML, col 16) -> 0-based line 3, col 15
        params_ton = lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file)),
            position=lsp.Position(line=3, character=15),
        )
        impl_ton = handle_implementation(index, params_ton)
        assert impl_ton is None

    def test_formatting_handler(self, tmp_path):
        unformatted_pou = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Unformatted" Id="{11111111-2222-3333-4444-555555555555}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Unformatted
VAR
a:INT:=1;
bLongName:BOOL:=FALSE;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[IF a=1 THEN
bLongName:=TRUE;
END_IF;
]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""
        pou_file = tmp_path / "FB_Unformatted.TcPOU"
        pou_file.write_text(unformatted_pou, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)

        params = lsp.DocumentFormattingParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file)),
            options=lsp.FormattingOptions(tab_size=4, insert_spaces=True),
        )
        edits = handle_formatting(index, params)
        assert len(edits) == 1
        formatted_text = edits[0].new_text
        assert "a         : INT" in formatted_text or "a : INT" in formatted_text or "bLongName : BOOL" in formatted_text

    def test_hover_with_variable_and_field_comments(self, tmp_path):
        """Verify that line comments (//) and block comments (* *) on variables appear in Hover."""
        pou_code = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_MotorControl" Id="{33333333-3333-3333-3333-333333333333}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_MotorControl
VAR_INPUT
    bEnable : BOOL := FALSE; // Enable flag for motor drive
    (* Desired target speed in RPM *)
    nTargetSpeed : INT := 1500;
END_VAR
VAR_OUTPUT
    bRunning : BOOL; (* Drive is currently running *)
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[bEnable := TRUE;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""
        pou_file = tmp_path / "FB_MotorControl.TcPOU"
        pou_file.write_text(pou_code, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)
        uri = path_to_uri(pou_file)

        # 1. Hover on bEnable (0-based line 5, col 8)
        params_enable = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=5, character=8),
        )
        hover_enable = handle_hover(index, params_enable)
        assert hover_enable is not None
        assert "Enable flag for motor drive" in hover_enable.contents.value
        assert "(VARIABLE) bEnable : BOOL" in hover_enable.contents.value

        # 2. Hover on nTargetSpeed (0-based line 7, col 8)
        params_speed = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=7, character=8),
        )
        hover_speed = handle_hover(index, params_speed)
        assert hover_speed is not None
        assert "Desired target speed in RPM" in hover_speed.contents.value

        # 3. Hover on FB_MotorControl signature (0-based line 3, col 45)
        params_fb = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=3, character=45),
        )
        hover_fb = handle_hover(index, params_fb)
        assert hover_fb is not None
        assert "bEnable : BOOL; // Enable flag for motor drive" in hover_fb.contents.value


class TestLspServerIntegration:
    """Test TwinCatLanguageServer instance lifecycle and incremental diagnostics."""

    def test_server_creation_and_capabilities(self):
        server = create_lsp_server()
        assert isinstance(server, TwinCatLanguageServer)
        assert server.name == "twincat-lsp"

    def test_did_open_and_incremental_did_change_updates(self, tmp_path):
        pou_file = tmp_path / "FB_Test.TcPOU"
        pou_file.write_text(SAMPLE_POU_XML, encoding="utf-8")

        server = create_lsp_server()
        uri = path_to_uri(pou_file)

        # 1. didOpen with valid file -> 0 diagnostics
        open_params = lsp.DidOpenTextDocumentParams(
            text_document=lsp.TextDocumentItem(
                uri=uri,
                language_id="iecst",
                version=1,
                text=SAMPLE_POU_XML,
            )
        )
        server.text_document_publish_diagnostics = lambda *args, **kwargs: None  # Mock send
        # Trigger index update directly through server workspace_index
        server.workspace_index.update_file(pou_file, text=SAMPLE_POU_XML)
        indexed = server.workspace_index.get_file(pou_file)
        assert indexed is not None
        assert len(indexed.diagnostics) == 0

        # 2. didChange with a syntax error (e.g. missing colon in variable declaration)
        broken_xml = SAMPLE_POU_XML.replace("bEnable : BOOL", "bEnable BOOL")
        server.workspace_index.update_file(pou_file, text=broken_xml)
        indexed_broken = server.workspace_index.get_file(pou_file)
        assert len(indexed_broken.diagnostics) > 0
        assert any("Expected ':'" in d.message or "colon" in d.message.lower() for d in indexed_broken.diagnostics)

        # 3. didChange fixing the syntax error
        server.workspace_index.update_file(pou_file, text=SAMPLE_POU_XML)
        indexed_fixed = server.workspace_index.get_file(pou_file)
        assert len(indexed_fixed.diagnostics) == 0

    def test_lsp_virtual_st_endpoints(self, tmp_path):
        pou_file = tmp_path / "FB_LspVirtual.TcPOU"
        pou_file.write_text(SAMPLE_POU_XML, encoding="utf-8")

        from twincat_core.lsp.handlers import (
            handle_virtual_st_get,
            handle_virtual_st_map_location,
            handle_virtual_st_save,
        )

        index = WorkspaceIndex()
        index.update_file(pou_file)
        uri = path_to_uri(pou_file)

        # 1. Get Virtual ST
        get_res = handle_virtual_st_get(index, uri)
        assert get_res["uri"] == uri
        assert "FUNCTION_BLOCK FB_Motor" in get_res["virtualSt"]
        assert len(get_res["sections"]) == 4

        # 2. Location mapping
        map_res = handle_virtual_st_map_location(index, uri, line=1, col=1, direction="toXml")
        assert map_res["line"] >= 1

        # 3. Save Virtual ST with modifications
        edited_st = get_res["virtualSt"].replace("bRunning : BOOL := FALSE;", "bRunning : BOOL := TRUE;\n    bFault : BOOL := FALSE;")
        save_res = handle_virtual_st_save(index, uri, edited_st)
        assert save_res["success"] is True
        assert "bFault : BOOL := FALSE;" in save_res["newXml"]
        assert 'Id="{11111111-2222-3333-4444-555555555555}"' in save_res["newXml"]

    def test_lsp_definition_fixture_isolation(self, tmp_path):
        """Verify Go to Definition inside a fixture file navigates to sibling fixture file, not solution."""
        sol_dir = tmp_path / "solution" / "plc_proj"
        fix_dir = tmp_path / "tests" / "fixtures" / "oneline"
        sol_dir.mkdir(parents=True)
        fix_dir.mkdir(parents=True)

        dut_sol = sol_dir / "ST_Cfg.TcDUT"
        dut_sol.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_Cfg" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[TYPE ST_Cfg :
STRUCT
    nVal : INT;
END_STRUCT
END_TYPE]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        pou_sol = sol_dir / "FB_Ctrl.TcPOU"
        pou_sol.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Ctrl" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Ctrl
VAR
    stData : ST_Cfg;
END_VAR]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        dut_fix = fix_dir / "ST_Cfg.TcDUT"
        dut_fix.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_Cfg" Id="{33333333-3333-3333-3333-333333333333}">
    <Declaration><![CDATA[TYPE ST_Cfg :
STRUCT
    nVal : INT;
END_STRUCT
END_TYPE]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        pou_fix = fix_dir / "FB_Ctrl.TcPOU"
        pou_fix.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Ctrl" Id="{44444444-4444-4444-4444-444444444444}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Ctrl
VAR
    stData : ST_Cfg;
END_VAR]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(dut_sol)
        index.update_file(pou_sol)
        index.update_file(dut_fix)
        index.update_file(pou_fix)

        # Definition on ST_Cfg in fixture FB_Ctrl (Line 6, character 15)
        uri_fix = path_to_uri(pou_fix)
        params_fix = lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri_fix),
            position=lsp.Position(line=5, character=15),
        )
        loc_fix = handle_definition(index, params_fix)
        assert loc_fix is not None
        assert uri_to_path(loc_fix.uri) == dut_fix.resolve()

        # Definition on ST_Cfg in solution FB_Ctrl (Line 6, character 15)
        uri_sol = path_to_uri(pou_sol)
        params_sol = lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri_sol),
            position=lsp.Position(line=5, character=15),
        )
        loc_sol = handle_definition(index, params_sol)
        assert loc_sol is not None
        assert uri_to_path(loc_sol.uri) == dut_sol.resolve()

    def test_hover_outside_cdata_on_xml_tags_returns_none(self, tmp_path):
        """Verify that hovering on XML tags like <Implementation>, <POU>, etc. does not show ST hover."""
        pou_file = tmp_path / "FB_Sample.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Sample" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Sample
VAR
    nVal : INT;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[nVal := 10;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)
        uri = path_to_uri(pou_file)

        # 1. Hover on <Implementation> (line 8, char 6 -> 0-based line 7, char 6)
        params_impl = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=7, character=6),
        )
        assert handle_hover(index, params_impl) is None

        # 2. Hover on </Implementation> (line 10, char 6 -> 0-based line 9, char 6)
        params_close = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=9, character=6),
        )
        assert handle_hover(index, params_close) is None

        # 3. Hover on <?xml (line 1, char 2 -> 0-based line 0, char 2)
        params_xml = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=0, character=2),
        )
        assert handle_hover(index, params_xml) is None

    def test_hover_named_call_parameters_resolves_field(self, tmp_path):
        """Verify that hovering on named call parameters like IN := or CLK := resolves the input variable."""
        pou_file = tmp_path / "FB_Caller.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Caller" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Caller
VAR
    fbTimer : TON;
    bStart  : BOOL;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[fbTimer(IN := bStart, PT := T#1S);]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)
        uri = path_to_uri(pou_file)

        # Hover on IN (0-based line 9, char 28)
        params_in = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=9, character=28),
        )
        hover_in = handle_hover(index, params_in)
        assert hover_in is not None
        assert "(VARIABLE) IN : BOOL" in hover_in.contents.value

        # Hover on PT (0-based line 9, char 43)
        params_pt = lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=9, character=43),
        )
        hover_pt = handle_hover(index, params_pt)
        assert hover_pt is not None
        assert "(VARIABLE) PT : TIME" in hover_pt.contents.value



