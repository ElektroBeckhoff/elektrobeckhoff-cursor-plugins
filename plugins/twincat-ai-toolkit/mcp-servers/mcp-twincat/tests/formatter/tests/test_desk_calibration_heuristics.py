"""Golden unit tests for DeskCalibration-driven alignment heuristics.

Each test pins one guarded rule with a minimal snippet derived from
FB_EB_BA_LightDaylightDeskBrightnessCalibration / FB_EB_BA_RoomConfigSync.
"""
from __future__ import annotations

import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_MCP_ROOT))

from formatter.file_processor import _insert_blank_lines_after_assign, _split_case_inline_statements
from formatter.st_alignment import (
    align_for_body_assignments,
    compact_orphan_overpadded_assigns,
    compact_same_col_outlier_assigns,
)


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
        from formatter.config import load_config

        config = load_config()
        assert config.alignment_heuristics.compact_same_col_outlier_enabled is False
