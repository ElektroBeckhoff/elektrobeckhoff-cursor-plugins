"""Tests for robust ST call / designator recognition and formatting."""
from __future__ import annotations

import pytest

from formatter.config import load_config
from formatter.file_processor import _format_st_pipeline, _normalize_call_param_indent
from formatter.st_call_expr import (
    is_st_call_callee,
    match_control_call_opener,
    match_multiline_call_opener,
    scan_st_designator,
    split_single_line_call,
)
from formatter.st_line_wrapper import wrap_long_lines
from formatter.st_parse_utils import is_if_wrapped_call_opener


# ---------------------------------------------------------------------------
# Designator scanner
# ---------------------------------------------------------------------------


class TestScanStDesignator:
    @pytest.mark.parametrize(
        "expr",
        [
            "FbName",
            "fbInst.Method",
            "_arrLogZone[_nZoneIdx]",
            "_arrLogZone[_nZoneIdx].AddField",
            "foo.bar[i].baz[j].Meth",
            "arr[foo[1]].Meth",
            "arr[i][j].Meth",
            "THIS^.Method",
            "SUPER^.Method",
            "pFb^.Method",
            "pFb^.pNext^.Method",
            "__ISVALIDREF",
            "__NEW",
            "obj.arr[ nIdx + 1 ].Meth",
        ],
    )
    def test_accepts_designators(self, expr: str):
        assert is_st_call_callee(expr)

    @pytest.mark.parametrize(
        "expr",
        [
            "",
            "IF",
            "WHILE",
            "foo : FB_Bar",
            "st :=",
            "1.Method",
            ".Method",
            "arr[",
            "arr[1",
            "foo.",
            "pFb^.",
        ],
    )
    def test_rejects_non_designators(self, expr: str):
        assert not is_st_call_callee(expr)

    def test_scan_stops_before_trailing_junk(self):
        text = "_arrFb[i].AddField("
        end = scan_st_designator(text, 0)
        assert end == text.index("(")


# ---------------------------------------------------------------------------
# Multiline call openers
# ---------------------------------------------------------------------------


class TestMultilineCallOpener:
    @pytest.mark.parametrize(
        "line,callee",
        [
            ("    _fbLogOccupancy.AddField(", "_fbLogOccupancy.AddField"),
            ("        _arrLogZone[_nZoneIdx].AddField(", "_arrLogZone[_nZoneIdx].AddField"),
            ("    foo.bar[i].baz[j].Meth(", "foo.bar[i].baz[j].Meth"),
            ("    arr[foo[1]].Meth(", "arr[foo[1]].Meth"),
            ("    arr[i][j].Meth(", "arr[i][j].Meth"),
            ("    THIS^.AddField(", "THIS^.AddField"),
            ("    pFb^.Method(", "pFb^.Method"),
            ("    result := _arrLogZone[_nZoneIdx].AddField(", "_arrLogZone[_nZoneIdx].AddField"),
            ("    result := Func(", "Func"),
        ],
    )
    def test_matches_call_openers(self, line: str, callee: str):
        m = match_multiline_call_opener(line)
        assert m is not None
        assert m.callee == callee
        assert m.group(1) == line[: len(line) - len(line.lstrip())]

    @pytest.mark.parametrize(
        "line",
        [
            "    stConfig := (",
            "    arrFacade := [(",
            "    IF condition THEN",
            "    IF FindAndSplit(",
            "    foo : FB_Bar(",
            "    (",
        ],
    )
    def test_rejects_non_call_openers(self, line: str):
        assert match_multiline_call_opener(line) is None


class TestControlCallOpener:
    @pytest.mark.parametrize(
        "line",
        [
            "IF NOT concat2(",
            "IF NOT __ISVALIDREF(",
            "IF pDyn^.Init(",
            "IF NOT _arrLogZone[_nZoneIdx].AddField(",
            "WHILE fbArr[i].Busy(",
            "ELSIF pFb^.Method(",
            "UNTIL arr[foo[1]].Done(",
        ],
    )
    def test_matches(self, line: str):
        assert match_control_call_opener(line) is not None
        assert is_if_wrapped_call_opener(line)

    def test_rejects_boolean_if(self):
        line = "IF (nA <> 0) AND_THEN (nB > 0) THEN"
        assert match_control_call_opener(line) is None
        assert not is_if_wrapped_call_opener(line)


# ---------------------------------------------------------------------------
# Param indent normalization (the RoomControl bug)
# ---------------------------------------------------------------------------


