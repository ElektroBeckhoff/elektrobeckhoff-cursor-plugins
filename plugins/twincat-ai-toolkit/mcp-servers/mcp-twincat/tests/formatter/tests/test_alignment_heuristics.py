"""Unit tests for alignment heuristics (AlignmentHeuristicsConfig).

Tests guarded alignment rules:
- split_case_inline_statements and numeric/enum label handling
- blank_after_assign_before_comment
- align_for_body_assignments (contiguous runs, bool literal guard)
- compact_orphan_overpadded_assigns (gap handling, string literals, OR/AND chains)
- compact_same_col_outlier_assigns
- clean CASE branch splitting and orphan normalization
"""
from __future__ import annotations

import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_MCP_ROOT))

from formatter.config import load_config
from formatter.file_processor import _format_st_segment, _insert_blank_lines_after_assign, _split_case_inline_statements
from formatter.st_alignment import (
    align_assignments,
    align_chained_init_assignments,
    align_for_body_assignments,
    align_pre_chained_true_orphans,
    align_ref_to_preceding_assign,
    compact_orphan_overpadded_assigns,
    compact_same_col_outlier_assigns,
    normalize_case_arm_single_assignments,
)
from formatter.st_statement_normalize import _split_line_statements


class TestSplitCaseNumericLabels:
    """split_case_inline_statements + split_case_numeric_labels_only."""

    def test_splits_inline_numeric_case_arm(self):
        source = [
            "CASE nIdx OF",
            "    0: ZoneIdxToEnum := E_EB_BA_DaylightAutomaticZone.Room;",
            "    1: ZoneIdxToEnum := E_EB_BA_DaylightAutomaticZone.Zone_01;",
            "ELSE",
            "    ZoneIdxToEnum := E_EB_BA_DaylightAutomaticZone.Room;",
            "END_CASE",
        ]
        expected = [
            "CASE nIdx OF",
            "    0:",
            "        ZoneIdxToEnum := E_EB_BA_DaylightAutomaticZone.Room;",
            "    1:",
            "        ZoneIdxToEnum := E_EB_BA_DaylightAutomaticZone.Zone_01;",
            "ELSE",
            "    ZoneIdxToEnum := E_EB_BA_DaylightAutomaticZone.Room;",
            "END_CASE",
        ]
        result = _split_case_inline_statements(source, 4, numeric_labels_only=True)
        assert result == expected

    def test_keeps_enum_label_on_one_line(self):
        source = [
            "CASE eStep OF",
            "    E_EB_BA_LightDaylightDeskBrightnessCalibrationStep.Idle:",
            "        _sStepText := 'Bereit';",
            "END_CASE",
        ]
        result = _split_case_inline_statements(source, 4, numeric_labels_only=True)
        assert result == source

    def test_keeps_else_inline_block_comment(self):
        source = [
            "CASE x OF",
            "    1:",
            "        y := 1;",
            "ELSE (* fallback *)",
            "    y := 0;",
            "END_CASE",
        ]
        result = _split_case_inline_statements(
            source, 4, numeric_labels_only=True, keep_else_inline_comment=True,
        )
        assert result == source


class TestBlankAfterAssignBeforeComment:
    """blank_after_assign_before_comment — only when comment precedes IF."""

    def test_inserts_blank_before_case_arm_comment_followed_by_if(self):
        source = [
            "    E_EB_BA_LightDaylightDeskBrightnessCalibrationStep.Commit:",
            "        _stWorking.bValid := TRUE;",
            "        (* Working params ready — InOut written only after Verify pass *)",
            "        IF stConfig.bSkipVerify THEN",
            "            bVerifyPass := TRUE;",
            "        END_IF",
        ]
        expected = [
            "    E_EB_BA_LightDaylightDeskBrightnessCalibrationStep.Commit:",
            "        _stWorking.bValid := TRUE;",
            "",
            "        (* Working params ready — InOut written only after Verify pass *)",
            "        IF stConfig.bSkipVerify THEN",
            "            bVerifyPass := TRUE;",
            "        END_IF",
        ]
        result = _insert_blank_lines_after_assign(
            source,
            before_comment=True,
            before_for=False,
            before_related_if=False,
            after_end_if=False,
        )
        assert result == expected

    def test_skips_blank_when_comment_not_before_if(self):
        source = [
            "        _stWorking.bValid := TRUE;",
            "        (* section marker only *)",
            "        bError := FALSE;",
        ]
        result = _insert_blank_lines_after_assign(
            source,
            before_comment=True,
            before_for=False,
            before_related_if=False,
            after_end_if=False,
        )
        assert result == source


