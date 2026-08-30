"""Comprehensive edge-case tests for all TwinCAT3 ST syntax elements.

Verifies the formatter handles every possible ST construct without corruption.
Each test checks that:
1. Formatting does not alter semantic content (keywords/identifiers/operators preserved)
2. The formatter handles the construct without crashing
3. Idempotency: formatting twice yields same result

Covers:
- All control flow: IF/CASE/FOR/WHILE/REPEAT/EXIT/RETURN/CONTINUE
- All VAR block types and modifiers
- OOP: EXTENDS, IMPLEMENTS, ABSTRACT, FINAL, OVERRIDE, THIS, SUPER
- Pointers/References: POINTER TO, REFERENCE TO, ^, ADR, REF, __NEW, __DELETE
- Complex types: multi-dim arrays, UNION, STRUCT variants
- Operators: AND_THEN, OR_ELSE, MOD, XOR, arithmetic, comparison
- Literals: hex, binary, octal, time, date, strings with escapes
- Direct addresses: AT %I*, AT %Q*, AT %M*
- Pragmas: {attribute}, {region}/{endregion}, conditional
- Special: empty statements, chained calls, property Get/Set
"""
import pytest

from formatter.st_formatter import format_st_code, split_disable_regions
from formatter.file_processor import _format_st_pipeline, _format_st_segment
from formatter.config import FormatterConfig


@pytest.fixture
def config():
    return FormatterConfig()


def _assert_idempotent(source: str, config: FormatterConfig):
    """Helper: format twice, assert stable output."""
    r1 = _format_st_pipeline(source, config)
    r2 = _format_st_pipeline(r1, config)
    assert r1 == r2, f"Not idempotent!\nFirst:\n{r1}\nSecond:\n{r2}"
    return r1


def _assert_preserves_tokens(source: str, config: FormatterConfig, tokens: list[str]):
    """Helper: ensure specific tokens appear in result."""
    result = _format_st_pipeline(source, config)
    for tok in tokens:
        assert tok in result, f"Token '{tok}' missing from result:\n{result}"
    return result


# ---------------------------------------------------------------------------
# Control Flow
# ---------------------------------------------------------------------------


class TestControlFlow:

    def test_if_elsif_else(self, config):
        code = (
            "if x = 1 then\n"
            "    y := 1;\n"
            "elsif x = 2 then\n"
            "    y := 2;\n"
            "else\n"
            "    y := 3;\n"
            "end_if;"
        )
        result = _assert_idempotent(code, config)
        assert "IF" in result
        assert "ELSIF" in result
        assert "ELSE" in result
        assert "END_IF" in result

    def test_case_with_multiple_labels(self, config):
        code = (
            "case nState of\n"
            "0:\n"
            "    x := 1;\n"
            "1, 2, 3:\n"
            "    x := 2;\n"
            "else\n"
            "    x := 99;\n"
            "end_case;"
        )
        result = _assert_idempotent(code, config)
        assert "CASE" in result
        assert "END_CASE" in result

    def test_for_loop_with_by(self, config):
        code = "for i := 0 to 10 by 2 do\n    arr[i] := 0;\nend_for;"
        result = _assert_idempotent(code, config)
        assert "FOR" in result
        assert "TO" in result
        assert "BY" in result
        assert "DO" in result
        assert "END_FOR" in result

    def test_while_loop(self, config):
        code = "while bRunning do\n    nCount := nCount + 1;\nend_while;"
        result = _assert_idempotent(code, config)
        assert "WHILE" in result
        assert "END_WHILE" in result

    def test_repeat_until(self, config):
        code = "repeat\n    nCount := nCount + 1;\nuntil nCount >= 10\nend_repeat;"
        result = _assert_idempotent(code, config)
        assert "REPEAT" in result
        assert "UNTIL" in result
        assert "END_REPEAT" in result

    def test_exit_return_continue(self, config):
        code = (
            "for i := 0 to 10 do\n"
            "    if i = 5 then\n"
            "        continue;\n"
            "    end_if;\n"
            "    if i = 8 then\n"
            "        exit;\n"
            "    end_if;\n"
            "end_for;\n"
            "return;"
        )
        result = _assert_idempotent(code, config)
        assert "CONTINUE" in result
        assert "EXIT" in result
        assert "RETURN" in result


# ---------------------------------------------------------------------------
# VAR Blocks and Modifiers
# ---------------------------------------------------------------------------


