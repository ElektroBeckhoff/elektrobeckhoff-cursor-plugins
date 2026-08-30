"""Comprehensive regression tests for ALL formatting scenarios.

Tests scenarios that caused bugs during development to prevent regressions.
Each test is a specific real-world pattern from the Tc3_EB_BA library.
"""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest
from formatter.config import load_config
from formatter.st_formatter import format_st_code
from formatter.st_alignment import align_declarations, align_assignments, align_fb_call_params
from formatter.st_line_wrapper import wrap_long_lines
from formatter.file_processor import _format_st_pipeline, process_file, check_syntax_integrity
from formatter.xml_validator import validate_twincat_xml
from formatter.xml_writer import serialize_twincat_xml
from formatter.xml_formatter import format_xml_structure, parse_twincat_xml, restore_cdata


CONFIG = load_config()


# ===========================================================================
# 1. Multi-line declarations (MUST NOT add semicolons)
# ===========================================================================

class TestMultilineDeclarations:
    """Lines ending with :=, (, [ must NOT get ; appended."""

    def test_multiline_array_init(self):
        lines = [
            "VAR CONSTANT",
            "    arrValues : ARRAY[1..3] OF INT := [1,",
            "                                       2,",
            "                                       3];",
            "    nCount   : INT := 5;",
            "END_VAR",
        ]
        result = align_declarations(lines)
        # First declaration line must NOT get ; (it continues on next lines)
        assert result[1].strip().endswith("[1,"), f"Got: {result[1]}"
        # The complete single-line declaration should have ;
        assert result[4].strip().endswith(";")

    def test_multiline_struct_init(self):
        lines = [
            "VAR",
            "    stVersion : ST_LibVersion := (",
            "        iMajor := 1,",
            "        iMinor := 0,",
            "        iBuild := 0);",
            "END_VAR",
        ]
        result = align_declarations(lines)
        # Must not add ; after (
        assert result[1].strip().endswith(":= ("), f"Got: {result[1]}"

    def test_multiline_assignment_continuation(self):
        lines = [
            "VAR",
            "    arrFacade : ARRAY[1..4] OF ST_Facade :=",
            "        [(fBright := 10.0), (fBright := 20.0)];",
            "    bEnable  : BOOL;",
            "END_VAR",
        ]
        result = align_declarations(lines)
        # Line ending with := (no value) must NOT get ;
        assert result[1].strip().endswith(":="), f"Got: {result[1]}"

    def test_multiline_enum_array(self):
        lines = [
            "VAR CONSTANT",
            "    _arrMask : ARRAY[1..3] OF E_Group := [E_Group.A,",
            "                                          E_Group.B,",
            "                                          E_Group.C];",
            "END_VAR",
        ]
        result = align_declarations(lines)
        assert "[E_Group.A," in result[1]
        assert ";" not in result[1] or result[1].count(";") == 0


# ===========================================================================
# 2. Block comment protection
# ===========================================================================

class TestBlockCommentProtection:
    """Content inside (* ... *) must NEVER be modified."""

    def test_multiline_comment_not_aligned(self):
        lines = [
            "VAR",
            "    (* Column description:",
            "       Spalte 1 = Zaehler: Ist in Szene,",
            "       Spalte 2 = Wert: Soll-Wert *)",
            "    nColumn : INT;",
            "    sValue  : STRING;",
            "END_VAR",
        ]
        result = align_declarations(lines)
        # Comment lines must be unchanged
        assert result[1] == "    (* Column description:"
        assert "Spalte 1 = Zaehler: Ist in Szene," in result[2]
        assert result[3] == "       Spalte 2 = Wert: Soll-Wert *)"

    def test_block_comment_in_assignments_not_touched(self):
        lines = [
            "    (* State machine:",
            "       Step 0 = Init,",
            "       Step 1 := Active (not valid ST, but in comment) *)",
            "    x := 1;",
            "    y := 2;",
        ]
        result = align_assignments(lines)
        # Comment lines preserved exactly
        assert result[0] == "    (* State machine:"
        assert ":= Active" in result[2]
        # Real assignments aligned
        x_pos = result[3].find(":=")
        y_pos = result[4].find(":=")
        assert x_pos == y_pos

    def test_keywords_in_comments_not_uppercased(self):
        code = "(* if you need to check then do this *)\nIF x THEN\nEND_IF"
        result = format_st_code(code, uppercase_keywords=True)
        assert "(* if you need to check then do this *)" in result
        assert "IF x THEN" in result

    def test_single_line_comment_preserved(self):
        code = "// This is a type comment for the enum\nIF x THEN\nEND_IF"
        result = format_st_code(code, uppercase_keywords=True)
        assert "// This is a type comment for the enum" in result


