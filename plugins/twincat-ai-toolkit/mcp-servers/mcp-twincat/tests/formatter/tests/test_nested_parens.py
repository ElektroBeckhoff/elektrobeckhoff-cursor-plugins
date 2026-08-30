"""Comprehensive tests for nested/recursive parentheses handling.

Verifies the formatter correctly handles:
- Deeply nested arithmetic: ((((x + y) * z)))
- Mixed bracket types: array[func(x, y)] 
- Parentheses inside strings/comments (must be ignored)
- FB calls with nested FB calls as parameters
- Struct init inside array init inside FB call
- OR/AND conditions with multiple grouped sub-expressions
- Mismatched-looking parens in strings
- Empty parentheses: func()
- Single-param parentheses: func(x)
- Recursive nesting depth (stress test)
"""
import pytest

from formatter.st_formatter import format_st_code
from formatter.st_alignment import (
    align_declarations,
    align_assignments,
    align_fb_call_params,
    _is_simple_assignment,
    _find_colon_pos,
)
from formatter.st_line_wrapper import wrap_long_lines, _split_params as wrap_split_params
from formatter.file_processor import _format_st_pipeline
from formatter.config import FormatterConfig


@pytest.fixture
def config():
    return FormatterConfig()


def _assert_idempotent(source: str, config: FormatterConfig) -> str:
    r1 = _format_st_pipeline(source, config)
    r2 = _format_st_pipeline(r1, config)
    assert r1 == r2, f"Not idempotent!\nFirst:\n{r1}\nSecond:\n{r2}"
    return r1


# ---------------------------------------------------------------------------
# Deeply nested arithmetic expressions
# ---------------------------------------------------------------------------


class TestDeepNestedArithmetic:

    def test_double_nested_parens(self, config):
        code = "x := ((a + b) * c);"
        result = _assert_idempotent(code, config)
        assert "((a + b) * c)" in result

    def test_triple_nested_parens(self, config):
        code = "x := (((a + b) * (c - d)) / e);"
        result = _assert_idempotent(code, config)
        assert "(((a + b) * (c - d)) / e)" in result

    def test_quad_nested_parens(self, config):
        code = "result := ((((nBase + nOffset) * nScale) - nBias) / nDivisor);"
        result = _assert_idempotent(code, config)
        assert "((((nBase + nOffset) * nScale) - nBias) / nDivisor)" in result

    def test_five_levels_deep(self, config):
        code = "x := (((((a + 1) * 2) + 3) * 4) + 5);"
        result = _assert_idempotent(code, config)
        assert "(((((a + 1) * 2) + 3) * 4) + 5)" in result

    def test_parallel_nested_groups(self, config):
        code = "x := (a + b) * (c + d) + (e * f) - (g / h);"
        result = _assert_idempotent(code, config)
        assert "(a + b)" in result
        assert "(c + d)" in result
        assert "(e * f)" in result
        assert "(g / h)" in result

    def test_nested_with_function_calls(self, config):
        code = "x := (ABS(a - b) + SQRT((c * c) + (d * d))) / 2.0;"
        result = _assert_idempotent(code, config)
        assert "ABS(a - b)" in result
        assert "SQRT((c * c) + (d * d))" in result


# ---------------------------------------------------------------------------
# Mixed bracket types: () [] combined
# ---------------------------------------------------------------------------


class TestMixedBrackets:

    def test_array_index_with_expression(self, config):
        code = "x := arrData[(nIdx + 1) * 2];"
        result = _assert_idempotent(code, config)
        assert "arrData[(nIdx + 1) * 2]" in result

    def test_function_in_array_index(self, config):
        code = "x := arrBuffer[F_GetIndex(nId, nOffset)];"
        result = _assert_idempotent(code, config)
        assert "arrBuffer[F_GetIndex(nId, nOffset)]" in result

    def test_array_in_function_param(self, config):
        code = "nResult := F_Calculate(arrInput[0], arrInput[nLen - 1]);"
        result = _assert_idempotent(code, config)
        assert "arrInput[0]" in result
        assert "arrInput[nLen - 1]" in result

    def test_nested_array_and_func(self, config):
        code = "x := arrOuter[arrInner[F_Idx(n)]];"
        result = _assert_idempotent(code, config)
        assert "arrOuter[arrInner[F_Idx(n)]]" in result

    def test_multidim_array_in_expression(self, config):
        code = "x := (arrMatrix[i, j] + arrMatrix[j, i]) / 2.0;"
        result = _assert_idempotent(code, config)
        assert "arrMatrix[i, j]" in result
        assert "arrMatrix[j, i]" in result

    def test_complex_array_init_with_nested_struct(self, config):
        code = "arrConfig := [(nId := 1, sName := 'A'), (nId := 2, sName := 'B')];"
        result = _assert_idempotent(code, config)
        assert "(nId := 1, sName := 'A')" in result
        assert "(nId := 2, sName := 'B')" in result


