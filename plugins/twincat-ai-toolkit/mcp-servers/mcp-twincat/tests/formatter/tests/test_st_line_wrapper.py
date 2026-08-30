"""Tests for ST line wrapping."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.st_line_wrapper import wrap_chained_binary_expression, wrap_long_lines


class TestChainedBinaryWrapping:
    def test_wraps_assignment_and_then_chain(self):
        line = (
            "_bCalActive := _bValidRoomCommands AND_THEN _pRoomCommands^.stCalibration.bActive "
            "AND_THEN _pRoomCommands^.stCalibration.bBlindValid AND_THEN "
            "((_pRoomCommands^.stCalibration.eBlindZoneFilter = E_EB_BA_DaylightAutomaticZone.Room) "
            "OR (eDaylightAutomaticZone = _pRoomCommands^.stCalibration.eBlindZoneFilter));"
        )
        result = wrap_chained_binary_expression(line, 230, force=True)
        assert result is not None
        assert len(result) == 4
        assert result[0].endswith("AND_THEN")
        assert result[1].startswith("               _pRoomCommands")

    def test_wraps_if_and_then_chain(self):
        line = (
            "IF _bPathReady AND_THEN (_sKeyMem = sKey) AND_THEN (_sDisplayNameMem = sDisplayName) "
            "AND_THEN (_sKeyPrefixMem = _sKeyPrefix) AND_THEN (_sDisplayNamePrefixMem = _sDisplayNamePrefix) "
            "AND_THEN (_bExcludeFromFullPathMem = bExcludeFromFullPath)"
        )
        result = wrap_chained_binary_expression(line, 230, force=True)
        assert result is not None
        assert len(result) == 6
        assert result[0] == "IF _bPathReady AND_THEN"
        assert result[1] == "   (_sKeyMem = sKey) AND_THEN"

    def test_short_chain_not_wrapped_without_force(self):
        line = "x := a AND_THEN b AND_THEN c;"
        assert wrap_chained_binary_expression(line, 230) is None


class TestFbCallWrapping:
    def test_wraps_when_exceeds_param_limit(self):
        line = "FbCall(a := 1, b := 2, c := 3, d := 4, e := 5);"
        result = wrap_long_lines([line], max_params_single=4)
        assert len(result) > 1
        assert result[0].strip() == "FbCall("
        assert result[-1].strip().endswith(");")

    def test_no_wrap_under_limit(self):
        line = "FbCall(a := 1, b := 2);"
        result = wrap_long_lines([line], max_params_single=4)
        assert len(result) == 1

    def test_multiline_indent_is_8(self):
        line = "FbCall(a := 1, b := 2, c := 3, d := 4, e := 5);"
        result = wrap_long_lines([line], max_params_single=4, call_indent=8)
        for param_line in result[1:]:
            leading = len(param_line) - len(param_line.lstrip())
            assert leading == 8


class TestLongLineWrapping:
    def test_wraps_at_operator(self):
        line = "x := " + " AND ".join([f"condition{i}" for i in range(20)])
        result = wrap_long_lines([line], max_length=80)
        assert len(result) > 1
        assert all(len(l) <= 80 or "AND" not in l for l in result)

    def test_short_lines_unchanged(self):
        lines = ["x := 1;", "y := 2;"]
        result = wrap_long_lines(lines, max_length=200)
        assert result == lines
