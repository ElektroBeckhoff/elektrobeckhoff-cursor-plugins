"""Test every config setting individually.

Verifies that:
1. Each setting loads correctly from defaults.json
2. Each setting can be overridden
3. The formatter respects each setting's behavior
"""
import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_MCP_ROOT))

import json
from formatter.config import (
    FormatterConfig, load_config, config_to_dict, _dict_to_config,
    IndentConfig, LineLengthConfig, BlankLinesConfig, SpacesConfig,
    AlignmentConfig, AlignMultilineConfig, AlignmentHeuristicsConfig, LineBreaksConfig, CallsConfig,
    ParenthesesConfig, KeywordsConfig, XmlConfig, ValidationConfig, SafetyConfig,
)
from formatter.st_formatter import format_st_code
from formatter.st_alignment import align_declarations, align_assignments, align_fb_call_params
from formatter.st_line_wrapper import wrap_long_lines


def test_config_loading():
    """Test that defaults.json loads all settings correctly."""
    config = load_config()
    d = config_to_dict(config)

    # Verify all defaults
    assert config.indent.size == 4, f"indent.size={config.indent.size}"
    assert config.indent.style == "spaces"
    assert config.indent.indent_cases_in_case is True
    assert config.indent.indent_statements_in_case is True
    assert config.indent.indent_else_case is False
    assert config.indent.indent_derived_types is True
    assert config.indent.indent_do_in_for is False
    assert config.indent.indent_then_in_if is False
    assert config.indent.indent_last_comment_before_case is False
    assert config.indent.indent_last_comment_before_else is False
    assert config.indent.continuous_indent_multiplier == 1

    assert config.line_length.wrap_at == 230
    assert config.line_length.wrap_enabled is True
    assert config.line_length.wrap_after_operator is True

    assert config.blank_lines.after_multiline_case == 0
    assert config.blank_lines.after_multiline_comment == 0
    assert config.blank_lines.after_multiline_declaration == 0
    assert config.blank_lines.after_multiline_statement == 0
    assert config.blank_lines.after_singleline_case == 0
    assert config.blank_lines.after_singleline_comment == 0
    assert config.blank_lines.after_singleline_declaration == 0
    assert config.blank_lines.after_singleline_statement == 0
    assert config.blank_lines.after_statement_with_body == 1
    assert config.blank_lines.after_var_blocks == 0
    assert config.blank_lines.at_implementation_end == 1
    assert config.blank_lines.at_implementation_start == 0
    assert config.blank_lines.before_multiline_comment == 0
    assert config.blank_lines.before_multiline_declaration == 0
    assert config.blank_lines.before_multiline_statement == 0
    assert config.blank_lines.before_singleline_comment == 0
    assert config.blank_lines.before_singleline_declaration == 0
    assert config.blank_lines.before_singleline_statement == 0
    assert config.blank_lines.before_statement_with_body == 1
    assert config.blank_lines.max_consecutive == 1

    assert config.spaces.after_comma is True
    assert config.spaces.after_declaration_colon is True
    assert config.spaces.before_declaration_colon is True
    assert config.spaces.around_additive_operator is True
    assert config.spaces.around_assignment_operator is True
    assert config.spaces.around_assignment_in_call is True
    assert config.spaces.around_assignment_in_init is True
    assert config.spaces.around_comment is True
    assert config.spaces.around_comparison_operator is True
    assert config.spaces.around_dot is False
    assert config.spaces.around_equality_operator is True
    assert config.spaces.around_term_operator is True
    assert config.spaces.before_array_brackets is False
    assert config.spaces.before_array_init_brackets is False
    assert config.spaces.before_comma is False
    assert config.spaces.before_fb_init_parens is False
    assert config.spaces.before_invocation_parens is False
    assert config.spaces.before_semicolon is False
    assert config.spaces.before_struct_init_parens is False
    assert config.spaces.before_subrange_parens is False
    assert config.spaces.between_nested_parens is False
    assert config.spaces.inside_array_brackets is False
    assert config.spaces.inside_array_init_brackets is False
    assert config.spaces.inside_expression_parens is False
    assert config.spaces.inside_fb_init_parens is False
    assert config.spaces.inside_invocation_parens is False
    assert config.spaces.inside_struct_init_parens is False
    assert config.spaces.inside_subrange_parens is False
    assert config.spaces.around_pragma is True

    assert config.alignment.declarations is True
    assert config.alignment.assignments is True
    assert config.alignment.fb_call_params is True
    assert config.alignment.comments is True
    assert config.alignment.address_assignments is True
    assert config.alignment.enum_initializers is True

    assert config.align_multiline.array_initializers is True
    assert config.align_multiline.chained_binary is True
    assert config.align_multiline.fb_init_assignments is True
    assert config.align_multiline.fb_init_params is True
    assert config.align_multiline.invocation_params is True
    assert config.align_multiline.invocation_assignments is True
    assert config.align_multiline.struct_init_assignments is True
    assert config.align_multiline.struct_init_params is True

    assert config.line_breaks.keep_existing is False
    assert config.line_breaks.after_if is False
    assert config.line_breaks.before_then is True
    assert config.line_breaks.before_do_in_for is False
    assert config.line_breaks.before_statements_in_case is True
    assert config.line_breaks.after_pragma == "keep_existing"
    assert config.line_breaks.after_type_keyword is False
    assert config.line_breaks.place_struct_on_new_line is True
    assert config.line_breaks.place_simple_if_single_line is False
    assert config.line_breaks.wrap_before_comma is False
    assert config.line_breaks.after_left_paren_invocation is True
    assert config.line_breaks.after_left_paren_struct_init is True
    assert config.line_breaks.after_left_paren_fb_init is False
    assert config.line_breaks.after_left_paren_enum is False
    assert config.line_breaks.after_left_bracket_array is False
    assert config.line_breaks.before_left_paren_invocation is False
    assert config.line_breaks.before_left_paren_struct_init is False
    assert config.line_breaks.before_left_paren_fb_init is False
    assert config.line_breaks.before_left_paren_enum is False
    assert config.line_breaks.before_left_bracket_array is False
    assert config.line_breaks.before_right_paren_invocation is False
    assert config.line_breaks.before_right_paren_struct_init is False
    assert config.line_breaks.before_right_paren_fb_init is False
    assert config.line_breaks.before_right_paren_enum is False
    assert config.line_breaks.before_right_bracket_array is False

    assert config.calls.max_params_single_line == 4
    assert config.calls.max_struct_init_single_line == 3
    assert config.calls.max_fb_init_single_line == 3
    assert config.calls.max_array_init_single_line == 30
    assert config.calls.max_enum_single_line == 5
    assert config.calls.multiline_indent == 8
    assert config.calls.normalize_param_indent is True
    assert config.calls.join_single_line_when_fits is True

    assert config.alignment_heuristics.join_wrapped_assignments is True
    assert config.alignment_heuristics.bool_literal_min_group_lines == 3
    assert config.alignment_heuristics.bool_literal_name_spread_max == 2
    assert config.alignment_heuristics.assign_already_aligned_max_gap == 1
    assert config.alignment_heuristics.compact_orphan_assign_min_gap == 3
    assert config.alignment_heuristics.compact_orphan_assign_max_gap == 0
    assert config.alignment_heuristics.compact_orphan_expression_rhs_max_gap == 0
    assert config.alignment_heuristics.compact_orphan_expression_rhs_min_gap_floor == 10
    assert config.alignment_heuristics.compact_orphan_skip_rhs_or_and_chain is True
    assert config.alignment_heuristics.compact_orphan_simple_identifier_only is True
    assert config.alignment_heuristics.compact_pair_assigns is True
    assert config.alignment_heuristics.compact_pair_min_over_pad == 8
    assert config.alignment_heuristics.compact_group_min_lines == 4
    assert config.alignment_heuristics.compact_group_max_over_pad == 3
    assert config.alignment_heuristics.compact_three_line_count == 3
    assert config.alignment_heuristics.compact_three_line_over_pad == 2
    assert config.alignment_heuristics.compact_bool_chain_assigns is True
    assert config.alignment_heuristics.compact_same_col_outlier_enabled is False
    assert config.alignment_heuristics.compact_same_col_outlier_lhs_delta == 2
    assert config.alignment_heuristics.decl_comment_preserve_tight_gap is True
    assert config.alignment_heuristics.decl_comment_preserve_source_gap == 1
    assert config.alignment_heuristics.decl_comment_preserve_max_col_delta == 1
    assert config.alignment_heuristics.decl_split_outlier_median_multiplier == 1.5
    assert config.alignment_heuristics.decl_split_outlier_median_add == 20
    assert config.alignment_heuristics.split_case_inline_statements is True
    assert config.alignment_heuristics.split_case_numeric_labels_only is True
    assert config.alignment_heuristics.split_case_keep_else_inline_comment is True
    assert config.alignment_heuristics.blank_after_assign_before_comment is True
    assert config.alignment_heuristics.blank_after_assign_before_for is True
    assert config.alignment_heuristics.blank_after_assign_before_related_if is True
    assert (
        config.alignment_heuristics.blank_after_assign_before_related_if_skip_if_rhs_contains_paren
        is False
    )
    assert config.alignment_heuristics.blank_after_end_if_before_if is True
    assert config.alignment_heuristics.align_for_body_assignments is True
    assert config.alignment_heuristics.align_for_body_min_group_lines == 3
    assert config.alignment_heuristics.align_for_body_long_rhs_len_threshold == 30
    assert config.alignment_heuristics.align_for_body_min_lhs_spread_for_alignment == 3
    assert config.alignment_heuristics.expand_tight_assignment_spacing is True
    assert config.alignment_heuristics.three_line_assign_group_count == 3
    assert config.alignment_heuristics.three_line_assign_group_min_spread == 12
    assert config.alignment_heuristics.three_line_assign_group_max_lhs_len == 36
    assert config.alignment_heuristics.three_line_assign_group_min_qualified_count == 2
    assert config.alignment_heuristics.three_line_assign_group_extra_pad == 2
    assert config.alignment_heuristics.align_chained_init_assignments is True
    assert config.alignment_heuristics.align_ref_to_preceding_assign is True
    assert config.alignment_heuristics.align_init_injection_if_bodies is True
    assert config.alignment_heuristics.align_pre_chained_true_orphans is True

    assert config.parentheses.array_init_style == 2
    assert config.parentheses.fb_init_style == 2
    assert config.parentheses.function_call_style == 2
    assert config.parentheses.enum_style == 2
    assert config.parentheses.struct_init_style == 2

    assert config.keywords.uppercase is True

    assert config.xml.indent_size == 2
    assert config.xml.sort_methods is True
    assert config.xml.sort_actions is True
    assert config.xml.sort_properties is True

    assert config.validation.check_name_match is True
    assert config.validation.check_guids is True
    assert config.validation.check_structure is True

    assert config.safety.backup is True
    assert config.safety.delete_backup_on_success is True
    assert config.safety.syntax_check is True

    assert config.line_ending == "auto"

    print("  [PASS] All config defaults verified")