class TestAlignForBodyContiguousRuns:
    """align_for_body_assignments — contiguous runs, bool-literal guard."""

    def test_skips_bool_literal_run_separated_by_call(self):
        source = [
            "FOR _nIdx := 1 TO _nCount DO",
            "    _bRegDiff  := FALSE;",
            "    _bCctDiff  := FALSE;",
            "    _bGateDiff := FALSE;",
            "    M_DaylightSectionDiffs(nIndex := _nIdx);",
            "    _bDaylightDiffers                  := _bRegDiff OR _bCctDiff;",
            "    stStatus.arrDaylightDiffers[_nIdx] := _bDaylightDiffers;",
            "END_FOR",
        ]
        result = align_for_body_assignments(source, indent_size=4)
        assert result == source

    def test_aligns_long_rhs_run_across_if_barrier(self):
        source = [
            "FOR nZ := 1 TO 3 DO",
            "    IF NOT stSlot.arrArtPerZone[nZ].bValid THEN",
            "        CONTINUE;",
            "    END_IF",
            "    fZoneLevel := GetAllZoneLightMean(nZone := nZ);",
            "    fArtDesk   := fArtDesk + F_EB_BA_InterpolateLinear1D(fX := fZoneLevel);",
            "    fArtCeil   := fArtCeil + F_EB_BA_InterpolateLinear1D(fX := fZoneLevel);",
            "END_FOR",
        ]
        result = align_for_body_assignments(source, indent_size=4)
        assign_lines = [line for line in result if ":=" in line and "FOR" not in line.upper()]
        positions = [line.index(":=") for line in assign_lines]
        assert len(set(positions)) == 1


class TestCompactOrphanBooleanRhs:
    """compact_orphan — preserve padding when RHS is OR/AND chain."""

    def test_preserves_or_chain_padding(self):
        source = [
            "    _bDaylightDiffers                  := _bRegDiff OR _bCctDiff OR _bGateDiff;",
        ]
        result = compact_orphan_overpadded_assigns(
            source,
            min_gap=3,
            max_gap=13,
            simple_identifier_only=True,
            expression_rhs_max_gap=13,
        )
        assert result == source


class TestCompactSameColOutlier:
    """compact_same_col_outlier — guarded, disabled globally in defaults.json."""

    def test_compacts_shorter_lhs_at_shared_column(self):
        assign_col = 40
        padded = [
            "    fArtDesk" + " " * (assign_col - 8) + ":= 0.0;",
            "    fArtCeil" + " " * (assign_col - 8) + ":= 0.0;",
            "    fZoneLevelLongName" + " " * (assign_col - 18) + ":= GetAllZoneLightMean(nZone := nZ);",
        ]
        result = compact_same_col_outlier_assigns(padded, min_gap=8)
        assert result[0] == "    fArtDesk := 0.0;"
        assert result[1] == "    fArtCeil := 0.0;"
        assert "fZoneLevelLongName" in result[2]

    def test_disabled_in_defaults(self):
        config = load_config()
        assert config.alignment_heuristics.compact_same_col_outlier_enabled is False