# ===========================================================================
# 3. Pragma handling
# ===========================================================================

class TestPragmaHandling:
    """Pragmas must be handled correctly in alignment."""

    def test_pragma_breaks_alignment_group(self):
        lines = [
            "VAR",
            "    x : INT;",
            "    {attribute 'hide'}",
            "    longName : BOOL;",
            "    y        : REAL;",
            "END_VAR",
        ]
        result = align_declarations(lines)
        # Pragma line preserved
        assert "{attribute" in result[2]

    def test_inline_pragma_with_declaration(self):
        lines = [
            "VAR",
            "    {attribute 'hide'} _sPath : STRING;",
            "    {attribute 'hide'} _bInit : BOOL;",
            "END_VAR",
        ]
        result = align_declarations(lines)
        # Both should have pragmas preserved and colons aligned
        assert "{attribute 'hide'}" in result[1]
        assert "{attribute 'hide'}" in result[2]


# ===========================================================================
# 4. ENUM indentation
# ===========================================================================

class TestEnumIndentation:
    """Enum members must be indented correctly."""

    def test_inline_enum_type(self):
        code = "TYPE E_Mode :\n(\n    Idle := 0,\n    Active := 1,\n    Error := 2\n);\nEND_TYPE"
        result = format_st_code(code, reindent=True)
        lines = result.split("\n")
        assert lines[0] == "TYPE E_Mode :"
        # Members should be indented
        assert "Idle" in result
        assert "Active" in result

    def test_qualified_enum(self):
        code = "{attribute 'qualified_only'}\n{attribute 'strict'}\nTYPE E_Test : (\n    Val1 := 0,\n    Val2 := 1\n);\nEND_TYPE"
        result = format_st_code(code, reindent=True)
        assert "Val1" in result
        assert "Val2" in result


# ===========================================================================
# 5. XML namespace preservation
# ===========================================================================

class TestXmlNamespace:
    """xml:space and other namespaced attributes must serialize correctly."""

    def test_xml_space_preserve(self):
        xml = '''<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1" ProductVersion="3.1">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test
END_VAR]]></Declaration>
    <Implementation>
      <NWL>
        <XmlArchive>
          <Data>
            <o xml:space="preserve" t="NWLImplementationObject">
              <v n="Test">val</v>
            </o>
          </Data>
        </XmlArchive>
      </NWL>
    </Implementation>
  </POU>
</TcPlcObject>'''
        result, cmap = format_xml_structure(xml)
        restored = restore_cdata(result, cmap)
        assert 'xml:space="preserve"' in restored
        assert "{http://www.w3.org/XML/1998/namespace}" not in restored


# ===========================================================================
# 6. Syntax integrity check
# ===========================================================================

class TestSyntaxIntegrityCheck:
    """check_syntax_integrity must detect added/removed tokens."""

    def test_no_change_passes(self):
        text = '<root><![CDATA[x := 1;\ny := 2;]]></root>'
        errors = check_syntax_integrity(text, text)
        assert errors == []

    def test_added_semicolon_detected(self):
        orig = '<root><![CDATA[x := 1\ny := 2]]></root>'
        modified = '<root><![CDATA[x := 1;\ny := 2;]]></root>'
        errors = check_syntax_integrity(orig, modified)
        assert len(errors) > 0
        assert any("semicolons" in e for e in errors)

    def test_removed_identifier_detected(self):
        orig = '<root><![CDATA[longVarName := 1;]]></root>'
        modified = '<root><![CDATA[x := 1;]]></root>'
        errors = check_syntax_integrity(orig, modified)
        assert len(errors) > 0

    def test_whitespace_only_passes(self):
        orig = '<root><![CDATA[x:=1; y:=2;]]></root>'
        modified = '<root><![CDATA[x := 1;  y := 2;]]></root>'
        errors = check_syntax_integrity(orig, modified)
        assert errors == []


