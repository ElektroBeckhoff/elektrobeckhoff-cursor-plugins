"""Advanced comment edge case tests."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.st_formatter import format_st_code
from formatter.st_alignment import align_declarations, align_assignments
from formatter.file_processor import _format_st_pipeline
from formatter.config import load_config

CONFIG = load_config()


def test_deeply_nested_comments():
    code = "(* level1 (* level2 (* level3 *) back2 *) back1 *)\nx := 1;\n"
    result = _format_st_pipeline(code, CONFIG)
    assert "level3" in result


def test_comment_with_assign_operator():
    lines = [
        "    (* Assignment test: x := 5 is just example *)",
        "    a := 1;",
        "    b := 2;",
    ]
    result = align_assignments(lines)
    assert ":= 5" in result[0]
    a_pos = result[1].find(":=")
    b_pos = result[2].find(":=")
    assert a_pos == b_pos


def test_comment_with_colon_inside():
    lines = [
        "VAR",
        "    (* Note: this describes the purpose *)",
        "    x : INT;",
        "    longName : BOOL;",
        "END_VAR",
    ]
    result = align_declarations(lines)
    assert "(* Note: this describes the purpose *)" in result[1]


def test_empty_block_comment():
    code = "(**)\nx := 1;\n"
    result = _format_st_pipeline(code, CONFIG)
    assert "(**)" in result


def test_comment_after_end_if():
    code = "IF x THEN\n    y := 1;\nEND_IF (* end of check *)\n"
    result = format_st_code(code, uppercase_keywords=True)
    assert "END_IF" in result
    assert "(* end of check *)" in result


def test_triple_slash_with_pragma_then_decl():
    lines = [
        "VAR",
        "    /// This is the enable flag",
        "    {attribute 'hide'}",
        "    bEnable : BOOL;",
        "    /// Counter value",
        "    nCount  : INT;",
        "END_VAR",
    ]
    result = align_declarations(lines)
    assert "/// This is the enable flag" in result[1]
    assert "{attribute" in result[2]


def test_multiline_comment_breaks_groups():
    lines = [
        "VAR",
        "    x : INT;",
        "    (* This is a separator",
        "       for the next group *)",
        "    longName : BOOL;",
        "    y        : REAL;",
        "END_VAR",
    ]
    result = align_declarations(lines)
    assert result[2] == "    (* This is a separator"
    assert result[3] == "       for the next group *)"


def test_single_line_comment_as_separator():
    lines = [
        "VAR",
        "    a : INT;",
        "    // --- Next section ---",
        "    longName : BOOL;",
        "    b        : REAL;",
        "END_VAR",
    ]
    result = align_declarations(lines)
    assert result[2] == "    // --- Next section ---"


def test_comment_delimiters_in_strings():
    code = "sMsg := '(* not a comment *) // neither';\n"
    result = format_st_code(code, uppercase_keywords=True)
    assert "'(* not a comment *) // neither'" in result


def test_triple_slash_content_not_uppercased():
    code = "/// enable flag for the function_block\nbEnable := TRUE;\n"
    result = format_st_code(code, uppercase_keywords=True)
    assert "/// enable flag for the function_block" in result
    assert "TRUE" in result


def test_block_comment_single_line_preserved():
    code = "(* Quick note *)\nIF x THEN\nEND_IF\n"
    result = format_st_code(code, uppercase_keywords=True)
    assert "(* Quick note *)" in result


def test_inline_comment_alignment_in_declarations():
    lines = [
        "VAR",
        "    bEnable : BOOL; (* Enable flag *)",
        "    nCount  : INT;  (* Counter *)",
        "    fValue  : REAL; (* Measured value *)",
        "END_VAR",
    ]
    result = align_declarations(lines)
    # All comments should be present
    assert "(* Enable flag *)" in result[1]
    assert "(* Counter *)" in result[2]
    assert "(* Measured value *)" in result[3]


def test_doc_comment_before_type():
    """/// before TYPE should be preserved and not confuse parsing."""
    code = "/// Sensor type enumeration\nTYPE E_Sensor : (None, Temp, Pressure);\nEND_TYPE\n"
    result = format_st_code(code, uppercase_keywords=True)
    assert "/// Sensor type enumeration" in result
    assert "TYPE" in result


def test_rst_comment_in_library_doc():
    """reStructuredText comments (for TE1030) must be preserved."""
    code = "(* :Description:\n   This FB implements the main control loop.\n   \n   :Requirements:\n   - Input range: 0..100\n*)\nIF x THEN\nEND_IF\n"
    result = format_st_code(code, uppercase_keywords=True)
    assert ":Description:" in result
    assert ":Requirements:" in result
    assert "- Input range: 0..100" in result


def test_comments_in_var_block_headers():
    """Comments right after VAR, VAR_INPUT, VAR_OUTPUT."""
    lines = [
        "VAR (* internal vars *)",
        "    nVal : INT; (* value *)",
        "END_VAR",
        "VAR_INPUT (* inputs *)",
        "    bIn  : BOOL; // input flag",
        "END_VAR",
    ]
    result = align_declarations(lines)
    assert "(* internal vars *)" in result[0]
    assert "(* inputs *)" in result[3]


def test_comments_inside_expressions():
    """Comments placed between tokens inside arithmetic and boolean expressions."""
    code = (
        "nRes := nA + (* term 1 *) nB * (* term 2 *) nC;\n"
        "bRes := bA (* first *) AND THEN (* second *) bB;\n"
    )
    result = _format_st_pipeline(code, CONFIG)
    assert "(* term 1 *)" in result
    assert "(* term 2 *)" in result
    assert "(* first *)" in result
    assert "(* second *)" in result