def test_config_override():
    """Test that user overrides are applied correctly."""
    override = {
        "indent": {"size": 2},
        "lineLength": {"wrap_at": 100},
        "keywords": {"uppercase": False},
        "alignment": {"declarations": False},
        "lineEnding": "crlf",
    }
    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".json"))
    tmp.write_text(json.dumps(override), encoding="utf-8")

    config = load_config(config_path=str(tmp))
    assert config.indent.size == 2
    assert config.indent.style == "spaces"  # not overridden
    assert config.line_length.wrap_at == 100
    assert config.keywords.uppercase is False
    assert config.alignment.declarations is False
    assert config.alignment.assignments is True  # not overridden
    assert config.line_ending == "crlf"
    tmp.unlink()
    print("  [PASS] Config overrides work correctly")


def test_config_roundtrip():
    """Test config serialization roundtrip."""
    config = load_config()
    d = config_to_dict(config)
    config2 = _dict_to_config(d)
    d2 = config_to_dict(config2)
    assert d == d2, "Config roundtrip failed"
    print("  [PASS] Config serialization roundtrip")


def test_keyword_casing():
    """Test keyword uppercasing on/off."""
    source = "if x = 5 then\n    y := 10;\nend_if\n"
    result = format_st_code(source, uppercase_keywords=True)
    assert "IF" in result and "THEN" in result and "END_IF" in result
    result2 = format_st_code(source, uppercase_keywords=False)
    assert "if" in result2 and "then" in result2
    print("  [PASS] Keyword casing (uppercase=true/false)")