# ---------------------------------------------------------------------------
# Boolean/logical expressions with grouped conditions
# ---------------------------------------------------------------------------


class TestLogicalGrouping:

    def test_or_grouped_conditions(self, config):
        code = "IF (a = 1) OR (b = 2) OR (c = 3) THEN\n    x := 1;\nEND_IF;"
        result = _assert_idempotent(code, config)
        assert "(a = 1)" in result
        assert "(b = 2)" in result
        assert "(c = 3)" in result
        assert "OR" in result

    def test_and_grouped_conditions(self, config):
        code = "IF (bReady) AND (nCount > 0) AND (NOT bError) THEN\n    x := 1;\nEND_IF;"
        result = _assert_idempotent(code, config)
        assert "(bReady)" in result
        assert "(nCount > 0)" in result
        assert "(NOT bError)" in result

    def test_mixed_and_or_precedence(self, config):
        code = "bResult := (a AND b) OR (c AND d) OR (e AND NOT f);"
        result = _assert_idempotent(code, config)
        assert "(a AND b)" in result
        assert "(c AND d)" in result
        assert "(e AND NOT f)" in result

    def test_nested_logical_groups(self, config):
        code = "IF ((a = 1) OR (a = 2)) AND ((b > 0) OR (c > 0)) THEN\n    x := 1;\nEND_IF;"
        result = _assert_idempotent(code, config)
        assert "((a = 1) OR (a = 2))" in result
        assert "((b > 0) OR (c > 0))" in result

    def test_deeply_nested_logical(self, config):
        code = "bOk := (((x > 0) AND (x < 100)) OR ((y >= 0) AND (y <= 50))) AND bEnable;"
        result = _assert_idempotent(code, config)
        assert "(x > 0)" in result
        assert "(x < 100)" in result
        assert "(y >= 0)" in result
        assert "(y <= 50)" in result

    def test_and_then_with_parens(self, config):
        code = "IF (pData <> 0) AND_THEN (pData^.bValid) THEN\n    x := pData^.nValue;\nEND_IF;"
        result = _assert_idempotent(code, config)
        assert "(pData <> 0)" in result
        assert "(pData^.bValid)" in result
        assert "AND_THEN" in result


# ---------------------------------------------------------------------------
# FB calls with nested calls/expressions as parameters
# ---------------------------------------------------------------------------


class TestNestedFBCalls:

    def test_fb_call_with_nested_call_param(self, config):
        code = "fbOuter(nInput := F_Calculate(a, b), bEnable := TRUE);"
        result = _assert_idempotent(code, config)
        assert "F_Calculate(a, b)" in result

    def test_fb_call_with_expression_params(self, config):
        code = "fbMotor(fSpeed := (fTarget * fScale) + fOffset, bRun := TRUE);"
        result = _assert_idempotent(code, config)
        assert "(fTarget * fScale) + fOffset" in result

    def test_multiline_fb_call_with_nested_expressions(self, config):
        code = (
            "fbComplex(\n"
            "        nParam1 := (a + b) * c,\n"
            "        fParam2 := SQRT(x * x + y * y),\n"
            "        bParam3 := (nState = 0) OR (nState = 5),\n"
            "        stParam4 := (nId := 1, fVal := 3.14),\n"
            "        arrParam5 := arrData[nStart..(nStart + nLen - 1)]);"
        )
        result = _assert_idempotent(code, config)
        assert "(a + b) * c" in result
        assert "SQRT(x * x + y * y)" in result
        assert "(nState = 0) OR (nState = 5)" in result

    def test_nested_fb_call_three_levels(self, config):
        code = "x := F_Outer(F_Middle(F_Inner(a, b), c), d);"
        result = _assert_idempotent(code, config)
        assert "F_Inner(a, b)" in result
        assert "F_Middle(F_Inner(a, b), c)" in result
        assert "F_Outer(F_Middle(F_Inner(a, b), c), d)" in result

    def test_empty_parens_fb_call(self, config):
        code = "fbTimer();\nfbCounter();\nnResult := F_GetValue();"
        result = _assert_idempotent(code, config)
        assert "fbTimer();" in result or "fbTimer()" in result
        assert "F_GetValue()" in result


