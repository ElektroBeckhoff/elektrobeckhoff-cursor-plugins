"""Comprehensive tests for ALL array/struct initialization and declaration patterns.

Covers:
- ARRAY OF STRUCT (type declaration + initialization)
- 2D/3D array initialization (nested brackets)
- Repeat-syntax n(val) for array init
- ARRAY OF POINTER TO / ARRAY OF INTERFACE
- Struct with array-of-struct field
- Large arrays (>30 elements, wrap behavior)
- Array in VAR_IN_OUT (by-reference)
- Array bounds with constants/expressions
- Array of FB instances
- Multiline init with alignment
- Nested ARRAY OF ARRAY OF STRUCT init
- ARRAY + STRUCT combined in complex declarations
- Edge: empty arrays, single-element arrays
- Edge: array of BOOL/STRING/ENUM init
"""
import pytest

from formatter.st_formatter import format_st_code
from formatter.st_alignment import align_declarations
from formatter.st_line_wrapper import wrap_long_lines
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
# ARRAY OF STRUCT type declarations
# ---------------------------------------------------------------------------


class TestArrayOfStructTypeDecl:

    def test_type_array_of_struct(self, config):
        code = (
            "TYPE ST_Point :\n"
            "STRUCT\n"
            "    fX : REAL;\n"
            "    fY : REAL;\n"
            "END_STRUCT\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        assert "ST_Point" in result
        assert "fX" in result
        assert "fY" in result

    def test_var_array_of_struct(self, config):
        code = (
            "VAR\n"
            "    arrPoints : ARRAY[0..9] OF ST_Point;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..9] OF ST_Point" in result

    def test_var_array_of_struct_with_init(self, config):
        code = (
            "VAR\n"
            "    arrPts : ARRAY[0..2] OF ST_Point := [\n"
            "        (fX := 0.0, fY := 0.0),\n"
            "        (fX := 1.0, fY := 1.0),\n"
            "        (fX := 2.0, fY := 2.0)\n"
            "    ];\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..2] OF ST_Point" in result
        assert "(fX := 0.0, fY := 0.0)" in result
        assert "(fX := 2.0, fY := 2.0)" in result

    def test_array_of_struct_single_line_init(self, config):
        code = "VAR\n    arr : ARRAY[0..1] OF ST_Pair := [(nA := 1, nB := 2), (nA := 3, nB := 4)];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "[(nA := 1, nB := 2), (nA := 3, nB := 4)]" in result


# ---------------------------------------------------------------------------
# 2D / 3D array initializations
# ---------------------------------------------------------------------------


class TestMultiDimArrayInit:

    def test_2d_array_declaration(self, config):
        code = "VAR\n    arrGrid : ARRAY[0..2, 0..2] OF INT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..2, 0..2] OF INT" in result

    def test_2d_array_init_flat(self, config):
        """2D arrays are initialized as flat list in TwinCAT."""
        code = "VAR\n    arrGrid : ARRAY[0..1, 0..1] OF INT := [1, 2, 3, 4];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "[1, 2, 3, 4]" in result

    def test_3d_array_declaration(self, config):
        code = "VAR\n    arrCube : ARRAY[0..2, 0..2, 0..2] OF REAL;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..2, 0..2, 0..2] OF REAL" in result

    def test_2d_array_multiline_init(self, config):
        code = (
            "VAR\n"
            "    arrMatrix : ARRAY[0..2, 0..2] OF INT := [\n"
            "        1, 0, 0,\n"
            "        0, 1, 0,\n"
            "        0, 0, 1\n"
            "    ];\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..2, 0..2] OF INT" in result
        # All values preserved
        assert "1, 0, 0" in result


# ---------------------------------------------------------------------------
# Repeat syntax: n(val)
# ---------------------------------------------------------------------------


class TestRepeatSyntax:

    def test_simple_repeat_init(self, config):
        """TwinCAT supports n(value) for array init."""
        code = "VAR\n    arrZeros : ARRAY[0..99] OF INT := 100(0);\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "100(0)" in result

    def test_repeat_with_expression(self, config):
        code = "VAR\n    arrDefaults : ARRAY[0..9] OF REAL := 10(3.14);\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "10(3.14)" in result

    def test_mixed_repeat_and_values(self, config):
        """Mix of explicit values and repeat."""
        code = "VAR\n    arrMixed : ARRAY[0..5] OF INT := [1, 2, 3(0)];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "[1, 2, 3(0)]" in result

    def test_repeat_struct_init(self, config):
        code = "VAR\n    arrSt : ARRAY[0..4] OF ST_Pt := 5((fX := 0.0, fY := 0.0));\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "5((fX := 0.0, fY := 0.0))" in result


# ---------------------------------------------------------------------------
# ARRAY OF POINTER TO / ARRAY OF INTERFACE
# ---------------------------------------------------------------------------


class TestArrayOfPointerInterface:

    def test_array_of_pointer_to_fb(self, config):
        code = "VAR\n    arrPtrs : ARRAY[0..9] OF POINTER TO FB_Base;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..9] OF POINTER TO FB_Base" in result

    def test_array_of_pointer_to_struct(self, config):
        code = "VAR\n    arrPData : ARRAY[0..3] OF POINTER TO ST_Data;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "POINTER TO ST_Data" in result

    def test_array_of_interface(self, config):
        code = "VAR\n    arrWidgets : ARRAY[0..19] OF I_Widget;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..19] OF I_Widget" in result

    def test_array_of_reference_to(self, config):
        code = "VAR\n    arrRefs : ARRAY[0..4] OF REFERENCE TO INT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..4] OF REFERENCE TO INT" in result


# ---------------------------------------------------------------------------
# Struct with array-of-struct field
# ---------------------------------------------------------------------------


class TestStructWithArrayFields:

    def test_struct_with_array_field(self, config):
        code = (
            "TYPE ST_Container :\n"
            "STRUCT\n"
            "    nCount  : UINT;\n"
            "    arrData : ARRAY[0..9] OF ST_Item;\n"
            "    sName   : STRING(80);\n"
            "END_STRUCT\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..9] OF ST_Item" in result
        assert "nCount" in result
        assert "sName" in result

    def test_struct_with_2d_array(self, config):
        code = (
            "TYPE ST_Grid :\n"
            "STRUCT\n"
            "    arrCells : ARRAY[0..7, 0..7] OF BOOL;\n"
            "    nRows    : UINT := 8;\n"
            "    nCols    : UINT := 8;\n"
            "END_STRUCT\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..7, 0..7] OF BOOL" in result

    def test_struct_with_multiple_arrays(self, config):
        code = (
            "TYPE ST_MultiArray :\n"
            "STRUCT\n"
            "    arrX : ARRAY[0..99] OF REAL;\n"
            "    arrY : ARRAY[0..99] OF REAL;\n"
            "    arrZ : ARRAY[0..99] OF REAL;\n"
            "    nLen : UINT;\n"
            "END_STRUCT\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        assert "arrX" in result
        assert "arrY" in result
        assert "arrZ" in result

    def test_nested_struct_with_array(self, config):
        """Struct containing a struct that has array fields."""
        code = (
            "VAR\n"
            "    stOuter : ST_Outer;\n"
            "END_VAR\n"
            "stOuter.stInner.arrValues[0] := 42;"
        )
        result = _assert_idempotent(code, config)
        assert "stOuter.stInner.arrValues[0]" in result


# ---------------------------------------------------------------------------
# Large arrays (>30 elements)
# ---------------------------------------------------------------------------


class TestLargeArrays:

    def test_large_array_init_single_line(self, config):
        """Array with exactly 30 elements (at wrap threshold)."""
        elements = ", ".join(str(i) for i in range(30))
        code = f"VAR\n    arr : ARRAY[0..29] OF INT := [{elements}];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "[" in result
        assert "]" in result
        # All 30 elements preserved
        assert "29" in result

    def test_large_array_init_multiline(self, config):
        """Array with >30 elements spanning multiple lines."""
        lines = []
        lines.append("VAR")
        lines.append("    arrBig : ARRAY[0..49] OF INT := [")
        for row in range(5):
            start = row * 10
            vals = ", ".join(str(i) for i in range(start, start + 10))
            comma = "," if row < 4 else ""
            lines.append(f"        {vals}{comma}")
        lines.append("    ];")
        lines.append("END_VAR")
        code = "\n".join(lines)
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..49] OF INT" in result
        # Spot check values
        assert "0, 1, 2" in result
        assert "49" in result

    def test_array_of_bool_init(self, config):
        code = "VAR\n    arrFlags : ARRAY[0..7] OF BOOL := [TRUE, FALSE, TRUE, FALSE, TRUE, FALSE, TRUE, FALSE];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "TRUE" in result
        assert "FALSE" in result


# ---------------------------------------------------------------------------
# Array in VAR_IN_OUT (by-reference)
# ---------------------------------------------------------------------------


class TestArrayInVarInOut:

    def test_array_in_var_in_out(self, config):
        code = "VAR_IN_OUT\n    arrBuffer : ARRAY[0..255] OF BYTE;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "VAR_IN_OUT" in result
        assert "ARRAY[0..255] OF BYTE" in result

    def test_array_of_struct_in_var_in_out(self, config):
        code = "VAR_IN_OUT\n    arrItems : ARRAY[0..49] OF ST_Item;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..49] OF ST_Item" in result

    def test_var_in_out_constant_array(self, config):
        code = "VAR_IN_OUT CONSTANT\n    arrReadOnly : ARRAY[0..9] OF REAL;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "CONSTANT" in result
        assert "ARRAY[0..9] OF REAL" in result


# ---------------------------------------------------------------------------
# Array bounds with constants/expressions
# ---------------------------------------------------------------------------


class TestArrayBoundsExpressions:

    def test_bounds_with_constants(self, config):
        code = "VAR\n    arrData : ARRAY[0..cMaxItems - 1] OF REAL;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..cMaxItems - 1] OF REAL" in result

    def test_bounds_with_global_constant(self, config):
        code = "VAR\n    arrBuffer : ARRAY[1..Param.cBufferSize] OF BYTE;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[1..Param.cBufferSize] OF BYTE" in result

    def test_bounds_with_enum_values(self, config):
        code = "VAR\n    arrByEnum : ARRAY[E_Channel.Ch1..E_Channel.Ch8] OF REAL;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "E_Channel.Ch1..E_Channel.Ch8" in result

    def test_bounds_negative_index(self, config):
        code = "VAR\n    arrCentered : ARRAY[-5..5] OF INT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[-5..5] OF INT" in result


# ---------------------------------------------------------------------------
# Array of FB instances
# ---------------------------------------------------------------------------


class TestArrayOfFBInstances:

    def test_array_of_fb(self, config):
        code = "VAR\n    arrTimers : ARRAY[0..3] OF TON;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..3] OF TON" in result

    def test_array_of_fb_with_init(self, config):
        code = (
            "VAR\n"
            "    arrTons : ARRAY[0..1] OF TON := [\n"
            "        (PT := T#1s),\n"
            "        (PT := T#2s)\n"
            "    ];\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "(PT := T#1S)" in result
        assert "(PT := T#2S)" in result

    def test_array_of_custom_fb(self, config):
        code = "VAR\n    arrMotors : ARRAY[1..8] OF FB_MotorControl;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[1..8] OF FB_MotorControl" in result

    def test_array_of_fb_access_in_loop(self, config):
        code = (
            "FOR i := 0 TO 3 DO\n"
            "    arrTimers[i](IN := arrEnable[i], PT := T#5s);\n"
            "    arrDone[i] := arrTimers[i].Q;\n"
            "END_FOR;"
        )
        result = _assert_idempotent(code, config)
        assert "arrTimers[i](" in result
        assert "arrTimers[i].Q" in result


# ---------------------------------------------------------------------------
# Nested ARRAY OF ARRAY OF STRUCT
# ---------------------------------------------------------------------------


class TestDeepNestedArrayStruct:

    def test_array_of_array_of_int(self, config):
        code = "VAR\n    arrNested : ARRAY[0..2] OF ARRAY[0..4] OF INT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..2] OF ARRAY[0..4] OF INT" in result

    def test_array_of_array_access(self, config):
        code = "x := arrNested[i][j];"
        result = _assert_idempotent(code, config)
        assert "arrNested[i][j]" in result

    def test_array_of_array_of_struct(self, config):
        code = "VAR\n    arrGrid : ARRAY[0..3] OF ARRAY[0..3] OF ST_Cell;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..3] OF ARRAY[0..3] OF ST_Cell" in result

    def test_array_of_array_of_struct_access(self, config):
        code = "arrGrid[row][col].bOccupied := TRUE;\narrGrid[row][col].nValue := nNewVal;"
        result = _assert_idempotent(code, config)
        assert "arrGrid[row][col].bOccupied" in result
        assert "arrGrid[row][col].nValue" in result


# ---------------------------------------------------------------------------
# Array init: BOOL, STRING, ENUM
# ---------------------------------------------------------------------------


class TestArrayInitSpecificTypes:

    def test_array_of_bool_all_true(self, config):
        code = "VAR\n    arrEn : ARRAY[0..3] OF BOOL := [TRUE, TRUE, TRUE, TRUE];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "[TRUE, TRUE, TRUE, TRUE]" in result

    def test_array_of_string_init(self, config):
        code = (
            "VAR\n"
            "    arrNames : ARRAY[0..2] OF STRING := [\n"
            "        'Alice',\n"
            "        'Bob',\n"
            "        'Charlie'\n"
            "    ];\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "'Alice'" in result
        assert "'Bob'" in result
        assert "'Charlie'" in result

    def test_array_of_enum_init(self, config):
        code = "VAR\n    arrStates : ARRAY[0..2] OF E_State := [E_State.Idle, E_State.Running, E_State.Error];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "E_State.Idle" in result
        assert "E_State.Running" in result
        assert "E_State.Error" in result

    def test_array_of_time_init(self, config):
        code = "VAR\n    arrDelays : ARRAY[0..3] OF TIME := [T#100ms, T#200ms, T#500ms, T#1s];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "T#100MS" in result
        assert "T#1S" in result


# ---------------------------------------------------------------------------
# Edge cases: empty, single element, max complexity
# ---------------------------------------------------------------------------


class TestArrayEdgeCases:

    def test_single_element_array(self, config):
        code = "VAR\n    arrSingle : ARRAY[0..0] OF INT := [42];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "[42]" in result
        assert "ARRAY[0..0]" in result

    def test_array_assigned_in_loop(self, config):
        code = (
            "FOR i := 0 TO 9 DO\n"
            "    arrValues[i] := i * 2;\n"
            "END_FOR;"
        )
        result = _assert_idempotent(code, config)
        assert "arrValues[i]" in result
        assert "i * 2" in result

    def test_array_as_fb_output(self, config):
        code = "fbSensor(arrOutput => arrReadings);"
        result = _assert_idempotent(code, config)
        assert "arrOutput => arrReadings" in result

    def test_array_slice_copy(self, config):
        """MEMCPY-style array element access."""
        code = (
            "FOR i := 0 TO nLen - 1 DO\n"
            "    arrDest[nDestOffset + i] := arrSrc[nSrcOffset + i];\n"
            "END_FOR;"
        )
        result = _assert_idempotent(code, config)
        assert "arrDest[nDestOffset + i]" in result
        assert "arrSrc[nSrcOffset + i]" in result

    def test_complex_struct_array_field_access(self, config):
        """Deep access: array → struct → array → field."""
        code = "fVal := arrSensors[nCh].stConfig.arrCalibration[nPt].fOffset;"
        result = _assert_idempotent(code, config)
        assert "arrSensors[nCh].stConfig.arrCalibration[nPt].fOffset" in result

    def test_array_in_if_condition(self, config):
        code = "IF arrFlags[nIdx] AND (arrValues[nIdx] > fThreshold) THEN\n    bAlarm := TRUE;\nEND_IF;"
        result = _assert_idempotent(code, config)
        assert "arrFlags[nIdx]" in result
        assert "arrValues[nIdx] > fThreshold" in result

    def test_array_passed_to_function(self, config):
        code = "nSum := F_SumArray(arrData := arrValues, nLen := 10);"
        result = _assert_idempotent(code, config)
        assert "arrData := arrValues" in result

    def test_array_sizeof(self, config):
        code = "nSize := SIZEOF(arrBuffer) / SIZEOF(arrBuffer[0]);"
        result = _assert_idempotent(code, config)
        assert "SIZEOF(arrBuffer)" in result
        assert "SIZEOF(arrBuffer[0])" in result


# ---------------------------------------------------------------------------
# FB_init Array Instantiation & Canonical Multiline Formatting
# ---------------------------------------------------------------------------


class TestFBInitArrayInstantiation:

    def test_fb_init_array_single_line(self, config):
        code = "VAR\n    arrFbs : ARRAY[1..2] OF FB_Sample[(nParam := 1), (nParam := 2)];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "ARRAY[1..2] OF FB_Sample[(nParam := 1), (nParam := 2)]" in result

    def test_fb_init_array_multiline_params(self, config):
        code = (
            "VAR\n"
            "    arrFbs : ARRAY[1..2] OF FB_Sample[\n"
            "        (nParam := 10),\n"
            "        (nParam := 20)\n"
            "    ];\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "(nParam := 10)" in result
        assert "(nParam := 20)" in result

    def test_fb_init_array_repetition_factor(self, config):
        code = "VAR\n    arrBacnet : ARRAY[1..MAX_OBJ] OF FB_BACnet_AI := [MAX_OBJ((Server := Server, iParent := View_AI))];\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "[MAX_OBJ((Server := Server, iParent := View_AI))]" in result

    def test_fb_init_array_with_initializers(self, config):
        code = (
            "VAR\n"
            "    arrFbs : ARRAY[1..2] OF FB_Sample[(nInit := 1), (nInit := 2)] := [\n"
            "        (nInput := 5, nProp := 6),\n"
            "        (nInput := 8, nProp := 9)\n"
            "    ];\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "(nInput := 5, nProp := 6)" in result
        assert "(nInput := 8, nProp := 9)" in result


class TestMultilineArrayCanonicalIndentation:

    def test_2d_matrix_canonical_indent(self, config):
        raw = (
            "VAR\n"
            "arr2D : ARRAY[1..2, 1..2] OF REAL := [\n"
            "1.1, 1.2,\n"
            "2.1, 2.2\n"
            "];\n"
            "END_VAR"
        )
        expected = (
            "VAR\n"
            "    arr2D : ARRAY[1..2, 1..2] OF REAL := [\n"
            "        1.1, 1.2,\n"
            "        2.1, 2.2\n"
            "    ];\n"
            "END_VAR"
        )
        result = _format_st_pipeline(raw, config)
        assert result == expected
        # Fixed-point check
        assert _format_st_pipeline(result, config) == result

    def test_repetition_factor_multiline_canonical_indent(self, config):
        raw = (
            "VAR\n"
            "arrRepeat : ARRAY[1..100] OF INT := [\n"
            "10(0),\n"
            "20(1),\n"
            "70(99)\n"
            "];\n"
            "END_VAR"
        )
        expected = (
            "VAR\n"
            "    arrRepeat : ARRAY[1..100] OF INT := [\n"
            "        10(0),\n"
            "        20(1),\n"
            "        70(99)\n"
            "    ];\n"
            "END_VAR"
        )
        result = _format_st_pipeline(raw, config)
        assert result == expected
        assert _format_st_pipeline(result, config) == result

    def test_multiline_array_with_row_comments(self, config):
        raw = (
            "VAR\n"
            "arrMatrix : ARRAY[1..2, 1..2] OF REAL := [\n"
            "1.0, 0.5, // Row 1\n"
            "0.5, 1.0 // Row 2\n"
            "];\n"
            "END_VAR"
        )
        expected = (
            "VAR\n"
            "    arrMatrix : ARRAY[1..2, 1..2] OF REAL := [\n"
            "        1.0, 0.5, // Row 1\n"
            "        0.5, 1.0 // Row 2\n"
            "    ];\n"
            "END_VAR"
        )
        result = _format_st_pipeline(raw, config)
        assert result == expected
        assert _format_st_pipeline(result, config) == result

    def test_multiline_array_in_struct(self, config):
        raw = (
            "TYPE ST_TestArray :\n"
            "STRUCT\n"
            "arrVals : ARRAY[1..2] OF INT := [\n"
            "100,\n"
            "200\n"
            "];\n"
            "END_STRUCT\n"
            "END_TYPE"
        )
        expected = (
            "TYPE ST_TestArray :\n"
            "    STRUCT\n"
            "        arrVals : ARRAY[1..2] OF INT := [\n"
            "            100,\n"
            "            200\n"
            "        ];\n"
            "    END_STRUCT\n"
            "END_TYPE"
        )
        result = _format_st_pipeline(raw, config)
        assert result == expected
        assert _format_st_pipeline(result, config) == result

    def test_multiline_array_implementation_assign(self, config):
        raw = (
            "arrMatrix := [\n"
            "1.0, 2.0,\n"
            "3.0, 4.0\n"
            "];"
        )
        expected = (
            "arrMatrix := [\n"
            "    1.0, 2.0,\n"
            "    3.0, 4.0\n"
            "];"
        )
        result = _format_st_pipeline(raw, config)
        assert result == expected
        assert _format_st_pipeline(result, config) == result

