"""Unit tests for Markdown format generation for search and page reads."""

from infosys_mshc import format_page_markdown, format_search_markdown


def test_format_search_markdown():
    """Verify search result markdown layout."""
    mock_search = {
        "query": "FB_JsonDomParser",
        "mode": "auto",
        "count": 1,
        "results": [
            {
                "title": "FB_JsonDomParser",
                "type": "FUNCTION_BLOCK",
                "component": "tcplclib_tc3_jsonxml",
                "library": "Tc3_JsonXml",
                "parent": "",
                "path": "tcplclib_tc3_jsonxml/1033/4219231115.html",
                "score": 100,
                "description": "JSON DOM parser block",
            }
        ],
    }
    md = format_search_markdown(mock_search)
    assert "### InfoSys Search: `FB_JsonDomParser`" in md
    assert "| 1 | 100% | `FB_JsonDomParser` | `FUNCTION_BLOCK` | Tc3_JsonXml |" in md
    assert "JSON DOM parser block" in md


def test_format_page_markdown():
    """Verify documentation page markdown rendering with tables and IEC codeblock."""
    mock_page = {
        "title": "FB_Test",
        "type": "FUNCTION_BLOCK",
        "library": "Tc3_TestLib",
        "parent": "",
        "component": "tcplclib_tc3_test",
        "description": "A test block.",
        "syntax": "FUNCTION_BLOCK FB_Test\nVAR_INPUT\n    bExec : BOOL;\nEND_VAR",
        "inputs": [{"name": "bExec", "type": "BOOL", "description": "Execute"}],
        "outputs": [{"name": "bDone", "type": "BOOL", "description": "Done"}],
        "methods": [{"name": "M_Reset", "description": "Reset block"}],
        "requirements": {"library": "Tc3_TestLib", "twincat_version": "v3.1.4024.0"},
        "full_text": "",
        "truncated": False,
    }
    md = format_page_markdown(mock_page)
    assert "## `FB_Test` (`FUNCTION_BLOCK`)" in md
    assert "**Library:** `Tc3_TestLib`" in md
    assert "```iecst" in md
    assert "FUNCTION_BLOCK FB_Test" in md
    assert "| `bExec` | `BOOL` | Execute |" in md
    assert "| `bDone` | `BOOL` | Done |" in md
    assert "| `M_Reset` | Reset block |" in md