def test_max_consecutive_blanks():
    """Test blank line clamping."""
    source = "a := 1;\n\n\n\n\nb := 2;\n"
    result = format_st_code(source, max_consecutive_blanks=1)
    assert "\n\n\n" not in result
    assert "a := 1;\n\nb := 2;" in result

    result2 = format_st_code(source, max_consecutive_blanks=2)
    assert "a := 1;\n\n\nb := 2;" in result2
    assert "\n\n\n\n" not in result2
    print("  [PASS] Max consecutive blank lines (1 and 2)")


def test_trailing_whitespace():
    """Test trailing whitespace removal."""
    source = "x := 1;   \ny := 2;\t\n"
    result = format_st_code(source)
    for line in result.split("\n"):
        if line:
            assert line == line.rstrip(), f"Trailing whitespace: [{line}]"
    print("  [PASS] Trailing whitespace removal")


def test_declaration_alignment():
    """Test variable declaration alignment."""
    lines = [
        "VAR",
        "    x : INT;",
        "    longName : BOOL;",
        "    y : REAL;",
        "END_VAR",
    ]
    result = align_declarations(lines)
    # All colons should be at the same column
    colon_positions = []
    for line in result[1:-1]:
        pos = line.find(" : ")
        if pos >= 0:
            colon_positions.append(pos)
    assert len(set(colon_positions)) == 1, f"Colons not aligned: {colon_positions}"
    print("  [PASS] Declaration alignment (colon alignment)")