class TestVarBlocks:

    def test_all_var_block_types(self, config):
        code = (
            "VAR\n    x : INT;\nEND_VAR\n"
            "VAR_INPUT\n    bEnable : BOOL;\nEND_VAR\n"
            "VAR_OUTPUT\n    bDone : BOOL;\nEND_VAR\n"
            "VAR_IN_OUT\n    refData : REFERENCE TO INT;\nEND_VAR\n"
            "VAR_TEMP\n    nTemp : INT;\nEND_VAR\n"
            "VAR_STAT\n    nCallCount : UDINT;\nEND_VAR\n"
            "VAR_INST\n    fbTimer : TON;\nEND_VAR"
        )
        result = _assert_idempotent(code, config)
        for kw in ["VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_TEMP",
                   "VAR_STAT", "VAR_INST", "END_VAR"]:
            assert kw in result

    def test_var_constant(self, config):
        code = "VAR CONSTANT\n    cMaxRetries : UINT := 5;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "CONSTANT" in result

    def test_var_persistent(self, config):
        code = "VAR PERSISTENT\n    nRunHours : UDINT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "PERSISTENT" in result

    def test_var_retain(self, config):
        code = "VAR RETAIN\n    stLastState : ST_State;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "RETAIN" in result

    def test_var_persistent_retain(self, config):
        code = "VAR PERSISTENT RETAIN\n    nBootCount : UDINT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "PERSISTENT" in result
        assert "RETAIN" in result


# ---------------------------------------------------------------------------
# OOP
# ---------------------------------------------------------------------------


