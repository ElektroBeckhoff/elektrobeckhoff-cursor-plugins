"""Unit tests for token budget limits, truncation flags, and response trimming."""

import os
import pytest

from infosys_mshc import InfoSysMshcIndex, parse_page
from infosys_mshc.paths import DEFAULT_MSHC_PATH

skip_no_mshc = pytest.mark.skipif(
    not os.path.isfile(DEFAULT_MSHC_PATH),
    reason="TwinCAT InfoSys offline documentation (.mshc) is not installed",
)

SAMPLE_HTML_LARGE = """
<!DOCTYPE html>
<html>
<head>
<title>FB_Sample_Huge</title>
<meta name="Description" content="Huge test function block" />
<meta name="Microsoft.Help.DisplayVersion" content="Tc3_Sample (v3.1.4024.0)" />
</head>
<body>
<h2>Inputs</h2>
<table>
""" + "\n".join(f"<tr><td>nIn{i}</td><td>INT</td><td>Input {i}</td></tr>" for i in range(100)) + """
</table>
<h2>Methods</h2>
<table>
""" + "\n".join(f"<tr><td>M_Method{i}</td><td>Method {i} description</td></tr>" for i in range(80)) + """
</table>
<p>This is a very long documentation text with many sentences repeated. """ * 50 + """</p>
</body>
</html>
"""


def test_token_budget_full_text_flag():
    """Verify include_full_text=False suppresses full text and reduces payload."""
    res_no_ft = parse_page(SAMPLE_HTML_LARGE, "sample/path.html", include_full_text=False)
    assert res_no_ft["full_text"] == ""
    assert res_no_ft["full_text_included"] is False
    assert res_no_ft["total_full_text_chars"] > 0

    res_ft = parse_page(
        SAMPLE_HTML_LARGE,
        "sample/path.html",
        include_full_text=True,
        max_full_text_chars=500,
    )
    assert len(res_ft["full_text"]) <= 550
    assert res_ft["truncated"] is True
    assert res_ft["full_text_included"] is True


def test_token_budget_limits_methods_and_params():
    """Verify method and parameter arrays are truncated with total counters."""
    res = parse_page(
        SAMPLE_HTML_LARGE,
        "sample/path.html",
        max_methods=20,
        max_params=15,
    )
    assert res["methods_total"] == 80
    assert res["methods_shown"] == 20
    assert len(res["methods"]) == 20

    assert res["params_total"] == 100
    assert res["params_shown"] == 15
    assert len(res["inputs"]) == 15
    assert res["truncated"] is True


@skip_no_mshc
def test_read_page_with_token_budget():
    """Verify read_page in live MSHC respects token flags."""
    with InfoSysMshcIndex(DEFAULT_MSHC_PATH) as idx:
        page_compact = idx.read_page(
            "tcplclib_tc3_jsonxml/1033/4219231115.html",
            include_full_text=False,
            max_methods=10,
        )
        assert page_compact["full_text"] == ""
        assert page_compact["full_text_included"] is False
        assert page_compact["methods_total"] > 10
        assert page_compact["methods_shown"] == 10
        assert page_compact["truncated"] is True