class TestCleanCaseArmAndOrphanNormalization:
    """Tests for clean CASE branch splitting and orphan assignment normalization."""

    def test_splits_inline_case_arms_with_tabular_padding(self):
        source = [
            "CASE eErrorId OF",
            "    0: sReturn                 := 'BUSY';",
            "    1: sReturn      := 'CREATE_PROTOCOL';",
            "    2: sReturn           := 'CONN_INVAL';",
            "    3: sReturn := 'OK';",
            "END_CASE",
        ]
        result = _split_case_inline_statements(source, 4, numeric_labels_only=True)
        expected = [
            "CASE eErrorId OF",
            "    0:",
            "        sReturn := 'BUSY';",
            "    1:",
            "        sReturn := 'CREATE_PROTOCOL';",
            "    2:",
            "        sReturn := 'CONN_INVAL';",
            "    3:",
            "        sReturn := 'OK';",
            "END_CASE",
        ]
        assert result == expected

    def test_normalize_split_line_statements_in_case(self):
        line = "    ETcIotHttpRequestError.HTTP_REQ_ERR_BUSY: sReturn                 := 'BUSY';"
        result_lines, case_depth, depth, decl_paren = _split_line_statements(line, initial_case_depth=1)
        assert case_depth == 1
        assert len(result_lines) == 2
        assert result_lines[0] == "    ETcIotHttpRequestError.HTTP_REQ_ERR_BUSY:"
        assert result_lines[1] == "    sReturn := 'BUSY';"

    def test_compact_orphan_large_gap_string_and_expr(self):
        source = [
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_BUSY:",
            "        sReturn                 := 'BUSY';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_NOMEM:",
            "        sReturn              := 'NOMEM';",
        ]
        result = compact_orphan_overpadded_assigns(
            source,
            min_gap=3,
            max_gap=0,
            simple_identifier_only=True,
            expression_rhs_max_gap=0,
            expression_rhs_min_gap_floor=10,
        )
        assert result[1] == "        sReturn := 'BUSY';"
        assert result[3] == "        sReturn := 'NOMEM';"

    def test_full_pipeline_case_error_to_string_clean(self):
        cfg = load_config()
        st_code = """CASE eErrorId OF
    ETcIotHttpRequestError.HTTP_REQ_ERR_BUSY: sReturn                 := 'BUSY';
    ETcIotHttpRequestError.HTTP_REQ_ERR_NOMEM: sReturn                := 'NOMEM';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CREATE_PROTOCOL: sReturn      := 'CREATE_PROTOCOL';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_INVAL: sReturn           := 'CONN_INVAL';
    ETcIotHttpRequestError.HTTP_REQ_ERR_NO_CONN: sReturn              := 'NO_CONN';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS: sReturn                  := 'TLS';
ELSE
    sReturn := 'UNKNOWN';
END_CASE"""
        formatted = _format_st_segment(st_code, cfg)
        expected_lines = [
            "CASE eErrorId OF",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_BUSY:",
            "        sReturn := 'BUSY';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_NOMEM:",
            "        sReturn := 'NOMEM';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_CREATE_PROTOCOL:",
            "        sReturn := 'CREATE_PROTOCOL';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_INVAL:",
            "        sReturn := 'CONN_INVAL';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_NO_CONN:",
            "        sReturn := 'NO_CONN';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS:",
            "        sReturn := 'TLS';",
            "ELSE",
            "    sReturn := 'UNKNOWN';",
            "END_CASE",
        ]
        assert formatted.splitlines() == expected_lines


class TestInitMethodChainedAlignments:
    """Tests for chained init-method alignment heuristics."""

    def test_align_chained_followers(self):
        source = [
            "    Init := _bInitDone := FALSE;",
            "    _sName := sName;",
            "    _nCount := nCount;",
        ]
        result = align_chained_init_assignments(source)
        assert result == [
            "    Init := _bInitDone := FALSE;",
            "    _sName             := sName;",
            "    _nCount            := nCount;",
        ]

    def test_align_pre_chained_true_orphans(self):
        source = [
            "    _sName := sName;",
            "    Init   := _bInitDone := TRUE;",
        ]
        result = align_pre_chained_true_orphans(source)
        assert result == [
            "    _sName               := sName;",
            "    Init   := _bInitDone := TRUE;",
        ]

    def test_align_ref_to_preceding_assign(self):
        source = [
            "    _pData := ADR(stConfig);",
            "    _refData REF= stConfig;",
        ]
        result = align_ref_to_preceding_assign(source)
        assert result == [
            "    _pData := ADR(stConfig);",
            "    _refData REF= stConfig;",
        ]

    def test_nested_if_chained_scope_isolation(self):
        source = [
            "    Init := _bValid := FALSE;",
            "    IF bCondition THEN",
            "        _nInner := 1;",
            "    END_IF",
            "    _sOuter := sName;",
        ]
        result = align_chained_init_assignments(source)
        assert result == [
            "    Init := _bValid := FALSE;",
            "    IF bCondition THEN",
            "        _nInner := 1;",
            "    END_IF",
            "    _sOuter := sName;",
        ]