def test_comments_in_if_elsif_else():
    """Comments on IF, ELSIF, ELSE, and END_IF lines."""
    code = (
        "IF (* check A *) bA THEN // started A\n"
        "    nA := 1; // assigned\n"
        "ELSIF (* check B *) bB THEN (* alternate *)\n"
        "    nB := 2;\n"
        "ELSE (* default fallback *)\n"
        "    nC := 0;\n"
        "END_IF (* all done *);\n"
    )
    result = _format_st_pipeline(code, CONFIG)
    assert "(* check A *)" in result
    assert "// started A" in result
    assert "(* alternate *)" in result
    assert "(* default fallback *)" in result
    assert "(* all done *)" in result


def test_comments_in_case_statements():
    """Comments on CASE selector, labels, and inside branches."""
    code = (
        "CASE (* eval state *) nState OF\n"
        "    1 (* Idle state *):\n"
        "        nNext := 2; // transition\n"
        "    2 (* Running *), 3 (* Active *):\n"
        "        nNext := 4;\n"
        "    ELSE (* unknown state *)\n"
        "        nNext := 0;\n"
        "END_CASE (* case closed *);\n"
    )
    result = _format_st_pipeline(code, CONFIG)
    assert "(* eval state *)" in result
    assert "(* Idle state *)" in result
    assert "(* Running *)" in result
    assert "(* Active *)" in result
    assert "(* unknown state *)" in result
    assert "(* case closed *)" in result


def test_comments_in_loops():
    """Comments in FOR, WHILE, REPEAT, UNTIL statements."""
    code = (
        "FOR nI := 1 (* start *) TO 10 (* end *) BY 2 (* step *) DO\n"
        "    nSum := nSum + nI; // accumulate\n"
        "END_FOR (* for done *);\n"
        "\n"
        "WHILE (* check loop condition *) bRun DO\n"
        "    IF bStop THEN\n"
        "        EXIT; (* break out *)\n"
        "    END_IF\n"
        "END_WHILE (* while done *);\n"
        "\n"
        "REPEAT\n"
        "    nCount := nCount + 1;\n"
        "UNTIL (* stop when count reaches 10 *) nCount >= 10\n"
        "END_REPEAT (* repeat done *);\n"
    )
    result = _format_st_pipeline(code, CONFIG)
    assert "(* start *)" in result
    assert "(* end *)" in result
    assert "(* step *)" in result
    assert "(* check loop condition *)" in result
    assert "(* break out *)" in result
    assert "(* stop when count reaches 10 *)" in result
    assert "(* repeat done *)" in result


def test_comments_in_fb_calls():
    """Comments embedded inside FB and function parameter lists."""
    code = (
        "fbTon(\n"
        "    IN := (* enable signal *) bStart,\n"
        "    PT := (* duration *) T#5S\n"
        "); // timer call\n"
    )
    result = _format_st_pipeline(code, CONFIG)
    assert "(* enable signal *)" in result
    assert "(* duration *)" in result
    assert "// timer call" in result


def test_comments_with_xml_special_characters():
    """Comments containing <, >, &, \", ' must not break or be altered."""
    code = (
        "// <xml-tag attr=\"value\" &amp; other='true'>\n"
        "(* <a> && <b> || <c> -> test *) \n"
        "x := 1;\n"
    )
    result = _format_st_pipeline(code, CONFIG)
    assert "<xml-tag attr=\"value\" &amp; other='true'>" in result
    assert "<a> && <b> || <c> -> test" in result


def test_comments_containing_st_code_snippets():
    """Comments containing ST keywords/code must not trigger false indentation/parsing."""
    code = (
        "// IF bDummy THEN x := 1; END_IF;\n"
        "(*\n"
        "VAR\n"
        "    nOld : INT;\n"
        "END_VAR\n"
        "FOR i := 1 TO 10 DO\n"
        "    CASE state OF 1: y := 2; END_CASE\n"
        "END_FOR\n"
        "*)\n"
        "nReal := 42;\n"
    )
    result = _format_st_pipeline(code, CONFIG)
    assert "nReal := 42;" in result
    assert "IF bDummy THEN" in result
    assert "CASE state OF" in result


def test_comments_in_struct_declarations():
    """Comments inside STRUCT member declarations."""
    lines = [
        "TYPE ST_CommentTest :",
        "STRUCT",
        "    (* Header for group 1 *)",
        "    nId    : DINT;        (* Primary key *)",
        "    sName  : STRING(50);  // Name of entity",
        "    fValue : REAL := 0.0; (* Default float *)",
        "END_STRUCT",
        "END_TYPE",
    ]
    result = align_declarations(lines)
    assert "(* Header for group 1 *)" in result[2]
    assert "(* Primary key *)" in result[3]
    assert "// Name of entity" in result[4]
    assert "(* Default float *)" in result[5]


def test_comments_in_enum_declarations():
    """Comments inside ENUM members."""
    lines = [
        "TYPE E_Color : (",
        "    (* Primary colors *)",
        "    Red   := 1, (* bright red *)",
        "    Green := 2, (* forest green *)",
        "    Blue  := 3  // deep blue",
        ") INT;",
        "END_TYPE",
    ]
    result = align_declarations(lines)
    assert "(* Primary colors *)" in result[1]
    assert "(* bright red *)" in result[2]
    assert "(* forest green *)" in result[3]
    assert "// deep blue" in result[4]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