def test_declaration_alignment_with_init():
    """Test declaration alignment with := initializers.

    ':=' is aligned when type widths are similar (spread <= 16).
    Types are padded to align the ':=' operator.
    """
    lines = [
        "VAR",
        "    x : INT := 5;",
        "    longName : BOOL := TRUE;",
        "    y : REAL := 1.0;",
        "END_VAR",
    ]
    result = align_declarations(lines)
    assign_positions = []
    for line in result[1:-1]:
        pos = line.find(":=")
        if pos >= 0:
            assign_positions.append(pos)
    assert len(set(assign_positions)) == 1, f":= not aligned: {assign_positions}"
    print("  [PASS] Declaration alignment (:= aligned for similar types)")


def test_assignment_alignment():
    """Test implementation assignment alignment."""
    lines = [
        "x := 1;",
        "longName := 2;",
        "y := 3;",
    ]
    result = align_assignments(lines)
    assign_positions = []
    for line in result:
        pos = line.find(":=")
        if pos >= 0:
            assign_positions.append(pos)
    assert len(set(assign_positions)) == 1, f":= not aligned: {assign_positions}"
    print("  [PASS] Assignment alignment in implementation")


def test_assignment_excludes_fb_calls():
    """Test that FB calls with := are NOT treated as assignments."""
    lines = [
        "    fbTimer(IN := TRUE);",
        "    fbTimer(IN := FALSE);",
        "    _bBusy := FALSE;",
    ]
    result = align_assignments(lines)
    # _bBusy should NOT be padded to align with fbTimer's :=
    assert result[2].strip() == "_bBusy := FALSE;", f"Got: [{result[2]}]"
    print("  [PASS] Assignment alignment excludes FB calls")