class TestBlankLineInsertionHeuristics:
    """Tests for blank line insertion after assignments / END_IF."""

    def test_blank_after_assign_before_for(self):
        source = [
            "    nCount := 10;",
            "    FOR nIdx := 1 TO nCount DO",
            "        nSum := nSum + nIdx;",
            "    END_FOR",
        ]
        result = _insert_blank_lines_after_assign(source, before_for=True)
        assert result == [
            "    nCount := 10;",
            "",
            "    FOR nIdx := 1 TO nCount DO",
            "        nSum := nSum + nIdx;",
            "    END_FOR",
        ]

    def test_blank_after_assign_before_related_if(self):
        source = [
            "    bReady := TRUE;",
            "    IF bReady THEN",
            "        DoWork();",
            "    END_IF",
        ]
        result = _insert_blank_lines_after_assign(source, before_related_if=True)
        assert result == [
            "    bReady := TRUE;",
            "",
            "    IF bReady THEN",
            "        DoWork();",
            "    END_IF",
        ]

    def test_skip_related_if_when_rhs_contains_paren(self):
        source = [
            "    bFlag := Check(1);",
            "    IF bFlag THEN",
            "        DoWork();",
            "    END_IF",
        ]
        result = _insert_blank_lines_after_assign(
            source,
            before_related_if=True,
            skip_related_if_when_rhs_contains_paren=True,
        )
        assert result == source

    def test_blank_after_end_if_before_statement(self):
        source = [
            "    IF bCond THEN",
            "        DoSomething();",
            "    END_IF",
            "    nNextStep := 10;",
        ]
        result = _insert_blank_lines_after_assign(source, after_end_if=True)
        assert result == [
            "    IF bCond THEN",
            "        DoSomething();",
            "    END_IF",
            "",
            "    nNextStep := 10;",
        ]


class TestBoolLiteralGroupSpreadGuard:
    """Tests for bool literal group alignment and name spread guards."""

    def test_tight_bool_literal_group_preserved(self):
        source = [
            "    bA  := TRUE;",
            "    bBB := FALSE;",
            "    bC  := TRUE;",
        ]
        result = align_assignments(
            source,
            bool_literal_min_group_lines=3,
            bool_literal_name_spread_max=2,
        )
        assert result == source

    def test_wider_bool_spread_aligns_normally(self):
        source = [
            "    bAlarm := TRUE;",
            "    bActiveState := FALSE;",
            "    bRunning := TRUE;",
        ]
        result = align_assignments(source)
        assert result == [
            "    bAlarm       := TRUE;",
            "    bActiveState := FALSE;",
            "    bRunning     := TRUE;",
        ]


class TestCaseLabelVariationsAndNesting:
    """Tests for diverse CASE label variants and nested CASE structures."""

    def test_negative_numeric_label_split(self):
        cfg = load_config()
        st_code = """CASE nState OF
    -1: sDesc := 'FAULT_NEGATIVE';
    0: sDesc := 'IDLE';
    1: sDesc := 'RUNNING';
END_CASE"""
        formatted = _format_st_segment(st_code, cfg)
        expected = [
            "CASE nState OF",
            "    -1:",
            "        sDesc := 'FAULT_NEGATIVE';",
            "    0:",
            "        sDesc := 'IDLE';",
            "    1:",
            "        sDesc := 'RUNNING';",
            "END_CASE",
        ]
        assert formatted.splitlines() == expected

    def test_nested_case_clean_formatting(self):
        cfg = load_config()
        st_code = """CASE nOuter OF
    0:
        CASE nInner OF
            1: nVal := 10;
            2: nVal := 20;
        END_CASE
    1:
        nVal := 30;
END_CASE"""
        formatted = _format_st_segment(st_code, cfg)
        expected = [
            "CASE nOuter OF",
            "    0:",
            "        CASE nInner OF",
            "            1:",
            "                nVal := 10;",
            "            2:",
            "                nVal := 20;",
            "        END_CASE",
            "    1:",
            "        nVal := 30;",
            "END_CASE",
        ]
        assert formatted.splitlines() == expected


