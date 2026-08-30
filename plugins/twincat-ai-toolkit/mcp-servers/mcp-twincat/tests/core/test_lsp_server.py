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
    handle_type_definition,
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

    def test_lsp_diagnostics_line_numbers_in_xml(self, tmp_path):
        """Verify that diagnostics in both Declaration and Implementation map to exact XML document lines."""
        pou_file = tmp_path / "FB_LineTest.TcPOU"
        pou_text = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_LineTest" Id="{11111111-2222-3333-4444-555555555555}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_LineTest
VAR
    bFlag : BOOL;
    nNum  : INT;
    _bad  : UNKNOWN_TYPE_XYZ;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[
nNum := 10;
bFlag := nNum;
]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""
        pou_file.write_text(pou_text, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)

        diags = get_diagnostics_for_file(index, pou_file)
        assert len(diags) == 2

        # 1. Declaration error: UNKNOWN_TYPE_XYZ is on XML line 8 (0-based line 7)
        decl_diag = next(d for d in diags if "UNKNOWN_TYPE_XYZ" in d.message)
        assert decl_diag.range.start.line == 7  # 0-based index of XML line 8

        # 2. Implementation error: bFlag := nNum; is on XML line 14 (0-based line 13)
        impl_diag = next(d for d in diags if "Cannot convert" in d.message)
        assert impl_diag.range.start.line == 13  # 0-based index of XML line 14

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
        # Check XML structure is indented
        assert "  <POU Name=\"FB_Unformatted\"" in formatted_text
        assert "    <Declaration><![CDATA[" in formatted_text

        # Verify idempotence on second pass
        edits_second_pass = handle_formatting(index, params, unsaved_text=formatted_text)
        assert len(edits_second_pass) == 0

        # Verify CRLF inputs do not produce blank line duplication
        crlf_input = unformatted_pou.replace("\n", "\r\n")
        edits_crlf = handle_formatting(index, params, unsaved_text=crlf_input)
        assert len(edits_crlf) == 1
        assert "\r\r\n" not in edits_crlf[0].new_text
        assert "\n\n\n\n" not in edits_crlf[0].new_text

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
        assert "bEnable" in hover_fb.contents.value and "Enable flag for motor drive" in hover_fb.contents.value
        assert "nTargetSpeed" in hover_fb.contents.value and "Desired target speed in RPM" in hover_fb.contents.value

    def test_hover_public_interface_only_excludes_internal_vars(self, tmp_path):
        """Verify that Hover on an FB, Function, and Method shows ONLY public VAR_INPUT/OUTPUT/IN_OUT with comments, excluding internal VAR."""
        pou_code = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_ServiceCoordinator" Id="{44444444-4444-4444-4444-444444444444}">
    <Declaration><![CDATA[(* High-level multi-stage process service coordinator *)
FUNCTION_BLOCK FB_ServiceCoordinator
VAR_INPUT
    bStartCommand : BOOL; // Start command from supervisory HMI
    nCycleTimeout_ms : UDINT := 5000; // Max cycle timeout in milliseconds
END_VAR
VAR_IN_OUT
    stSharedBus : ST_Param; // Shared system bus reference
END_VAR
VAR_OUTPUT
    bBusy : BOOL; // True when cycle is active
    bDone : BOOL; // High pulse on completion
    bError : BOOL; // Error indicator
END_VAR
VAR
    _nInternalState : INT := 0; // Private state machine index
    _tTimerElapsed : TIME; // Internal accumulator
    _fbInternalBuffer : ARRAY[1..100] OF BYTE; // Private ring buffer
END_VAR
VAR_TEMP
    _nTempCounter : DINT;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[;]]></ST>
    </Implementation>
    <Method Name="M_Configure" Id="{55555555-5555-5555-5555-555555555555}">
      <Declaration><![CDATA[(* Configures service coordinator runtime parameters *)
METHOD PUBLIC M_Configure : BOOL
VAR_INPUT
    nNewTimeout : UDINT; // New timeout in ms
END_VAR
VAR
    _nLocalSecret : INT;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[M_Configure := TRUE;]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>"""
        pou_file = tmp_path / "FB_ServiceCoordinator.TcPOU"
        pou_file.write_text(pou_code, encoding="utf-8")

        func_code = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="F_CalculatePayload" Id="{66666666-6666-6666-6666-666666666666}">
    <Declaration><![CDATA[(* Calculates raw sensor telemetry payload *)
FUNCTION F_CalculatePayload : LREAL
VAR_INPUT
    fRawSensorA : LREAL; // Raw channel A reading in volts
    fRawSensorB : LREAL; // Raw channel B reading in volts
END_VAR
VAR
    _fScaleFactor : LREAL := 1.25;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[F_CalculatePayload := (fRawSensorA + fRawSensorB) * _fScaleFactor;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""
        func_file = tmp_path / "F_CalculatePayload.TcPOU"
        func_file.write_text(func_code, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)
        index.update_file(func_file)

        # 1. Hover on FB_ServiceCoordinator (0-based line 4, col 30)
        h_fb = handle_hover(index, lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file)),
            position=lsp.Position(line=4, character=30),
        ))
        assert h_fb is not None
        v_fb = h_fb.contents.value
        # Public inputs & outputs & in_outs present with comments
        assert "VAR_INPUT" in v_fb
        assert "bStartCommand" in v_fb and "Start command from supervisory HMI" in v_fb
        assert "nCycleTimeout_ms" in v_fb and "Max cycle timeout in milliseconds" in v_fb
        assert "VAR_IN_OUT" in v_fb
        assert "stSharedBus" in v_fb and "Shared system bus reference" in v_fb
        assert "VAR_OUTPUT" in v_fb
        assert "bBusy" in v_fb and "True when cycle is active" in v_fb
        assert "bDone" in v_fb and "High pulse on completion" in v_fb
        # Internal private variables are completely excluded
        assert "_nInternalState" not in v_fb
        assert "_tTimerElapsed" not in v_fb
        assert "_fbInternalBuffer" not in v_fb
        assert "_nTempCounter" not in v_fb
        # Doc comment on FB present
        assert "High-level multi-stage process service coordinator" in v_fb

        # 2. Hover on Method M_Configure (0-based line 31, col 16)
        h_m = handle_hover(index, lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file)),
            position=lsp.Position(line=31, character=16),
        ))
        assert h_m is not None
        v_m = h_m.contents.value
        assert "METHOD M_Configure : BOOL" in v_m
        assert "VAR_INPUT" in v_m
        assert "nNewTimeout" in v_m and "New timeout in ms" in v_m
        assert "_nLocalSecret" not in v_m
        assert "Configures service coordinator runtime parameters" in v_m

        # 3. Hover on Function F_CalculatePayload (0-based line 4, col 15)
        h_fn = handle_hover(index, lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(func_file)),
            position=lsp.Position(line=4, character=15),
        ))
        assert h_fn is not None
        v_fn = h_fn.contents.value
        assert "FUNCTION F_CalculatePayload : LREAL" in v_fn
        assert "VAR_INPUT" in v_fn
        assert "fRawSensorA" in v_fn and "Raw channel A reading in volts" in v_fn
        assert "fRawSensorB" in v_fn and "Raw channel B reading in volts" in v_fn
        assert "_fScaleFactor" not in v_fn
        assert "Calculates raw sensor telemetry payload" in v_fn

    def test_hover_infosys_external_fb_and_function_signatures(self, tmp_path):
        """Verify that InfoSys external FBs (TON, FB_FileOpen) and Functions (MEMCPY, ADSLOGSTR) render structured signatures with parameter doc-comments."""
        pou_code = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_UsageTest" Id="{77777777-7777-7777-7777-777777777777}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_UsageTest
VAR
    fbTimer : TON;
    fbFile : FB_FileOpen;
    fbJson : FB_JsonDomParser;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[fbTimer.IN := TRUE;
fbFile.bExecute := TRUE;
fbJson.NewDocument();
]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""
        pou_file = tmp_path / "FB_UsageTest.TcPOU"
        pou_file.write_text(pou_code, encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)
        uri = path_to_uri(pou_file)

        # 1. Hover on 'TON' type on line 6 (0-based line 5, col 15)
        h_ton = handle_hover(index, lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=5, character=15),
        ))
        assert h_ton is not None
        v_ton = h_ton.contents.value
        assert "FUNCTION_BLOCK TON" in v_ton
        assert "VAR_INPUT" in v_ton
        assert "IN" in v_ton and "BOOL" in v_ton
        assert "PT" in v_ton and "TIME" in v_ton
        assert "VAR_OUTPUT" in v_ton
        assert "Q" in v_ton and "BOOL" in v_ton
        assert "ET" in v_ton and "TIME" in v_ton
        assert "**Library:** `Tc2_Standard`" in v_ton

        # 2. Hover on member 'IN' on line 12 (0-based line 11, col 28)
        h_in = handle_hover(index, lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=11, character=28),
        ))
        assert h_in is not None
        v_in = h_in.contents.value
        assert "(VARIABLE) IN : BOOL" in v_in
        assert "Rising edge: Start timer" in v_in

        # 3. Hover on 'FB_FileOpen' type on line 7 (0-based line 6, col 15)
        h_file = handle_hover(index, lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=6, character=15),
        ))
        assert h_file is not None
        v_file = h_file.contents.value
        assert "FUNCTION_BLOCK FB_FileOpen" in v_file
        assert "sNetId" in v_file and "T_AmsNetId" in v_file
        assert "bExecute" in v_file and "BOOL" in v_file
        assert "bBusy" in v_file and "BOOL" in v_file
        assert "bError" in v_file and "BOOL" in v_file
        assert "**Library:** `Tc2_System`" in v_file

        # 4. Hover on 'NewDocument' method of FB_JsonDomParser on line 14 (0-based line 13, col 8)
        h_newdoc = handle_hover(index, lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=13, character=8),
        ))
        assert h_newdoc is not None
        v_newdoc = h_newdoc.contents.value
        assert "METHOD NewDocument" in v_newdoc
        assert "**Library:** `Tc3_JsonXml`" in v_newdoc
        assert "**Defined in:** `FB_JsonDomParser`" in v_newdoc

    def test_all_twincat3_types_definition_implementation_type_definition_and_hover(self, tmp_path):
        """Exhaustive test verifying ALL TwinCAT3 types: POU, Method, Property, Action, Interface, Struct, Enum, Union, Alias, GVL."""
        # 1. Struct DUT
        dut_struct = tmp_path / "ST_Config.TcDUT"
        dut_struct.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_Config" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[TYPE ST_Config :
STRUCT
    nId : INT := 1; // Node identifier
    fThreshold : LREAL := 25.5; // Trigger threshold
END_STRUCT
END_TYPE]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        # 2. Enum DUT
        dut_enum = tmp_path / "E_State.TcDUT"
        dut_enum.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="E_State" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[TYPE E_State :
(
    Init := 0, // Initial state
    Running := 10, // Active processing
    Error := 99 // Fault state
);
END_TYPE]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        # 3. Union DUT
        dut_union = tmp_path / "U_RawWord.TcDUT"
        dut_union.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="U_RawWord" Id="{33333333-3333-3333-3333-333333333333}">
    <Declaration><![CDATA[TYPE U_RawWord :
UNION
    wValue : WORD;
    bLow : BYTE;
END_UNION
END_TYPE]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        # 4. Alias DUT
        dut_alias = tmp_path / "T_Identifier.TcDUT"
        dut_alias.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="T_Identifier" Id="{44444444-4444-4444-4444-444444444444}">
    <Declaration><![CDATA[TYPE T_Identifier : STRING(30);
END_TYPE]]></Declaration>
  </DUT>
</TcPlcObject>""", encoding="utf-8")

        # 5. GVL
        gvl_file = tmp_path / "GVL_App.TcGVL"
        gvl_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <GVL Name="GVL_App" Id="{55555555-5555-5555-5555-555555555555}">
    <Declaration><![CDATA[{attribute 'qualified_only'}
VAR_GLOBAL
    nGlobalCount : UDINT := 0; // Global cycle counter
    stGlobalConfig : ST_Config; // Global machine parameter set
END_VAR]]></Declaration>
  </GVL>
</TcPlcObject>""", encoding="utf-8")

        # 6. Interface (.TcIO)
        itf_file = tmp_path / "I_Device.TcIO"
        itf_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_Device" Id="{66666666-6666-6666-6666-666666666666}">
    <Declaration><![CDATA[INTERFACE I_Device
]]></Declaration>
    <Method Name="M_Start" Id="{66666666-6666-6666-6666-777777777777}">
      <Declaration><![CDATA[METHOD M_Start : BOOL
VAR_INPUT
    bForce : BOOL;
END_VAR
]]></Declaration>
    </Method>
    <Property Name="P_Running" Id="{66666666-6666-6666-6666-888888888888}">
      <Declaration><![CDATA[PROPERTY P_Running : BOOL
]]></Declaration>
    </Property>
  </Itf>
</TcPlcObject>""", encoding="utf-8")

        # 7. FB implementing Interface (.TcPOU) with Method, Property, Action
        fb_file = tmp_path / "FB_DeviceImpl.TcPOU"
        fb_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_DeviceImpl" Id="{77777777-7777-7777-7777-777777777777}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_DeviceImpl IMPLEMENTS I_Device
VAR_INPUT
    bEnable : BOOL; // Enable device operation
END_VAR
VAR_OUTPUT
    bBusy : BOOL; // True when busy
END_VAR
VAR
    _bActive : BOOL;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[bBusy := bEnable;]]></ST>
    </Implementation>
    <Method Name="M_Start" Id="{77777777-7777-7777-7777-888888888888}">
      <Declaration><![CDATA[METHOD PUBLIC M_Start : BOOL
VAR_INPUT
    bForce : BOOL;
END_VAR
]]></Declaration>
      <Implementation>
        <ST><![CDATA[_bActive := TRUE;
M_Start := TRUE;]]></ST>
      </Implementation>
    </Method>
    <Property Name="P_Running" Id="{77777777-7777-7777-7777-999999999999}">
      <Declaration><![CDATA[PROPERTY PUBLIC P_Running : BOOL]]></Declaration>
      <Get Name="Get" Id="{77777777-7777-7777-7777-AAAAAAAAAAAA}">
        <Declaration><![CDATA[VAR
END_VAR
]]></Declaration>
        <Implementation>
          <ST><![CDATA[P_Running := _bActive;]]></ST>
        </Implementation>
      </Get>
    </Property>
    <Action Name="A_Reset" Id="{77777777-7777-7777-7777-BBBBBBBBBBBB}">
      <Implementation>
        <ST><![CDATA[_bActive := FALSE;]]></ST>
      </Implementation>
    </Action>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        # 8. Function (.TcPOU)
        func_file = tmp_path / "F_Compute.TcPOU"
        func_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="F_Compute" Id="{88888888-8888-8888-8888-888888888888}">
    <Declaration><![CDATA[FUNCTION F_Compute : LREAL
VAR_INPUT
    fIn : LREAL; // Input value
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[F_Compute := fIn * 2.0;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        # 9. Main POU using all types
        main_file = tmp_path / "MAIN.TcPOU"
        main_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="MAIN" Id="{99999999-9999-9999-9999-999999999999}">
    <Declaration><![CDATA[PROGRAM MAIN
VAR
    stCfg : ST_Config;
    eCurState : E_State;
    uData : U_RawWord;
    sId : T_Identifier;
    fbDev : FB_DeviceImpl;
    iDev : I_Device;
    fOut : LREAL;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[stCfg.nId := 5;
fbDev.M_Start(bForce := TRUE);
fbDev.A_Reset();
iDev := fbDev;
fOut := F_Compute(10.0);
GVL_App.nGlobalCount := 1;
]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        index = WorkspaceIndex()
        for f in [dut_struct, dut_enum, dut_union, dut_alias, gvl_file, itf_file, fb_file, func_file, main_file]:
            index.update_file(f)

        main_uri = path_to_uri(main_file)

        # A. Struct Variable: 'stCfg' on line 6 (0-based line 5, col 7)
        # 1. Definition (F12) -> returns declaration of stCfg in MAIN.TcPOU
        def_st = handle_definition(index, lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=5, character=7),
        ))
        assert def_st is not None
        assert def_st.uri == main_uri

        # 2. Type Definition -> returns ST_Config.TcDUT
        type_st = handle_type_definition(index, lsp.TypeDefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=5, character=7),
        ))
        assert type_st is not None
        assert type_st.uri == path_to_uri(dut_struct)

        # 3. Implementation (Ctrl+F12) -> returns ST_Config.TcDUT
        impl_st = handle_implementation(index, lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=5, character=7),
        ))
        assert impl_st is not None
        assert (impl_st.uri if isinstance(impl_st, lsp.Location) else impl_st[0].uri) == path_to_uri(dut_struct)

        # B. Interface Variable: 'iDev' on line 11 (0-based line 10, col 7)
        # 1. Definition -> returns declaration of iDev in MAIN.TcPOU
        def_idev = handle_definition(index, lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=10, character=7),
        ))
        assert def_idev is not None
        assert def_idev.uri == main_uri

        # 2. Type Definition -> returns I_Device.TcIO
        type_idev = handle_type_definition(index, lsp.TypeDefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=10, character=7),
        ))
        assert type_idev is not None
        assert type_idev.uri == path_to_uri(itf_file)

        # 3. Implementation (Ctrl+F12) -> returns FB_DeviceImpl.TcPOU implementation body!
        impl_idev = handle_implementation(index, lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=10, character=7),
        ))
        assert impl_idev is not None
        assert (impl_idev.uri if isinstance(impl_idev, lsp.Location) else impl_idev[0].uri) == path_to_uri(fb_file)

        # C. Function Call: 'F_Compute' on line 20 (0-based line 19, col 12)
        # 1. Definition -> returns F_Compute.TcPOU declaration
        def_fn = handle_definition(index, lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=19, character=12),
        ))
        assert def_fn is not None
        assert def_fn.uri == path_to_uri(func_file)

        # 2. Implementation -> returns F_Compute.TcPOU ST implementation body
        impl_fn = handle_implementation(index, lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=19, character=12),
        ))
        assert impl_fn is not None
        assert (impl_fn.uri if isinstance(impl_fn, lsp.Location) else impl_fn[0].uri) == path_to_uri(func_file)

        # D. GVL Access: 'GVL_App.nGlobalCount' on line 21 (0-based line 20, col 18)
        # 1. Definition -> returns variable line in GVL_App.TcGVL
        def_gvl_v = handle_definition(index, lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=20, character=18),
        ))
        assert def_gvl_v is not None
        assert def_gvl_v.uri == path_to_uri(gvl_file)

        # E. Action Call: 'A_Reset' on line 18 (0-based line 17, col 8)
        # 1. Definition -> returns Action in FB_DeviceImpl.TcPOU
        def_act = handle_definition(index, lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=17, character=8),
        ))
        assert def_act is not None
        assert def_act.uri == path_to_uri(fb_file)

        # 2. Implementation -> returns Action implementation body in FB_DeviceImpl.TcPOU
        impl_act = handle_implementation(index, lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=main_uri),
            position=lsp.Position(line=17, character=8),
        ))
        assert impl_act is not None
        assert (impl_act.uri if isinstance(impl_act, lsp.Location) else impl_act[0].uri) == path_to_uri(fb_file)

    def test_hover_and_definition_for_unknown_external_libraries_vs_solution_libraries(self, tmp_path):
        """Verify behavior for unknown external compiled libraries (not in InfoSys) vs custom user libraries in solution."""
        from twincat_core.semantic.diagnostics import run_semantic_analysis

        # 1. Custom library POU in a sibling library folder (part of workspace/solution)
        lib_dir = tmp_path / "MyCustomLib"
        lib_dir.mkdir(parents=True)
        custom_fb_file = lib_dir / "FB_CustomSensorDriver.TcPOU"
        custom_fb_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_CustomSensorDriver" Id="{AAAAAAAA-1111-2222-3333-444444444444}">
    <Declaration><![CDATA[// Custom in-house sensor driver
FUNCTION_BLOCK FB_CustomSensorDriver
VAR_INPUT
    bEnable : BOOL; // Enable acquisition
END_VAR
VAR_OUTPUT
    fSample_V : LREAL; // Measured voltage
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[fSample_V := 3.3;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        # 2. App POU using both:
        #    - A custom in-house FB from solution (FB_CustomSensorDriver)
        #    - An unknown 3rd party compiled library FB not in solution and not in InfoSys (FB_UnknownThirdParty)
        app_file = tmp_path / "MAIN_App.TcPOU"
        app_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="MAIN_App" Id="{BBBBBBBB-1111-2222-3333-444444444444}">
    <Declaration><![CDATA[PROGRAM MAIN_App
VAR
    fbDriver : FB_CustomSensorDriver;
    fbUnknown : FB_UnknownThirdParty;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[fbDriver.bEnable := TRUE;
]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(custom_fb_file)
        index.update_file(app_file)

        app_uri = path_to_uri(app_file)

        # --- A. Custom User Library FB (indexed in workspace) ---
        # 1. Hover on 'fbDriver' variable -> shows type with public signature
        h_drv_var = handle_hover(index, lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=app_uri),
            position=lsp.Position(line=5, character=8),
        ))
        assert h_drv_var is not None
        assert "fbDriver : FB_CustomSensorDriver" in h_drv_var.contents.value
        assert "FUNCTION_BLOCK FB_CustomSensorDriver" in h_drv_var.contents.value
        assert "bEnable" in h_drv_var.contents.value and "fSample_V" in h_drv_var.contents.value

        # 2. Go to Definition on 'FB_CustomSensorDriver' type name -> navigates to FB_CustomSensorDriver.TcPOU!
        def_drv_type = handle_definition(index, lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=app_uri),
            position=lsp.Position(line=5, character=20),
        ))
        assert def_drv_type is not None
        assert def_drv_type.uri == path_to_uri(custom_fb_file)

        # 3. Go to Implementation on 'fbDriver' -> navigates to ST implementation of FB_CustomSensorDriver.TcPOU!
        impl_drv_var = handle_implementation(index, lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=app_uri),
            position=lsp.Position(line=5, character=8),
        ))
        assert impl_drv_var is not None
        assert (impl_drv_var.uri if isinstance(impl_drv_var, lsp.Location) else impl_drv_var[0].uri) == path_to_uri(custom_fb_file)

        # --- B. Unknown Third-Party Library FB (not in workspace, not in InfoSys) ---
        # 1. Hover on 'fbUnknown' variable -> shows clean variable info
        h_unk_var = handle_hover(index, lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=app_uri),
            position=lsp.Position(line=6, character=8),
        ))
        assert h_unk_var is not None
        assert "(VARIABLE) fbUnknown : FB_UnknownThirdParty" in h_unk_var.contents.value

        # 2. Hover on 'FB_UnknownThirdParty' type -> returns None (no metadata available)
        h_unk_type = handle_hover(index, lsp.HoverParams(
            text_document=lsp.TextDocumentIdentifier(uri=app_uri),
            position=lsp.Position(line=6, character=20),
        ))
        assert h_unk_type is None

        # 3. Go to Definition on 'FB_UnknownThirdParty' type -> returns None (no source on disk)
        def_unk_type = handle_definition(index, lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=app_uri),
            position=lsp.Position(line=6, character=20),
        ))
        assert def_unk_type is None

        # 4. Go to Implementation on 'fbUnknown' variable -> returns None (no source on disk)
        impl_unk_var = handle_implementation(index, lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=app_uri),
            position=lsp.Position(line=6, character=8),
        ))
        assert impl_unk_var is None

        # 5. Semantic diagnostics correctly reports TC-SEM-001 (Unknown type) for FB_UnknownThirdParty
        diags = run_semantic_analysis(index, app_file)
        assert len(diags) == 1
        assert diags[0].code == "TC-SEM-001"
        assert "Unknown type 'FB_UnknownThirdParty'" in diags[0].message


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

    def test_exact_line_numbers_for_definitions_implementations_and_diagnostics(self, tmp_path):
        """Comprehensive verification that all line and column numbers in XML files match exactly for GoToDef, GoToImpl, and Diagnostics."""
        from twincat_core.syntax.span import offset_to_line_col, line_col_to_offset

        # 1. Test offset <-> line/col bidirectional roundtrips for CRLF and LF
        crlf_sample = "<?xml version=\"1.0\"?>\r\n<TcPlcObject>\r\n  <POU>\r\n    <Declaration><![CDATA[VAR\r\n  a : INT;\r\nEND_VAR]]></Declaration>\r\n"
        for offset in range(len(crlf_sample)):
            l, c = offset_to_line_col(crlf_sample, offset)
            re_off = line_col_to_offset(crlf_sample, l, c)
            assert re_off == offset, f"CRLF mismatch at offset {offset}: ({l}, {c}) -> {re_off}"

        lf_sample = "<?xml version=\"1.0\"?>\n<TcPlcObject>\n  <POU>\n    <Declaration><![CDATA[VAR\n  a : INT;\nEND_VAR]]></Declaration>\n"
        for offset in range(len(lf_sample)):
            l, c = offset_to_line_col(lf_sample, offset)
            re_off = line_col_to_offset(lf_sample, l, c)
            assert re_off == offset, f"LF mismatch at offset {offset}: ({l}, {c}) -> {re_off}"

        # 2. Test Multi-element POU file with Method, Property, Action and verify exact XML line locations
        pou_file = tmp_path / "FB_LineTest.TcPOU"
        pou_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_LineTest" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_LineTest
