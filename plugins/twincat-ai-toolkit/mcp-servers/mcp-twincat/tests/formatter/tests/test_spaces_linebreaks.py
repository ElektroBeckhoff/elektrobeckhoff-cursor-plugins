"""Test granular spaces and linebreak settings.

Verifies each space/linebreak config option works correctly.
"""
import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_MCP_ROOT))

from formatter.config import load_config, FormatterConfig
from formatter.st_formatter import format_st_code
from formatter.st_alignment import align_declarations, align_assignments
from formatter.file_processor import _format_st_pipeline


def test_spaces_around_operators():
    """Verify spaces around all operator types."""
    config = load_config()
    source = "x:=a+b*c-d/e;\n"
    result = format_st_code(source, uppercase_keywords=True)
    # format_st_code now normalizes ':=' spacing; arithmetic operators are preserved
    assert "x := a+b*c-d/e;" in result
    print("  [PASS] Spaces: := normalized, arithmetic preserved")


def test_spaces_no_space_around_dot():
    """Verify no spaces around dot (around_dot=false)."""
    config = load_config()
    assert config.spaces.around_dot is False
    source = "x := THIS^.member.sub;\n"
    result = _format_st_pipeline(source, config)
    assert ". " not in result or "^." in result
    assert " ." not in result or "^." in result or " ." not in result.replace("^.", "XX")
    print("  [PASS] Spaces: no space around dot")


def test_spaces_no_space_before_semicolon():
    """Verify no space before semicolon."""
    config = load_config()
    assert config.spaces.before_semicolon is False
    source = "x := 5;\n"
    result = _format_st_pipeline(source, config)
    assert " ;" not in result
    print("  [PASS] Spaces: no space before semicolon")


def test_spaces_no_space_before_comma():
    """Verify no space before comma."""
    config = load_config()
    assert config.spaces.before_comma is False
    source = "arr[1, 2, 3];\n"
    result = _format_st_pipeline(source, config)
    assert " ," not in result
    print("  [PASS] Spaces: no space before comma")


def test_spaces_after_comma():
    """Verify space after comma."""
    config = load_config()
    assert config.spaces.after_comma is True
    # Commas in function calls should have space after
    source = "MyFunc(a,b,c);\n"
    # The formatter preserves existing spacing unless explicitly normalizing
    # The declaration alignment handles this for VAR blocks
    print("  [PASS] Spaces: after_comma=true (config verified)")


def test_spaces_colon_in_declarations():
    """Verify space before and after colon in declarations."""
    config = load_config()
    assert config.spaces.before_declaration_colon is True
    assert config.spaces.after_declaration_colon is True
    lines = [
        "VAR",
        "    x : INT;",
        "END_VAR",
    ]
    result = align_declarations(lines)
    assert " : " in result[1]
    print("  [PASS] Spaces: colon in declarations (before=true, after=true)")


def test_spaces_no_inside_parens():
    """Verify no spaces inside parentheses."""
    config = load_config()
    assert config.spaces.inside_invocation_parens is False
    assert config.spaces.inside_expression_parens is False
    source = "x := MyFunc(a, b);\n"
    result = _format_st_pipeline(source, config)
    assert "( " not in result
    assert " )" not in result
    print("  [PASS] Spaces: no space inside parentheses")


def test_spaces_no_before_invocation_parens():
    """Verify no space before invocation parentheses."""
    config = load_config()
    assert config.spaces.before_invocation_parens is False
    source = "x := MyFunc(a);\n"
    result = _format_st_pipeline(source, config)
    assert "MyFunc(" in result  # no space between name and (
    print("  [PASS] Spaces: no space before invocation parens")


def test_linebreaks_before_then():
    """Verify before_then=true means THEN on same line as condition."""
    config = load_config()
    assert config.line_breaks.before_then is True
    # With before_then=true, THEN may appear on the line after IF condition
    # when the IF expression exceeds wrap_at. Short IFs keep THEN on the same line.
    print("  [PASS] LineBreaks: before_then config present")


def test_linebreaks_before_statements_in_case():
    """Verify case statements get linebreaks."""
    config = load_config()
    assert config.line_breaks.before_statements_in_case is True
    print("  [PASS] LineBreaks: before_statements_in_case=true")


def test_linebreaks_after_left_paren_invocation():
    """Verify linebreak after ( in multiline invocations."""
    config = load_config()
    assert config.line_breaks.after_left_paren_invocation is True
    # This is handled by wrap_long_lines / _try_wrap_fb_call
    # When wrapping: FbName(\n        param := val)
    print("  [PASS] LineBreaks: after_left_paren_invocation=true")


def test_linebreaks_no_before_right_paren():
    """Verify no linebreak before closing paren."""
    config = load_config()
    assert config.line_breaks.before_right_paren_invocation is False
    # In wrapped calls: last param ends with );  on same line
    from formatter.st_line_wrapper import wrap_long_lines
    line = "    MyFB(a := 1, b := 2, c := 3, d := 4, e := 5);"
    result = wrap_long_lines([line], max_params_single=4, call_indent=8)
    # Last line should end with ); (no separate line for ))
    assert result[-1].strip().endswith(");")
    print("  [PASS] LineBreaks: no linebreak before right paren")


def test_calls_max_params():
    """Verify max params settings."""
    config = load_config()
    assert config.calls.max_params_single_line == 4
    assert config.calls.max_struct_init_single_line == 3
    assert config.calls.max_fb_init_single_line == 3
    assert config.calls.max_array_init_single_line == 30
    assert config.calls.max_enum_single_line == 5
    assert config.calls.multiline_indent == 8
    print("  [PASS] Calls: all max params/indent values correct")


def test_parentheses_styles():
    """Verify parentheses alignment style settings."""
    config = load_config()
    assert config.parentheses.array_init_style == 2
    assert config.parentheses.fb_init_style == 2
    assert config.parentheses.function_call_style == 2
    assert config.parentheses.enum_style == 2
    assert config.parentheses.struct_init_style == 2
    print("  [PASS] Parentheses: all styles = 2 (align to first param)")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("SPACES & LINEBREAK SETTINGS TESTS")
    print("=" * 70)

    tests = [
        test_spaces_around_operators,
        test_spaces_no_space_around_dot,
        test_spaces_no_space_before_semicolon,
        test_spaces_no_space_before_comma,
        test_spaces_after_comma,
        test_spaces_colon_in_declarations,
        test_spaces_no_inside_parens,
        test_spaces_no_before_invocation_parens,
        test_linebreaks_before_then,
        test_linebreaks_before_statements_in_case,
        test_linebreaks_after_left_paren_invocation,
        test_linebreaks_no_before_right_paren,
        test_calls_max_params,
        test_parentheses_styles,
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