class TestUniversalOrphanCompaction:
    """Tests for universal orphan assignment compaction across all literal and expression kinds."""

    def test_compact_orphan_all_literal_types(self):
        source = [
            "    sStr            := 'Hello';",
            "",
            "    nNum            := 12345;",
            "",
            "    bBool           := TRUE;",
            "",
            "    fCall           := CalculateMean(1, 2);",
        ]
        result = compact_orphan_overpadded_assigns(
            source,
            min_gap=3,
            max_gap=0,
            simple_identifier_only=True,
            expression_rhs_max_gap=0,
            expression_rhs_min_gap_floor=10,
        )
        assert result == [
            "    sStr := 'Hello';",
            "",
            "    nNum := 12345;",
            "",
            "    bBool := TRUE;",
            "",
            "    fCall := CalculateMean(1, 2);",
        ]


class TestCaseArmSingleAssignmentNormalization:
    """Tests for normalize_case_arm_single_assignments heuristic."""

    def test_normalize_case_arm_single_assignments_direct(self):
        source = [
            "CASE eErrorId OF",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_CREATE_PROTOCOL:",
            "        sReturn      := 'CREATE_PROTOCOL';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_REFUSED:",
            "        sReturn         := 'CONN_REFUSED';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_VERSION_INVALID:",
            "        sReturn  := 'TLS_VERSION_INVALID';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_BIND_ADDR_INUSE:",
            "        sReturn      := 'BIND_ADDR_INUSE';",
            "ELSE",
            "    sReturn := 'undefined';",
            "END_CASE",
        ]
        result = normalize_case_arm_single_assignments(source)
        assert result == [
            "CASE eErrorId OF",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_CREATE_PROTOCOL:",
            "        sReturn := 'CREATE_PROTOCOL';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_REFUSED:",
            "        sReturn := 'CONN_REFUSED';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_VERSION_INVALID:",
            "        sReturn := 'TLS_VERSION_INVALID';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_BIND_ADDR_INUSE:",
            "        sReturn := 'BIND_ADDR_INUSE';",
            "ELSE",
            "    sReturn := 'undefined';",
            "END_CASE",
        ]

    def test_case_arm_multi_assignment_preserves_aligned_block(self):
        source = [
            "CASE nStep OF",
            "    10:",
            "        a   := 1;",
            "        foo := 2;",
            "    20:",
            "        sReturn       := 'ONLY_ONE';",
            "END_CASE",
        ]
        result = normalize_case_arm_single_assignments(source)
        # Multi-assignment arm 10 should keep its group lines intact, single-arm 20 normalizes
        assert result == [
            "CASE nStep OF",
            "    10:",
            "        a   := 1;",
            "        foo := 2;",
            "    20:",
            "        sReturn := 'ONLY_ONE';",
            "END_CASE",
        ]

    def test_full_pipeline_enum_case_multiline_formatting(self):
        cfg = load_config()
        st_code = """CASE eErrorId OF
    ETcIotHttpRequestError.HTTP_REQ_ERR_CREATE_PROTOCOL:
        sReturn      := 'CREATE_PROTOCOL';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_INVAL:
        sReturn := 'CONN_INVAL';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_REFUSED:
        sReturn         := 'CONN_REFUSED';
ELSE
    sReturn := 'undefined';
END_CASE"""
        formatted = _format_st_segment(st_code, cfg)
        expected = [
            "CASE eErrorId OF",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_CREATE_PROTOCOL:",
            "        sReturn := 'CREATE_PROTOCOL';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_INVAL:",
            "        sReturn := 'CONN_INVAL';",
            "    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_REFUSED:",
            "        sReturn := 'CONN_REFUSED';",
            "ELSE",
            "    sReturn := 'undefined';",
            "END_CASE",
        ]
        assert formatted.splitlines() == expected