def test_fb_call_param_alignment():
    """Test FB call parameter alignment."""
    lines = [
        "FbName(",
        "        x := 1,",
        "        longParam := 2,",
        "        y := 3);",
    ]
    result = align_fb_call_params(lines)
    assign_positions = []
    for line in result[1:]:
        pos = line.find(":=")
        if pos >= 0:
            assign_positions.append(pos)
    assert len(set(assign_positions)) == 1, f":= not aligned: {assign_positions}"
    print("  [PASS] FB call parameter alignment")


def test_line_wrapping():
    """Test line wrapping at configured limit."""
    long_line = "x := " + "a + " * 60 + "b;"  # Very long line
    lines = [long_line]
    result = wrap_long_lines(lines, max_length=230)
    assert all(len(l) <= 230 for l in result), "Wrapped lines exceed 230"
    print("  [PASS] Line wrapping at 230 chars")


def test_line_wrapping_fb_call():
    """Test FB call wrapping with >4 params."""
    line = "    MyFB(a := 1, b := 2, c := 3, d := 4, e := 5);"
    lines = [line]
    result = wrap_long_lines(lines, max_params_single=4, call_indent=8)
    assert len(result) > 1, "FB call with 5 params should be wrapped"
    assert result[0].strip() == "MyFB("
    print("  [PASS] FB call wrapping (>4 params)")


def test_line_wrapping_no_wrap_under_limit():
    """Test that short FB calls are not wrapped."""
    line = "    MyFB(a := 1, b := 2, c := 3);"
    lines = [line]
    result = wrap_long_lines(lines, max_params_single=4, call_indent=8)
    assert len(result) == 1, "FB call with 3 params should NOT be wrapped"
    print("  [PASS] No wrapping under param limit")


def test_wrap_disabled():
    """Test that wrapping can be disabled via config."""
    from formatter.file_processor import _format_st_pipeline
    config = load_config()
    config.line_length.wrap_enabled = False

    long_line = "x := " + "a + " * 100 + "b;\n"
    result = _format_st_pipeline(long_line, config)
    assert len(result.split("\n")[0]) > 230
    print("  [PASS] Line wrapping disabled via config")


def test_alignment_disabled():
    """Test that alignment can be disabled via config."""
    from formatter.file_processor import _format_st_pipeline
    config = load_config()
    config.alignment.declarations = False
    config.alignment.assignments = False
    config.alignment.fb_call_params = False

    source = "VAR\n    x : INT;\n    longName : BOOL;\nEND_VAR\n"
    result = _format_st_pipeline(source, config)
    lines = result.strip().split("\n")
    # If alignment is off, colons should NOT be aligned
    pos1 = lines[1].find(" : ")
    pos2 = lines[2].find(" : ")
    assert pos1 != pos2, "Alignment should be disabled"
    print("  [PASS] Alignment disabled via config")


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("CONFIG & FEATURE TESTS")
    print("=" * 70)

    tests = [
        test_config_loading,
        test_config_override,
        test_config_roundtrip,
        test_keyword_casing,
        test_max_consecutive_blanks,
        test_trailing_whitespace,
        test_declaration_alignment,
        test_declaration_alignment_with_init,
        test_assignment_alignment,
        test_assignment_excludes_fb_calls,
        test_fb_call_param_alignment,
        test_line_wrapping,
        test_line_wrapping_fb_call,
        test_line_wrapping_no_wrap_under_limit,
        test_wrap_disabled,
        test_alignment_disabled,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 70}")
    print(f"RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'=' * 70}")
    sys.exit(0 if failed == 0 else 1)
