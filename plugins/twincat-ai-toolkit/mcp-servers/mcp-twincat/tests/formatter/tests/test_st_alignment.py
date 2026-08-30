"""Tests for ST alignment logic."""
import re
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.st_alignment import (
    align_declarations,
    align_assignments,
    align_fb_call_params,
    align_for_body_assignments,
    _align_enum_members,
    _is_enum_member_line,
    _split_decl_name_address,
)


class TestAlignDeclarations:
    def test_aligns_colons(self):
        lines = [
            "VAR",
            "    b : BOOL;",
            "    nLongName : INT;",
            "    f : REAL;",
            "END_VAR",
        ]
        result = align_declarations(lines)
        colon_positions = [line.index(":") for line in result if ":" in line and "VAR" not in line.upper()]
        assert len(set(colon_positions)) == 1

    def test_preserves_var_keywords(self):
        lines = ["VAR_INPUT", "    x : INT;", "END_VAR"]
        result = align_declarations(lines)
        assert result[0] == "VAR_INPUT"
        assert result[-1] == "END_VAR"

    def test_handles_init_values(self):
        lines = [
            "VAR",
            "    bEnable : BOOL := TRUE;",
            "    nCount : INT := 0;",
            "END_VAR",
        ]
        result = align_declarations(lines)
        assert ":=" in result[1]
        assert ":=" in result[2]


class TestAlignAssignments:
    def test_aligns_assign_group(self):
        lines = [
            "    x := 1;",
            "    longVarName := 2;",
            "    y := 3;",
        ]
        result = align_assignments(lines)
        positions = [line.index(":=") for line in result]
        assert len(set(positions)) == 1

    def test_single_assignment_not_aligned(self):
        lines = ["    x := 1;", "    IF y THEN", "END_IF"]
        result = align_assignments(lines)
        assert result == lines


class TestAlignFbCallParams:
    def test_aligns_call_params(self):
        lines = [
            "FbCall(",
            "        param1 := val1,",
            "        longParam := val2,",
            "        p := val3);",
        ]
        result = align_fb_call_params(lines)
        assign_positions = [line.index(":=") for line in result[1:]]
        assert len(set(assign_positions)) == 1

    def test_aligns_if_wrapped_call_params(self):
        lines = [
            "IF FindAndSplit(",
            "        pSeparator := ADR(csSepId),",
            "        pSrcString       := ADR(sInString),",
            "        pLeftString := ADR(_sBuffer),",
            "        bSearchFromRight := FALSE)",
            "THEN",
        ]
        result = align_fb_call_params(lines)
        positions = [line.index(":=") for line in result[1:4]]
        assert len(set(positions)) == 1
        assert result[4].endswith("FALSE)")
        assert result[5] == "THEN"

    def test_aligns_if_not_method_call_params(self):
        lines = [
            "IF NOT THIS^._ReadPlc(",
            "        nIdx    := nIdx,",
            "        bBool => bBool,",
            "        fLreal => fLreal,",
            "        nLint => nLint,",
            "        nUlint => nUlint,",
            "        nCrc => nCrc,",
            "        nStrLen => nLen)",
            "THEN",
        ]
        result = align_fb_call_params(lines)
        op_cols = []
        for line in result[1:8]:
            if ":=" in line:
                op_cols.append(line.index(":="))
            else:
                op_cols.append(line.index("=>"))
        assert len(set(op_cols)) == 1
        assert result[8] == "THEN"

    def test_aligns_if_not_concat2_multiline(self):
        lines = [
            "IF NOT concat2(",
            "        ADR(sStr1),",
            "        ADR(sStr2),",
            "        ADR(sResult),",
            "        SIZEOF(sResult))",
            "THEN",
        ]
        result = align_fb_call_params(lines)
        adr_cols = [line.index("ADR") for line in result[1:4]]
        assert len(set(adr_cols)) == 1
        assert result[5] == "THEN"

    def test_aligns_if_not_isvalidref_multiline(self):
        lines = [
            "IF NOT __ISVALIDREF(",
            "        rTarget)",
            "THEN",
        ]
        result = align_fb_call_params(lines)
        assert result[2] == "THEN"

    def test_aligns_nested_formatstring_in_message_log_else(self):
        """EB_BA DALI pattern: MessageLog(… sArg1 := FormatString_3(…) …) in ELSE."""
        lines = [
            "        ELSE",
            "            F_IoT_Utilities_MessageLog(",
            "                    eMode := Param_EB_BA.ceMessageLog,",
            "                    eMask := E_IoT_Utilities_MessageLog.Debug,",
            "                    sFmt  := '_fbDaliPowerOff %s',",
            "                    sPath := _sPath,",
            "                    sArg1 := F_IoT_Utilities_FormatString_3(",
            "                            sFormat := 'nAddress:%s eAddressType:%s Value:%s',",
            "                            arg1    := BYTE_TO_STRING(_fbDaliPowerOff.nAddress),",
            "                            arg2    := BYTE_TO_STRING(_fbDaliPowerOff.eAddressType),",
            "                            arg3    := TO_STRING(_tCalcSafetyOff)),",
            "                    sArg2 := '');",
        ]
        result = align_fb_call_params(lines)
        outer_ops = []
        inner_ops = []
        in_inner = False
        for line in result[2:]:
            if "FormatString_3(" in line and ":=" not in line.split("FormatString_3(")[0]:
                in_inner = True
            if ":=" in line:
                col = line.index(":=")
                if in_inner and "sArg1" not in line:
                    inner_ops.append(col)
                elif "sArg1" in line:
                    in_inner = True
                else:
                    outer_ops.append(col)
            if line.rstrip().endswith(")),"):
                in_inner = False
        assert len(set(outer_ops)) == 1
        assert len(set(inner_ops)) == 1

    def test_aligns_struct_init_fields(self):
        lines = [
            "\t(\tsDisplayName := 'N',",
            "\t\tbEnable := FALSE,",
            "\t\teFacade := E_North,",
            "\t)",
        ]
        result = align_fb_call_params(lines)
        positions = [line.index(":=") for line in result[1:3]]
        assert len(set(positions)) == 1