class TestOOP:

    def test_extends_implements(self, config):
        code = (
            "FUNCTION_BLOCK FB_Child EXTENDS FB_Base IMPLEMENTS I_MyInterface\n"
            "VAR\n    _x : INT;\nEND_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "EXTENDS" in result
        assert "IMPLEMENTS" in result

    def test_abstract_final(self, config):
        code = "FUNCTION_BLOCK ABSTRACT FB_AbstractBase\nVAR\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ABSTRACT" in result

    def test_override_method(self, config):
        code = "METHOD PUBLIC OVERRIDE M_DoWork\nVAR\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "OVERRIDE" in result
        assert "PUBLIC" in result

    def test_this_reference(self, config):
        code = "THIS^.M_Init();"
        result = _assert_idempotent(code, config)
        assert "THIS" in result

    def test_super_call(self, config):
        code = "SUPER^.M_Init();"
        result = _assert_idempotent(code, config)
        assert "SUPER" in result

    def test_access_specifiers(self, config):
        for spec in ["PRIVATE", "PROTECTED", "PUBLIC", "INTERNAL"]:
            code = f"METHOD {spec} M_Test\nVAR\nEND_VAR"
            result = _assert_idempotent(code, config)
            assert spec in result


# ---------------------------------------------------------------------------
# Pointer / Reference / Dynamic Memory
# ---------------------------------------------------------------------------


class TestPointerReference:

    def test_pointer_to_declaration(self, config):
        code = "VAR\n    pData : POINTER TO ST_Data;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "POINTER" in result

    def test_reference_to_declaration(self, config):
        code = "VAR_IN_OUT\n    refValue : REFERENCE TO REAL;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "REFERENCE" in result

    def test_pointer_dereference(self, config):
        code = "x := pData^.nValue;"
        result = _assert_idempotent(code, config)
        assert "^" in result

    def test_adr_operator(self, config):
        code = "pData := ADR(myStruct);"
        result = _assert_idempotent(code, config)
        assert "ADR" in result

    def test_ref_operator(self, config):
        code = "refX REF= myVar;"
        result = _assert_idempotent(code, config)
        assert "REF" in result

    def test_new_delete(self, config):
        code = (
            "pBuffer := __NEW(BYTE, 1024);\n"
            "IF pBuffer <> 0 THEN\n"
            "    __DELETE(pBuffer);\n"
            "END_IF;"
        )
        result = _assert_idempotent(code, config)
        assert "__NEW" in result
        assert "__DELETE" in result

    def test_isvalidref(self, config):
        code = "IF __ISVALIDREF(refValue) THEN\n    x := refValue;\nEND_IF;"
        result = _assert_idempotent(code, config)
        assert "__ISVALIDREF" in result

    def test_queryinterface(self, config):
        code = (
            "IF __QUERYINTERFACE(iBase, iDerived) THEN\n"
            "    iDerived.DoSomething();\n"
            "END_IF;"
        )
        result = _assert_idempotent(code, config)
        assert "__QUERYINTERFACE" in result


# ---------------------------------------------------------------------------
# Complex Types
# ---------------------------------------------------------------------------


class TestComplexTypes:

    def test_multidimensional_array(self, config):
        code = "VAR\n    arrMatrix : ARRAY[0..3, 0..3] OF REAL;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY" in result
        assert "0..3, 0..3" in result

    def test_array_of_array(self, config):
        code = "VAR\n    arrNested : ARRAY[0..9] OF ARRAY[0..4] OF INT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..9] OF ARRAY[0..4] OF INT" in result

    def test_union_declaration(self, config):
        code = (
            "TYPE U_Converter :\n"
            "UNION\n"
            "    nAsUdint : UDINT;\n"
            "    fAsReal  : REAL;\n"
            "    arrBytes : ARRAY[0..3] OF BYTE;\n"
            "END_UNION\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        assert "UNION" in result
        assert "END_UNION" in result

    def test_struct_persistent(self, config):
        code = (
            "TYPE ST_Persistent :\n"
            "STRUCT\n"
            "    nValue : INT;\n"
            "END_STRUCT\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        assert "STRUCT" in result
        assert "END_STRUCT" in result

    def test_string_with_size(self, config):
        code = "VAR\n    sName : STRING(255);\n    wsWide : WSTRING(100);\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "STRING(255)" in result
        assert "WSTRING(100)" in result


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


class TestOperators:

    def test_and_then_or_else(self, config):
        """Short-circuit operators (TwinCAT extension)."""
        code = (
            "IF pData <> 0 AND_THEN pData^.bValid THEN\n"
            "    x := 1;\n"
            "END_IF;\n"
            "IF bDefault OR_ELSE CheckCondition() THEN\n"
            "    y := 2;\n"
            "END_IF;"
        )
        result = _assert_idempotent(code, config)
        assert "AND_THEN" in result
        assert "OR_ELSE" in result

    def test_mod_xor(self, config):
        code = "x := nValue MOD 10;\ny := nA XOR nB;"
        result = _assert_idempotent(code, config)
        assert "MOD" in result
        assert "XOR" in result

    def test_output_assign(self, config):
        code = "fbTrigger(CLK := bInput, Q => bOutput);"
        result = _assert_idempotent(code, config)
        assert "=>" in result

    def test_sizeof(self, config):
        code = "nSize := SIZEOF(ST_MyStruct);"
        result = _assert_idempotent(code, config)
        assert "SIZEOF" in result


# ---------------------------------------------------------------------------
# Number Literals
# ---------------------------------------------------------------------------


class TestLiterals:

    def test_hex_literal(self, config):
        code = "nMask := 16#FF00_00FF;"
        result = _assert_idempotent(code, config)
        assert "16#FF00_00FF" in result

    def test_binary_literal(self, config):
        code = "nBits := 2#1010_0101;"
        result = _assert_idempotent(code, config)
        assert "2#1010_0101" in result

    def test_octal_literal(self, config):
        code = "nOctal := 8#377;"
        result = _assert_idempotent(code, config)
        assert "8#377" in result

    def test_time_literals(self, config):
        code = (
            "tDelay := T#5s;\n"
            "tLong := LTIME#1000ms;\n"
            "tComplex := T#1h2m3s4ms;"
        )
        result = _assert_idempotent(code, config)
        assert "T#5S" in result
        assert "LTIME#1000MS" in result
        assert "T#1H2M3S4MS" in result

    def test_date_time_literals(self, config):
        code = (
            "dToday := DATE#2024-01-15;\n"
            "todNow := TOD#14:30:00;\n"
            "dtFull := DT#2024-01-15-14:30:00;"
        )
        result = _assert_idempotent(code, config)
        assert "DATE#2024-01-15" in result
        assert "TOD#14:30:00" in result
        assert "DT#2024-01-15-14:30:00" in result

    def test_real_literal_with_exponent(self, config):
        code = "fValue := 1.23E-4;"
        result = _assert_idempotent(code, config)
        assert "1.23E-4" in result

    def test_string_with_escaped_quotes(self, config):
        code = "sMsg := 'It''s a test';"
        result = _assert_idempotent(code, config)
        assert "It''s a test" in result

    def test_wstring_literal(self, config):
        code = 'wsText := "Hello World";'
        result = _assert_idempotent(code, config)
        assert '"Hello World"' in result


# ---------------------------------------------------------------------------
# Direct Addresses (AT)
# ---------------------------------------------------------------------------


class TestDirectAddresses:

    def test_at_input(self, config):
        code = "VAR\n    bSensor AT %I* : BOOL;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "AT" in result
        assert "%I*" in result

    def test_at_output(self, config):
        code = "VAR\n    bActuator AT %Q* : BOOL;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "%Q*" in result

    def test_at_memory(self, config):
        code = "VAR\n    nCounter AT %M* : UDINT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "%M*" in result

    def test_at_specific_address(self, config):
        code = "VAR\n    bDigIn AT %IX0.0 : BOOL;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "%IX0.0" in result


# ---------------------------------------------------------------------------
# Pragmas
# ---------------------------------------------------------------------------


class TestPragmas:

    def test_attribute_pragma(self, config):
        code = "{attribute 'qualified_only'}\nVAR_GLOBAL\n    nGlobal : INT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "{attribute 'qualified_only'}" in result

    def test_region_pragma(self, config):
        code = (
            "{region 'Initialization'}\n"
            "x := 0;\n"
            "y := 0;\n"
            "{endregion}"
        )
        result = _assert_idempotent(code, config)
        assert "{region 'Initialization'}" in result
        assert "{endregion}" in result

    def test_conditional_pragma(self, config):
        code = (
            "{IF defined(SIMULATION)}\n"
            "bSimMode := TRUE;\n"
            "{ELSE}\n"
            "bSimMode := FALSE;\n"
            "{END_IF}"
        )
        result = _assert_idempotent(code, config)
        assert "{IF defined(SIMULATION)}" in result
        assert "{ELSE}" in result
        assert "{END_IF}" in result

    def test_warning_pragma(self, config):
        code = "{warning 'This is deprecated'}\nx := 0;"
        result = _assert_idempotent(code, config)
        assert "{warning 'This is deprecated'}" in result

    def test_attribute_hide(self, config):
        code = "VAR\n    {attribute 'hide'}\n    _nInternal : INT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "{attribute 'hide'}" in result

    def test_pack_mode_pragma(self, config):
        code = "{attribute 'pack_mode' := '1'}\nTYPE ST_Packed :\nSTRUCT\n    b : BYTE;\nEND_STRUCT\nEND_TYPE"
        result = _assert_idempotent(code, config)
        assert "{attribute 'pack_mode' := '1'}" in result


# ---------------------------------------------------------------------------
# Special Syntax Constructs
# ---------------------------------------------------------------------------


class TestSpecialSyntax:

    def test_empty_statement(self, config):
        """Standalone variable as statement (used for side-effects)."""
        code = "fbTimer;\nfbCounter;"
        result = _assert_idempotent(code, config)
        assert "fbTimer;" in result
        assert "fbCounter;" in result

    def test_chained_method_calls(self, config):
        code = "sResult := fbBuilder.AddHeader('X').AddBody(sPayload).Build();"
        result = _assert_idempotent(code, config)
        assert ".AddHeader(" in result
        assert ".AddBody(" in result
        assert ".Build()" in result

    def test_pointer_chain(self, config):
        code = "nVal := pOuter^.pInner^.nField;"
        result = _assert_idempotent(code, config)
        assert "pOuter^.pInner^.nField" in result

    def test_array_index_expression(self, config):
        code = "x := arrData[nIdx * 2 + 1];"
        result = _assert_idempotent(code, config)
        assert "arrData[nIdx * 2 + 1]" in result

    def test_fb_call_with_named_params(self, config):
        code = "fbTimer(IN := bStart, PT := T#5s, Q => bDone, ET => tElapsed);"
        result = _assert_idempotent(code, config)
        assert ":=" in result
        assert "=>" in result
        assert "T#5S" in result

    def test_struct_initialization(self, config):
        code = "stConfig := (nId := 1, sName := 'Test', fValue := 3.14);"
        result = _assert_idempotent(code, config)
        assert "(nId := 1" in result
        assert "sName := 'Test'" in result

    def test_array_initialization(self, config):
        code = "arrInit := [1, 2, 3, 4, 5];"
        result = _assert_idempotent(code, config)
        assert "[1, 2, 3, 4, 5]" in result

    def test_implicit_enum(self, config):
        code = (
            "TYPE E_State :\n"
            "(\n"
            "    Idle,\n"
            "    Running,\n"
            "    Error\n"
            ");\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        assert "Idle" in result
        assert "Running" in result
        assert "Error" in result

    def test_bit_access(self, config):
        code = "bBit0 := nWord.0;\nbBit7 := nByte.7;"
        result = _assert_idempotent(code, config)
        assert "nWord.0" in result
        assert "nByte.7" in result

    def test_type_conversion(self, config):
        code = (
            "nInt := REAL_TO_INT(fValue);\n"
            "fReal := INT_TO_REAL(nCount);\n"
            "bFlag := UINT_TO_BOOL(nStatus);"
        )
        result = _assert_idempotent(code, config)
        assert "REAL_TO_INT" in result
        assert "INT_TO_REAL" in result
        assert "UINT_TO_BOOL" in result

    def test_multiline_if_condition(self, config):
        code = (
            "IF bCondition1\n"
            "    AND bCondition2\n"
            "    AND bCondition3\n"
            "THEN\n"
            "    x := 1;\n"
            "END_IF;"
        )
        result = _assert_idempotent(code, config)
        assert "bCondition1" in result
        assert "bCondition2" in result
        assert "bCondition3" in result

    def test_property_declaration_context(self, config):
        """Property-like code (Get/Set bodies are in separate CDATA)."""
        code = "Value := _nInternal;"
        result = _assert_idempotent(code, config)
        assert "_nInternal" in result

    def test_negative_number(self, config):
        code = "x := -1;\ny := -3.14;\nz := nVal * -2;"
        result = _assert_idempotent(code, config)
        assert "-1" in result
        assert "-3.14" in result
        assert "* -2" in result or "*-2" in result or "* - 2" in result


# ---------------------------------------------------------------------------
# Safety: unrecognized constructs preserved
# ---------------------------------------------------------------------------


class TestUnrecognizedSyntax:
    """Verify formatter does not corrupt unknown/unusual syntax."""

    def test_unknown_identifier_preserved(self, config):
        """Identifiers that aren't keywords stay as-is."""
        code = "myCustomThing := fbSpecial.SomeMethod(arg1 := x, arg2 := y);"
        result = _assert_idempotent(code, config)
        assert "myCustomThing" in result
        assert "fbSpecial" in result
        assert "SomeMethod" in result

    def test_vendor_extension_syntax(self, config):
        """Vendor-specific extensions not in keyword list stay untouched."""
        code = "__POOLALLOCATOR.Alloc(SIZEOF(ST_Node));"
        result = _assert_idempotent(code, config)
        assert "__POOLALLOCATOR" in result

    def test_deeply_nested_expression(self, config):
        code = "x := ((((a + b) * c) - d) / e) MOD f;"
        result = _assert_idempotent(code, config)
        assert "((((a + b) * c) - d) / e)" in result
        assert "MOD" in result

    def test_very_long_line_preserved(self, config):
        """Line at exactly wrap limit should not be broken."""
        cfg = FormatterConfig()
        cfg.line_length.wrap_at = 300
        code = "x := " + "a + " * 50 + "b;"
        result = _format_st_pipeline(code, cfg)
        # Should not crash, content preserved
        assert "b;" in result

    def test_empty_source(self, config):
        code = ""
        result = _format_st_pipeline(code, config)
        assert result == ""

    def test_whitespace_only_source(self, config):
        code = "   \n\n   \n"
        result = _format_st_pipeline(code, config)
        # Whitespace-only should remain minimal/empty
        assert result.strip() == "" or result == code

    def test_comment_only_source(self, config):
        code = "(* This is just a comment *)"
        result = _format_st_pipeline(code, config)
        assert "(* This is just a comment *)" in result


# ---------------------------------------------------------------------------
# Region + Formatting Combined Edge Cases
# ---------------------------------------------------------------------------


class TestCombinedEdgeCases:

    def test_disable_inside_var_block(self, config):
        """Disable in the middle of a VAR block."""
        code = (
            "VAR\n"
            "    x : INT;\n"
            "{STweep.Disable}\n"
            "    y:INT;\n"
            "{STweep.Enable}\n"
            "    z : INT;\n"
            "END_VAR"
        )
        result = _format_st_pipeline(code, config)
        assert "y:INT;" in result

    def test_disable_around_entire_code(self, config):
        """Entire code disabled - nothing should change."""
        code = (
            "{STweep.Disable}\n"
            "x:=1;\n"
            "y:= 2;\n"
            "if x=1 then y:=3;end_if;"
        )
        result = _format_st_pipeline(code, config)
        assert "x:=1;" in result
        assert "y:= 2;" in result
        assert "if x=1 then y:=3;end_if;" in result

    def test_nested_disable_markers_not_supported(self, config):
        """Second disable while already disabled is just text."""
        code = (
            "{STweep.Disable}\n"
            "x := 1;\n"
            "{STweep.Disable}\n"
            "y := 2;\n"
            "{STweep.Enable}\n"
            "z := 3;"
        )
        segments = split_disable_regions(code)
        # First Enable re-enables, second Disable is just text in disabled region
        disabled_segment = segments[0][0] if not segments[0][1] else segments[1][0]
        assert "{STweep.Disable}" in disabled_segment