# ===========================================================================
# 7. Line ending detection and preservation
# ===========================================================================

class TestLineEndingPreservation:
    """Formatter must detect and preserve original line endings."""

    def test_crlf_preserved(self, tmp_path):
        content = '<?xml version="1.0" encoding="utf-8"?>\r\n<TcPlcObject Version="1.1" ProductVersion="3.1">\r\n  <DUT Name="ST_Test" Id="{12345678-1234-1234-1234-123456789012}">\r\n    <Declaration><![CDATA[TYPE ST_Test :\r\nSTRUCT\r\n    x : INT;\r\nEND_STRUCT\r\nEND_TYPE]]></Declaration>\r\n  </DUT>\r\n</TcPlcObject>\r\n'
        filepath = tmp_path / "test.TcDUT"
        filepath.write_bytes(content.encode("utf-8"))

        result = process_file(str(filepath), CONFIG, dry_run=False, sort_xml=False)
        result_bytes = filepath.read_bytes()
        assert b"\r\n" in result_bytes
        assert b"\n" in result_bytes
        # No bare \n (every \n should be preceded by \r)
        text = result_bytes.decode("utf-8")
        for i, ch in enumerate(text):
            if ch == "\n" and i > 0 and text[i-1] != "\r":
                pytest.fail(f"Found bare \\n at pos {i}")

    def test_lf_preserved(self, tmp_path):
        content = '<?xml version="1.0" encoding="utf-8"?>\n<TcPlcObject Version="1.1" ProductVersion="3.1">\n  <DUT Name="ST_Test" Id="{12345678-1234-1234-1234-123456789012}">\n    <Declaration><![CDATA[TYPE ST_Test :\nSTRUCT\n    x : INT;\nEND_STRUCT\nEND_TYPE]]></Declaration>\n  </DUT>\n</TcPlcObject>\n'
        filepath = tmp_path / "test.TcDUT"
        filepath.write_bytes(content.encode("utf-8"))

        result = process_file(str(filepath), CONFIG, dry_run=False, sort_xml=False)
        result_bytes = filepath.read_bytes()
        assert b"\r\n" not in result_bytes


# ===========================================================================
# 8. Validator: name_match with comments
# ===========================================================================

class TestValidatorNameMatchComments:
    """Validator must NOT match keywords inside comments."""

    def test_keyword_in_comment_not_matched(self):
        xml = '''<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1" ProductVersion="3.1">
  <DUT Name="E_Test" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[(* This type derived from base *)
TYPE E_Test : (
    Val1 := 0
);
END_TYPE]]></Declaration>
  </DUT>
</TcPlcObject>'''
        issues = validate_twincat_xml(xml, "test.TcDUT")
        name_issues = [i for i in issues if i.rule == "name_match"]
        assert len(name_issues) == 0, f"False positive: {name_issues}"

    def test_interface_keyword_in_comment(self):
        xml = '''<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1" ProductVersion="3.1">
  <Itf Name="I_Test" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[(* Interface for device control *)
INTERFACE I_Test]]></Declaration>
  </Itf>
</TcPlcObject>'''
        issues = validate_twincat_xml(xml, "test.TcIO")
        name_issues = [i for i in issues if i.rule == "name_match"]
        assert len(name_issues) == 0

    def test_method_keyword_in_comment(self):
        xml = '''<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1" ProductVersion="3.1">
  <POU Name="FB_Test" Id="{12345678-1234-1234-1234-123456789012}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
    <Method Name="DoWork" Id="{22345678-1234-1234-1234-123456789012}">
      <Declaration><![CDATA[(* Method to handle processing *)
METHOD DoWork]]></Declaration>
      <Implementation><ST><![CDATA[]]></ST></Implementation>
    </Method>
  </POU>
</TcPlcObject>'''
        issues = validate_twincat_xml(xml, "test.TcPOU")
        name_issues = [i for i in issues if i.rule == "name_match"]
        assert len(name_issues) == 0