class TestAlignForBodyAssignments:
    def test_does_not_merge_runs_across_non_assign_barrier(self):
        lines = [
            "FOR i := 1 TO 3 DO",
            "    a := 1;",
            "    b := 2;",
            "    c := 3;",
            "    SomeCall();",
            "    x := 4;",
            "    longName := 5;",
            "    y := 6;",
            "END_FOR",
        ]
        result = align_for_body_assignments(lines, indent_size=4, max_spread=12)
        assert result[1] == "    a := 1;"
        assert result[2] == "    b := 2;"
        assert result[3] == "    c := 3;"


class TestAlignEnumMembers:
    """Enum member alignment: decimal, 2#, 16#, pragmas, expressions."""

    @staticmethod
    def _enum_members(*member_lines: str) -> list[str]:
        block = ["TYPE E_Test : (", *member_lines, ") INT;", "END_TYPE"]
        result = align_declarations(block)
        return result[1:-2]

    def test_decimal_literals_align_assign(self):
        result = self._enum_members("    Low := 0,", "    High := 255,")
        positions = [line.index(":=") for line in result]
        assert len(set(positions)) == 1

    def test_binary_2hash_literals(self):
        result = self._enum_members(
            "    BitA := 2#0000_0001,",
            "    BitB := 2#10,",
        )
        assert "2#0000_0001" in result[0]
        assert "2#10" in result[1]
        positions = [line.index(":=") for line in result]
        assert len(set(positions)) == 1

    def test_hex_16hash_literals(self):
        result = self._enum_members(
            "    MaskA := 16#FF,",
            "    MaskB := 16#00,",
        )
        assert "16#FF" in result[0]
        assert "16#00" in result[1]
        positions = [line.index(":=") for line in result]
        assert len(set(positions)) == 1

    def test_mixed_radix_literals(self):
        result = self._enum_members(
            "    Dec := 0,",
            "    Bin := 2#01,",
            "    Hex := 16#A,",
        )
        positions = [line.index(":=") for line in result]
        assert len(set(positions)) == 1

    def test_pragma_on_member_preserved(self):
        result = self._enum_members(
            "    {attribute 'hide'} Hidden := 0,",
            "    Visible := 1,",
        )
        assert "{attribute 'hide'}" in result[0]
        assert "Hidden" in result[0]
        assert ":= 0," in result[0]
        assert "Visible := 1," in result[1]

    def test_expression_member_aligns(self):
        result = self._enum_members(
            "    BitA := 2#01,",
            "    Both := BitA + BitB,",
        )
        assert "BitA + BitB" in result[1]
        positions = [line.index(":=") for line in result]
        assert len(set(positions)) == 1

    def test_single_member_with_comment_one_space(self):
        block = [
            "TYPE E_Test : (",
            "    All (* everything *)",
            ") INT;",
            "END_TYPE",
        ]
        result = align_declarations(block)
        assert result[1].endswith("All (* everything *)")

    def test_is_enum_member_excludes_statement_assign(self):
        assert not _is_enum_member_line("    x := 1;")

    def test_align_enum_members_direct(self):
        block = [
            "TYPE E_Flags : (",
            "    A := 16#01,",
            "    LongName := 2#10,",
            "    ) INT;",
        ]
        aligned = _align_enum_members(block)
        assert aligned[1].index(":=") == aligned[2].index(":=")