VAR
    nMainCounter : INT;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[nMainCounter := nMainCounter + 1;
A_Step();]]></ST>
    </Implementation>
    <Method Name="M_DoWork" Id="{11111111-1111-1111-1111-111111111111}">
      <Declaration><![CDATA[METHOD M_DoWork : BOOL
VAR_INPUT
    bExecute : BOOL;
END_VAR]]></Declaration>
      <Implementation>
        <ST><![CDATA[M_DoWork := bExecute;]]></ST>
      </Implementation>
    </Method>
    <Property Name="P_Status" Id="{22222222-2222-2222-2222-222222222222}">
      <Declaration><![CDATA[PROPERTY P_Status : INT]]></Declaration>
      <Get Name="Get" Id="{33333333-3333-3333-3333-333333333333}">
        <Declaration><![CDATA[VAR
END_VAR]]></Declaration>
        <Implementation>
          <ST><![CDATA[P_Status := nMainCounter;]]></ST>
        </Implementation>
      </Get>
    </Property>
    <Action Name="A_Step" Id="{44444444-4444-4444-4444-444444444444}">
      <Implementation>
        <ST><![CDATA[nMainCounter := 0;]]></ST>
      </Implementation>
    </Action>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        index = WorkspaceIndex()
        index.update_file(pou_file)
        uri = path_to_uri(pou_file)

        # Go to Definition for nMainCounter on line 6 (0-based line 5, col 6)
        def_var = handle_definition(index, lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=5, character=6),
        ))
        assert def_var is not None
        assert def_var.range.start.line == 5  # Line 6 in XML

        # Go to Type Definition for nMainCounter (resolves to INT)
        type_def_var = handle_type_definition(index, lsp.TypeDefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=5, character=6),
        ))
        assert type_def_var is not None

        # Go to Definition for Method M_DoWork on line 13 (0-based line 12, col 36)
        def_m = handle_definition(index, lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=12, character=36),
        ))
        assert def_m is not None
        assert def_m.range.start.line == 12  # Line 13 in XML

        # Go to Definition for Property P_Status on line 22 (0-based line 21, col 38)
        def_p = handle_definition(index, lsp.DefinitionParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=21, character=38),
        ))
        assert def_p is not None
        assert def_p.range.start.line == 21  # Line 22 in XML

        # Go to Implementation for Method M_DoWork (navigates to ST CDATA on line 18 / 0-based line 17)
        impl_m = handle_implementation(index, lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=12, character=36),
        ))
        assert impl_m is not None
        assert impl_m.range.start.line == 17  # Line 18 in XML

        # Go to Implementation for Action A_Step (navigates to ST CDATA on line 33 / 0-based line 32)
        impl_a = handle_implementation(index, lsp.ImplementationParams(
            text_document=lsp.TextDocumentIdentifier(uri=uri),
            position=lsp.Position(line=9, character=2),
        ))
        assert impl_a is not None
        assert impl_a.range.start.line == 32  # Line 33 in XML

        # 3. Test Diagnostic Line Numbers in XML for both Declaration and Implementation errors
        diag_file = tmp_path / "FB_DiagLineTest.TcPOU"
        diag_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_DiagLineTest" Id="{99999999-9999-9999-9999-999999999999}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_DiagLineTest
VAR
    arrInvalid : ARRAY[10..2] OF INT;
    bFlag      : BOOL;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[bFlag := 12345;
undeclaredVar := TRUE;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        index.update_file(diag_file)
        diags = get_diagnostics_for_file(index, diag_file)

        # We expect:
        # 1. TC-DECL-007 (Array bound error) on line 6 (0-based line 5)
        # 2. TC-SEM-006 (Type mismatch: cannot convert INT to BOOL) on line 10 (0-based line 9)
        # 3. TC-SEM-008 (Undeclared identifier) on line 11 (0-based line 10)
        assert len(diags) >= 3
        codes = {d.code: d for d in diags}

        assert "TC-DECL-007" in codes
        assert codes["TC-DECL-007"].range.start.line == 5  # Line 6 in XML

        assert "TC-SEM-006" in codes
        assert codes["TC-SEM-006"].range.start.line == 9  # Line 10 in XML

        assert "TC-SEM-008" in codes
        assert codes["TC-SEM-008"].range.start.line == 10  # Line 11 in XML