class TestNormalizeCallParamIndent:
    def test_simple_method_indent(self):
        lines = [
            "    _fbLogMeasurements.AddField(",
            "    pValue := ADR(x),",
            "    nSize := SIZEOF(x));",
        ]
        out = _normalize_call_param_indent(lines, call_indent=8)
        assert out[0] == "    _fbLogMeasurements.AddField("
        assert out[1].startswith("            pValue")
        assert out[2].startswith("            nSize")

    def test_array_element_method_indent(self):
        """Regression: ``arr[i].Method(`` must get multiline_indent like plain calls."""
        lines = [
            "        _arrLogZone[_nZoneIdx].AddField(",
            "        pValue    := ADR(st.bVal),",
            "        nSize     := SIZEOF(st.bVal),",
            "        ePlcType  := E_Type.eBool,",
            "        eType     := E_Field.eBoolean,",
            "        sKey      := Param.csKey,",
            "        eLogMode  := E_Mode.eOnChange,",
            "        tMin      := T#0S,",
            "        tMax      := T#0S,",
            "        fDeadband := 0.0,",
            "        pValid    := 0);",
        ]
        out = _normalize_call_param_indent(lines, call_indent=8)
        assert out[0] == "        _arrLogZone[_nZoneIdx].AddField("
        for line in out[1:]:
            assert line.startswith("                "), repr(line)

    @pytest.mark.parametrize(
        "opener",
        [
            "    foo.bar[i].baz[j].Meth(",
            "    arr[foo[1]].Meth(",
            "    arr[i][j].Meth(",
            "    THIS^.Meth(",
            "    pFb^.Meth(",
            "    result := arr[i].Meth(",
        ],
    )
    def test_mixed_designator_forms_indent(self, opener: str):
        lines = [
            opener,
            "    a := 1,",
            "    b := 2);",
        ]
        out = _normalize_call_param_indent(lines, call_indent=8)
        indent = opener[: len(opener) - len(opener.lstrip())]
        expected = indent + " " * 8
        assert out[1].startswith(expected)
        assert out[2].startswith(expected)


# ---------------------------------------------------------------------------
# Single-line wrap
# ---------------------------------------------------------------------------


class TestWrapArrayElementMethodCalls:
    def _five_params(self, callee: str) -> str:
        return (
            f"    {callee}("
            "a := 1, b := 2, c := 3, d := 4, e := 5);"
        )

    @pytest.mark.parametrize(
        "callee",
        [
            "FbCall",
            "fbInst.AddField",
            "_arrLogZone[_nZoneIdx].AddField",
            "foo.bar[i].baz[j].Meth",
            "arr[foo[1]].Meth",
            "arr[i][j].Meth",
            "THIS^.AddField",
            "pFb^.AddField",
        ],
    )
    def test_wraps_all_callee_forms(self, callee: str):
        line = self._five_params(callee)
        split = split_single_line_call(line)
        assert split is not None
        result = wrap_long_lines([line], max_params_single=4, call_indent=8)
        assert len(result) > 1
        assert result[0].strip() == f"{callee}("
        assert result[1].startswith("            a := 1,")
        assert result[-1].rstrip().endswith(");")

    def test_does_not_treat_declaration_fb_ctor_as_statement_call(self):
        line = (
            "    _fb : FB_Foo(a := 1, b := 2, c := 3, d := 4, e := 5);"
        )
        assert split_single_line_call(line) is None
        from formatter.st_line_wrapper import _try_wrap_fb_call
        assert _try_wrap_fb_call(line, max_params=4, call_indent=8) is None


# ---------------------------------------------------------------------------
# Full pipeline regression (RoomControl pattern)
# ---------------------------------------------------------------------------


class TestPipelineArrayMethodCall:
    def test_for_body_array_method_params_indented(self):
        code = (
            "FOR _nZoneIdx := 1 TO 4 DO\n"
            "    _arrLogZone[_nZoneIdx].AddField(\n"
            "    pValue    := ADR(st.bVal),\n"
            "    nSize     := SIZEOF(st.bVal),\n"
            "    ePlcType  := E_Type.eBool,\n"
            "    eType     := E_Field.eBoolean,\n"
            "    sKey      := Param.csKey,\n"
            "    eLogMode  := E_Mode.eOnChange,\n"
            "    tMin      := T#0S,\n"
            "    tMax      := T#0S,\n"
            "    fDeadband := 0.0,\n"
            "    pValid    := 0);\n"
            "END_FOR\n"
        )
        result = _format_st_pipeline(code, load_config()).split("\n")
        opener = next(l for l in result if "AddField(" in l)
        opener_idx = result.index(opener)
        param = result[opener_idx + 1]
        opener_indent = len(opener) - len(opener.lstrip())
        param_indent = len(param) - len(param.lstrip())
        assert param_indent == opener_indent + 8, (
            f"opener={opener!r} param={param!r} "
            f"opener_indent={opener_indent} param_indent={param_indent}"
        )
        assert "pValue" in param