class TestAlignAddressAssignments:
    def test_split_decl_name_address(self):
        base, addr = _split_decl_name_address("bOutput AT %Q*")
        assert base == "bOutput"
        assert addr == "AT %Q*"

    def test_aligns_at_i_and_q_addresses(self):
        lines = [
            "VAR",
            "    nInput AT %I0 : INT;",
            "    nInput2 AT %I2 : DINT;",
            "    bOutput AT %Q0.0 : BOOL;",
            "END_VAR",
        ]
        result = align_declarations(lines, align_address_assignments=True)
        at_positions = [line.index("AT") for line in result[1:-1]]
        colon_positions = [line.index(" : ") for line in result[1:-1]]
        assert len(set(at_positions)) == 1
        assert len(set(colon_positions)) == 1

    def test_mixed_at_and_plain_declarations(self):
        lines = [
            "VAR",
            "    bOut AT %Q* : BOOL;",
            "    nValue : INT;",
            "END_VAR",
        ]
        result = align_declarations(lines, align_address_assignments=True)
        assert "AT %Q*" in result[1]
        colon_positions = [line.index(" : ") for line in result[1:-1]]
        assert len(set(colon_positions)) == 1

    def test_disabled_skips_address_column_align(self):
        lines = [
            "VAR",
            "    a AT %I0 : INT;",
            "    bb AT %I2 : INT;",
            "END_VAR",
        ]
        on = align_declarations(lines, align_address_assignments=True)
        off = align_declarations(lines, align_address_assignments=False)
        assert on[1].index("AT") == on[2].index("AT")
        assert off != on


class TestSplitInlineEnumMembers:

    def test_splits_when_over_member_limit(self):
        from formatter.st_alignment import split_inline_enum_members

        lines = [
            "TYPE E_Test : (",
            "    A := 0, B := 1, C := 2, D := 3, E := 4, F := 5, G := 6",
            ") INT;",
            "END_TYPE",
        ]
        result = split_inline_enum_members(lines, max_members_per_line=5)
        assert len(result) == 10
        assert result[1].strip() == "A := 0"
        assert result[7].strip() == "G := 6"

    def test_keeps_short_inline_line(self):
        from formatter.st_alignment import split_inline_enum_members

        lines = [
            "TYPE E_Test : (",
            "    A := 0, B := 1",
            ") INT;",
            "END_TYPE",
        ]
        result = split_inline_enum_members(lines, max_members_per_line=5)
        assert result[1] == "    A := 0, B := 1"


class TestAlignArrayStructInits:

    def test_array_of_struct_separator_and_fields(self):
        from formatter.file_processor import _format_st_pipeline
        from formatter.config import load_config

        code = (
            "VAR_GLOBAL\n"
            "    stCfg : ST_Cfg := (\n"
            "            arrFacade := [(\n"
            "                        a := 1, (* c1 *)\n"
            "                        bb := 2 (* c2 *)\n"
            "                              ),\n"
            "                          (\n"
            "                        a := 3,\n"
            "                        bb := 4\n"
            "                              )]);\n"
            "END_VAR"
        )
        result = _format_st_pipeline(code, load_config()).split("\n")
        assert any(l.strip() == "), (" for l in result)
        assert not any(re.match(r"^\s+\),\s*$", l) for l in result)
        field_lines = [
            l for l in result
            if re.search(r"^\s{12,}\w+\s*:=", l) and "arrFacade" not in l
        ]
        assert len(field_lines) >= 4
        assign_cols = {l.index(":=") for l in field_lines}
        assert len(assign_cols) == 1