# ===========================================================================
# 9. Assignment alignment: := inside FB calls excluded
# ===========================================================================

class TestAssignmentInsideParens:
    """assign_assignments must NOT align := inside function calls."""

    def test_fb_call_not_aligned_as_assignment(self):
        lines = [
            "    fbTimer(IN := TRUE);",
            "    fbTon(IN := bStart, PT := T#5S);",
            "    _bBusy := FALSE;",
            "    _bDone := TRUE;",
        ]
        result = align_assignments(lines)
        # FB calls should be unchanged
        assert "fbTimer(IN := TRUE);" in result[0]
        assert "fbTon(IN := bStart, PT := T#5S);" in result[1]
        # Real assignments aligned
        busy_pos = result[2].find(":=")
        done_pos = result[3].find(":=")
        assert busy_pos == done_pos

    def test_nested_parens_not_treated_as_assignment(self):
        lines = [
            "    Func(param1 := Nested(x := 1));",
            "    _result := 5;",
        ]
        result = align_assignments(lines)
        # Func line should be unchanged (has := inside parens)
        assert result[0].strip() == "Func(param1 := Nested(x := 1));"


# ===========================================================================
# 10. Full pipeline: already formatted files unchanged
# ===========================================================================

class TestAlreadyFormattedUnchanged:
    """Already correctly formatted code must not be changed."""

    def test_aligned_declarations_stable(self):
        code = (
            "VAR\n"
            "    bEnable  : BOOL;\n"
            "    nCounter : INT;\n"
            "    fValue   : REAL;\n"
            "END_VAR\n"
        )
        result = _format_st_pipeline(code, CONFIG)
        assert result == code

    def test_aligned_fb_call_joined_when_short(self):
        code = (
            "fbInflux(\n"
            "        pValue   := ADR(fTemp),\n"
            "        nSize    := SIZEOF(fTemp),\n"
            "        ePlcType := E_Type.eReal);\n"
        )
        expected = "fbInflux(pValue := ADR(fTemp), nSize := SIZEOF(fTemp), ePlcType := E_Type.eReal);\n"
        result = _format_st_pipeline(code, CONFIG)
        assert result == expected

    def test_mixed_declarations_and_blanks_stable(self):
        code = (
            "VAR\n"
            "    bEnable : BOOL;\n"
            "\n"
            "    (* Internal state *)\n"
            "    _nStep : INT;\n"
            "    _bDone : BOOL;\n"
            "END_VAR\n"
        )
        result = _format_st_pipeline(code, CONFIG)
        assert result == code


# ===========================================================================
# 11. Edge cases
# ===========================================================================