# ---------------------------------------------------------------------------
# Struct/Array initializations with nested brackets
# ---------------------------------------------------------------------------


class TestNestedInitializations:

    def test_struct_init_with_array_field(self, config):
        code = "stConfig := (nId := 1, arrValues := [10, 20, 30], sName := 'Test');"
        result = _assert_idempotent(code, config)
        assert "[10, 20, 30]" in result
        assert "nId := 1" in result

    def test_array_of_structs_init(self, config):
        code = "arrItems := [(nX := 1, nY := 2), (nX := 3, nY := 4), (nX := 5, nY := 6)];"
        result = _assert_idempotent(code, config)
        assert "(nX := 1, nY := 2)" in result
        assert "(nX := 3, nY := 4)" in result

    def test_nested_struct_init(self, config):
        code = "stOuter := (stInner := (nVal := 42, bFlag := TRUE), nCount := 5);"
        result = _assert_idempotent(code, config)
        assert "(nVal := 42, bFlag := TRUE)" in result
        assert "nCount := 5" in result

    def test_deeply_nested_init(self, config):
        code = "stDeep := (stLevel1 := (stLevel2 := (nLeaf := 99)));"
        result = _assert_idempotent(code, config)
        assert "(nLeaf := 99)" in result


# ---------------------------------------------------------------------------
# Parentheses in comments/strings (must be IGNORED)
# ---------------------------------------------------------------------------


class TestParensInNonCode:

    def test_parens_in_string_not_counted(self, config):
        """Parentheses inside strings must not affect bracket counting."""
        code = "sMsg := 'Error (code: ' + INT_TO_STRING(nErr) + ')';"
        result = _assert_idempotent(code, config)
        assert "'Error (code: '" in result
        assert "INT_TO_STRING(nErr)" in result

    def test_brackets_in_block_comment(self, config):
        code = "x := 1; (* array[0] and func(a, b) are examples *)"
        result = _assert_idempotent(code, config)
        assert "(* array[0] and func(a, b) are examples *)" in result

    def test_brackets_in_line_comment(self, config):
        code = "x := 1; // func(a) + arr[0]"
        result = _assert_idempotent(code, config)
        assert "// func(a) + arr[0]" in result

    def test_mismatched_paren_in_string(self, config):
        """A string with unbalanced paren must not confuse the formatter."""
        code = "sOpen := '(';\nsClose := ')';\nsCombo := '(())';"
        result = _assert_idempotent(code, config)
        assert "'('" in result
        assert "')'" in result
        assert "'(())'" in result

    def test_bracket_in_pragma(self, config):
        code = "{attribute 'TcRpcEnable' := '(nParam := 0)'}\nnValue := 1;"
        result = _assert_idempotent(code, config)
        assert "{attribute 'TcRpcEnable' := '(nParam := 0)'}" in result


# ---------------------------------------------------------------------------
# _split_params: unit tests for nesting correctness
# ---------------------------------------------------------------------------