class TestEdgeCases:
    """Edge cases that could crash or produce wrong output."""

    def test_empty_cdata(self, tmp_path):
        content = '<?xml version="1.0" encoding="utf-8"?>\n<TcPlcObject Version="1.1" ProductVersion="3.1">\n  <POU Name="FB_Empty" Id="{12345678-1234-1234-1234-123456789012}">\n    <Declaration><![CDATA[FUNCTION_BLOCK FB_Empty\nEND_VAR]]></Declaration>\n    <Implementation><ST><![CDATA[]]></ST></Implementation>\n  </POU>\n</TcPlcObject>\n'
        filepath = tmp_path / "FB_Empty.TcPOU"
        filepath.write_text(content, encoding="utf-8")
        result = process_file(str(filepath), CONFIG, dry_run=True)
        assert result.success

    def test_only_comments_in_implementation(self):
        code = "(* This is a placeholder *)\n(* Nothing to do here *)\n"
        result = _format_st_pipeline(code, CONFIG)
        assert "(* This is a placeholder *)" in result
        assert "(* Nothing to do here *)" in result

    def test_very_long_declaration(self):
        code = (
            "VAR\n"
            "    arrData : ARRAY[1..GVL.cnMax] OF ST_VeryLongTypeName_WithExtraInfo;\n"
            "    x       : INT;\n"
            "END_VAR\n"
        )
        result = _format_st_pipeline(code, CONFIG)
        assert "arrData" in result
        assert "ST_VeryLongTypeName_WithExtraInfo" in result

    def test_declaration_with_at_percent(self):
        """AT %Q* declarations align name/AT/address columns and do not crash."""
        lines = [
            "VAR",
            "    bOutput AT %Q* : BOOL;",
            "    nValue         : INT;",
            "END_VAR",
        ]
        result = align_declarations(lines, align_address_assignments=True)
        assert "AT %Q*" in result[1]
        colon_positions = [line.index(" : ") for line in result[1:-1]]
        assert len(set(colon_positions)) == 1

    def test_string_with_special_chars(self):
        code = "sMsg := 'Value: := 5; (* not a comment *)';\n"
        result = format_st_code(code, uppercase_keywords=True)
        # String content must be preserved exactly
        assert "'Value: := 5; (* not a comment *)'" in result

    def test_hex_literal(self):
        code = "nMask := 16#FF00;\n"
        result = format_st_code(code, uppercase_keywords=True)
        assert "16#FF00" in result

    def test_pragmas_not_uppercased(self):
        code = "{attribute 'qualified_only'}\nTYPE E_Test : (Val := 0);\nEND_TYPE"
        result = format_st_code(code, uppercase_keywords=True)
        assert "{attribute 'qualified_only'}" in result
        assert "TYPE" in result


class TestGoldenParityFixes:
    """Regression tests for golden-corpus parity fixes (684/692 gate)."""

    def test_fb_init_in_declaration_type_not_split(self):
        """FB constructor params inside VAR type must stay intact (_parse_decl)."""
        from formatter.st_alignment import _parse_decl

        line = (
            "    _fbLightProxy : FB_EB_BA_LightControlProxy("
            "ipParent := 0, fbLightControl := 0, fbLightDaylightAutomatic := 0);"
        )
        parsed = _parse_decl(line)
        assert parsed is not None
        name, type_part, init_part, _, _ = parsed
        assert name == "_fbLightProxy"
        assert init_part == ""
        assert "ipParent := 0" in type_part

    def test_fb_param_bool_chain_indent_preserved(self):
        """Bool-chain continuations in FB params keep operand-column indent."""
        from formatter.file_processor import _normalize_call_param_indent

        lines = [
            "_fbTon(",
            "        IN := (_eMode = E_Test.Neutral) AND",
            "              ((stConfig.eMode = E_Test.Cooling) OR (stConfig.eMode = E_Test.Auto)) AND",
            "              (_fTemp > stConfig.fSetpoint),",
            "        PT := tDelay);",
        ]
        out = _normalize_call_param_indent(lines, call_indent=8)
        assert out[2].startswith("              ((")

    def test_line_comment_error_not_treated_as_or_continuation(self):
        """``// error`` must not match bool-op suffix ``OR`` in join pass 1.5."""
        from formatter.config import load_config
        from formatter.file_processor import _format_st_pipeline

        code = (
            "CASE _nState OF\n"
            "    1:\n"
            "        IF NOT _fb.bBusy THEN\n"
            "            IF NOT _fb.bError THEN\n"
            "                _nState := 2;\n"
            "            ELSE\n"
            "                nErrorId := _fb.nErrId; // error\n"
            "                bError   := TRUE;\n"
            "                _nState  := 3;\n"
            "            END_IF\n"
            "        END_IF\n"
            "ELSE\n"
            "    _nState := 0;\n"
            "END_CASE\n"
        )
        result = _format_st_pipeline(code, load_config()).split("\n")
        assert any(l.strip() == "bError   := TRUE;" for l in result)
        assert not any("// error bError" in l for l in result)