class TestSplitParams:
    """Direct tests of the parameter splitting logic."""

    def test_simple_params(self):
        result = wrap_split_params("a, b, c")
        assert result == ["a", " b", " c"]

    def test_nested_call_in_param(self):
        result = wrap_split_params("F_Inner(a, b), c, d")
        assert len(result) == 3
        assert "F_Inner(a, b)" in result[0]

    def test_deeply_nested_calls(self):
        result = wrap_split_params("F_A(F_B(x, y), z), w")
        assert len(result) == 2
        assert "F_A(F_B(x, y), z)" in result[0]

    def test_array_bracket_in_param(self):
        result = wrap_split_params("arr[0, 1], arr[2, 3]")
        assert len(result) == 2
        assert "arr[0, 1]" in result[0]
        assert "arr[2, 3]" in result[1].strip()

    def test_mixed_nesting(self):
        result = wrap_split_params("F_A(arr[i, j]), (x + y)")
        assert len(result) == 2
        assert "F_A(arr[i, j])" in result[0]

    def test_string_with_comma_not_split(self):
        result = wrap_split_params("sName := 'a, b, c', nVal := 1")
        assert len(result) == 2

    def test_empty_params(self):
        result = wrap_split_params("")
        assert result == [] or result == [""]

    def test_single_param(self):
        result = wrap_split_params("x := 42")
        assert len(result) == 1
        assert "x := 42" in result[0]

    def test_three_levels_nested(self):
        result = wrap_split_params("F_A(F_B(F_C(1, 2), 3), 4), 5, 6")
        assert len(result) == 3
        assert "F_A(F_B(F_C(1, 2), 3), 4)" in result[0]


# ---------------------------------------------------------------------------
# _is_simple_assignment: parentheses depth check
# ---------------------------------------------------------------------------


class TestIsSimpleAssignment:
    """Verify := inside parens is NOT treated as top-level assignment."""

    def test_simple_assign_is_true(self):
        assert _is_simple_assignment("    x := 1;") is True

    def test_assign_in_fb_call_is_false(self):
        assert _is_simple_assignment("    fbTimer(IN := TRUE);") is False

    def test_assign_in_nested_call_is_false(self):
        assert _is_simple_assignment("    F_X(nA := F_Y(nB := 1));") is False

    def test_assign_with_expression_parens_is_true(self):
        assert _is_simple_assignment("    x := (a + b) * c;") is True

    def test_assign_with_nested_parens_rhs_is_true(self):
        assert _is_simple_assignment("    x := ((a + b) * (c - d));") is True

    def test_struct_init_is_true(self):
        # Struct inits have 1 top-level := and nested := inside parens — treated as simple
        # assignments; the _MAX_ASSIGN_SPREAD limit prevents over-alignment in groups.
        assert _is_simple_assignment("    stCfg := (nId := 1, sName := 'X');") is True

    def test_multiline_continuation_is_false(self):
        assert _is_simple_assignment("        param1 := val1,") is False


# ---------------------------------------------------------------------------
# _find_colon_pos: respects strings, comments, nested brackets
# ---------------------------------------------------------------------------


class TestFindColonPos:
    """Verify colon detection skips colons in strings/comments."""

    def test_simple_declaration(self):
        pos = _find_colon_pos("x : INT;")
        assert pos == 2

    def test_colon_in_string_ignored(self):
        pos = _find_colon_pos("sMsg : STRING := 'key:value';")
        assert pos == 5

    def test_colon_in_block_comment_ignored(self):
        pos = _find_colon_pos("nVal (* a:b *) : INT;")
        assert pos > 0
        actual_content = "nVal (* a:b *) : INT;"
        assert actual_content[pos] == ":"
        assert actual_content[pos + 1] != "="

    def test_assign_operator_not_matched(self):
        pos = _find_colon_pos("x := 1;")
        # := should NOT be found as declaration colon
        assert pos == -1

    def test_double_colon_not_matched(self):
        pos = _find_colon_pos("Ns::Type")
        assert pos == -1

    def test_name_ending_digit_before_colon(self):
        pos = _find_colon_pos("nShadingAux3 : UDINT;")
        assert pos == len("nShadingAux3 ")

    def test_time_literal_digit_colon_skipped(self):
        pos = _find_colon_pos("TOD#19:00:00")
        assert pos == -1

    def test_dt_literal_in_decl_init(self):
        pos = _find_colon_pos("dtEvent : DT := DT#2024-01-15-12:30:00;")
        assert pos == len("dtEvent ")

    def test_jmp_label_not_declaration_colon(self):
        pos = _find_colon_pos("_label1:")
        assert pos == len("_label1")

    def test_multi_var_name_ending_digit(self):
        pos = _find_colon_pos("nAux, nAux2, nAux3 : UDINT;")
        assert pos == len("nAux, nAux2, nAux3 ")


# ---------------------------------------------------------------------------
# Stress test: extreme nesting depth
# ---------------------------------------------------------------------------


class TestExtremeNesting:

    def test_10_levels_deep_parens(self, config):
        """10 levels of parentheses nesting."""
        inner = "x"
        for _ in range(10):
            inner = f"({inner} + 1)"
        code = f"result := {inner};"
        result = _assert_idempotent(code, config)
        assert result.count("(") == 10
        assert result.count(")") == 10

    def test_10_levels_mixed_brackets(self, config):
        """Alternating () and [] nesting."""
        code = "x := arr[func(arr2[calc(arr3[0] + 1)] * 2) - 1];"
        result = _assert_idempotent(code, config)
        assert "arr[func(arr2[calc(arr3[0] + 1)] * 2) - 1]" in result

    def test_many_parallel_groups(self, config):
        """Many parallel parenthesized groups."""
        groups = " + ".join(f"(n{i} * {i})" for i in range(20))
        code = f"nSum := {groups};"
        result = _assert_idempotent(code, config)
        for i in range(20):
            assert f"(n{i} * {i})" in result

    def test_recursive_struct_init_depth(self, config):
        """Struct init nested 5 levels deep."""
        code = "st := (a := (b := (c := (d := (e := 42)))));"
        result = _assert_idempotent(code, config)
        assert "(e := 42)" in result
        assert "(d := (e := 42))" in result

    def test_wrapping_preserves_nesting(self, config):
        """Even after line wrapping, nested parens stay balanced."""
        cfg = FormatterConfig()
        cfg.line_length.wrap_at = 80
        cfg.calls.max_params_single_line = 2

        code = "fbComplex(nA := (x + y) * z, fB := SQRT((a * a) + (b * b)), sC := 'test', nD := arr[0]);"
        result = _format_st_pipeline(code, cfg)
        assert result.count("(") == result.count(")")
        assert result.count("[") == result.count("]")


# ---------------------------------------------------------------------------
# Edge: Type declarations with parens (enum, subrange)
# ---------------------------------------------------------------------------


class TestTypeDeclarationsWithParens:

    def test_enum_implicit_in_declaration(self, config):
        code = "VAR\n    eMode : (Idle, Running, Error);\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "(Idle, Running, Error)" in result

    def test_subrange_type(self, config):
        code = "VAR\n    nBounded : INT(0..100);\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "INT(0..100)" in result

    def test_string_size_parens(self, config):
        code = "VAR\n    sName : STRING(255) := '';\n    wsPath : WSTRING(1024);\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "STRING(255)" in result
        assert "WSTRING(1024)" in result

    def test_array_of_string_with_size(self, config):
        code = "VAR\n    arrNames : ARRAY[0..9] OF STRING(80);\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..9] OF STRING(80)" in result

    def test_pointer_to_function_block(self, config):
        code = "VAR\n    pFb : POINTER TO FB_Base;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "POINTER TO FB_Base" in result


# ---------------------------------------------------------------------------
# Edge: Expressions used in FOR/WHILE/CASE
# ---------------------------------------------------------------------------


class TestControlFlowWithParens:

    def test_for_with_expression_bounds(self, config):
        code = "FOR i := (nStart + nOffset) TO (nEnd - 1) BY (nStep * 2) DO\n    x := 1;\nEND_FOR;"
        result = _assert_idempotent(code, config)
        assert "(nStart + nOffset)" in result
        assert "(nEnd - 1)" in result
        assert "(nStep * 2)" in result

    def test_while_with_complex_condition(self, config):
        code = "WHILE ((nCount < nMax) AND (NOT bAbort)) OR (bForce) DO\n    nCount := nCount + 1;\nEND_WHILE;"
        result = _assert_idempotent(code, config)
        assert "((nCount < nMax) AND (NOT bAbort))" in result
        assert "(bForce)" in result

    def test_case_with_expression(self, config):
        code = "CASE (nState + nOffset) OF\n0:\n    x := 1;\nEND_CASE;"
        result = _assert_idempotent(code, config)
        assert "(nState + nOffset)" in result

    def test_if_with_function_call_condition(self, config):
        code = "IF F_IsValid(pData) AND (F_GetCount(pData) > 0) THEN\n    x := 1;\nEND_IF;"
        result = _assert_idempotent(code, config)
        assert "F_IsValid(pData)" in result
        assert "(F_GetCount(pData) > 0)" in result
