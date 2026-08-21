"""Unit tests for infosys_mshc.html_parser module."""

import pytest
from infosys_mshc.html_parser import (
    detect_type,
    extract_methods,
    extract_requirements,
    extract_syntax,
    parse_page,
    parse_param_table,
    split_sections,
    strip_tags,
)


def test_strip_tags():
    html_input = "<p>Hello <b>World</b>&amp; TwinCAT!<br />Line 2<br>Line 3</p>"
    text = strip_tags(html_input)
    assert "Hello World& TwinCAT!" in text
    assert "Line 2\nLine 3" in text


def test_detect_type():
    assert detect_type("FB_Sample") == "FUNCTION_BLOCK"
    assert detect_type("ST_Config") == "STRUCT"
    assert detect_type("E_Mode") == "ENUM"
    assert detect_type("I_Widget") == "INTERFACE"
    assert detect_type("F_Calc") == "FUNCTION"
    assert detect_type("T_MaxString") == "TYPE"
    assert detect_type("Overview and Introduction") == "article"


def test_extract_syntax():
    html_with_syntax = (
        "<div><h2>Syntax</h2>"
        "<pre>FUNCTION_BLOCK FB_Test\nVAR_INPUT\n    bEnable : BOOL;\nEND_VAR</pre>"
        "</div>"
    )
    syntax = extract_syntax(html_with_syntax)
    assert "FUNCTION_BLOCK FB_Test" in syntax
    assert "VAR_INPUT" in syntax
    assert "bEnable : BOOL;" in syntax

    html_no_syntax = "<div><p>Just normal text here.</p></div>"
    assert extract_syntax(html_no_syntax) == ""


def test_split_sections():
    raw_html = (
        "<h2>Eingänge</h2><p>Input content</p>"
        "<h2>Ausgänge</h2><p>Output content</p>"
        "<h2>Methoden</h2><p>Methods content</p>"
        "<h2>Voraussetzungen</h2><p>Req content</p>"
    )
    sections = split_sections(raw_html)
    assert "inputs" in sections
    assert "outputs" in sections
    assert "methods" in sections
    assert "requirements" in sections
    assert "<p>Input content</p>" in sections["inputs"]


def test_parse_param_table():
    section_html = (
        "<table>"
        "<tr><th>Name</th><th>Type</th><th>Description</th></tr>"
        "<tr><td>bExecute</td><td>BOOL</td><td>Rising edge starts operation</td></tr>"
        "<tr><td>tTimeout</td><td>TIME</td><td>Timeout duration</td></tr>"
        "</table>"
    )
    params = parse_param_table(section_html)
    assert len(params) == 2
    assert params[0]["name"] == "bExecute"
    assert params[0]["type"] == "BOOL"
    assert params[0]["description"] == "Rising edge starts operation"
    assert params[1]["name"] == "tTimeout"
    assert params[1]["type"] == "TIME"


def test_extract_methods():
    table_html = (
        "<table>"
        "<tr><th>Method Name</th><th>Description</th></tr>"
        "<tr><td>M_Execute</td><td>Runs one execution step</td></tr>"
        "<tr><td>Reset</td><td>Resets internal state</td></tr>"
        "</table>"
    )
    methods = extract_methods(table_html)
    assert len(methods) == 2
    assert methods[0]["name"] == "M_Execute"
    assert methods[0]["description"] == "Runs one execution step"
    assert methods[1]["name"] == "Reset"

    text_fallback_html = (
        "<div>"
        "M_Init(bMode : BOOL) - Initialize<br/>"
        "M_Cleanup() : Closes all handles"
        "</div>"
    )
    methods_fallback = extract_methods(text_fallback_html)
    assert len(methods_fallback) == 2
    assert methods_fallback[0]["name"] == "M_Init"
    assert methods_fallback[1]["name"] == "M_Cleanup"


def test_extract_requirements():
    section_html = (
        "<table>"
        "<tr><td>PLC Lib</td><td>Tc3_IoTBase</td></tr>"
        "<tr><td>TwinCAT Version</td><td>v3.1.4024.0 or higher</td></tr>"
        "<tr><td>Development Environment</td><td>TwinCAT XAE</td></tr>"
        "<tr><td>Target Platform</td><td>PC or CX (x86, x64, ARM)</td></tr>"
        "</table>"
    )
    reqs = extract_requirements(section_html)
    assert reqs["library"] == "Tc3_IoTBase"
    assert reqs["twincat_version"] == "v3.1.4024.0 or higher"
    assert reqs["development_environment"] == "TwinCAT XAE"
    assert reqs["target_platform"] == "PC or CX (x86, x64, ARM)"


def test_parse_page_full():
    raw_html = (
        "<html><head>"
        "<title>FB_DemoController</title>"
        '<meta name="Description" content="Controller function block description" />'
        '<meta name="Microsoft.Help.DisplayVersion" content="Tc3_Demo (v3.1.4024)" />'
        "</head><body>"
        "<h2>Syntax</h2>"
        "<pre>FUNCTION_BLOCK FB_DemoController\nVAR_INPUT\n    bRun : BOOL;\nEND_VAR</pre>"
        "<h2>Inputs</h2>"
        "<table><tr><td>bRun</td><td>BOOL</td><td>Run control flag</td></tr></table>"
        "<h2>Outputs</h2>"
        "<table><tr><td>bDone</td><td>BOOL</td><td>Operation completed</td></tr></table>"
        "<h2>Methods</h2>"
        "<table><tr><td>Reset</td><td>Reset controller</td></tr></table>"
        "<h2>Requirements</h2>"
        "<table><tr><td>PLC Lib</td><td>Tc3_Demo</td></tr></table>"
        "</body></html>"
    )
    page = parse_page(raw_html, "tc3_demo/1033/12345.html")
    assert page["title"] == "FB_DemoController"
    assert page["type"] == "FUNCTION_BLOCK"
    assert page["component"] == "tc3_demo"
    assert page["description"] == "Controller function block description"
    assert "FUNCTION_BLOCK FB_DemoController" in page["syntax"]
    assert len(page["inputs"]) == 1
    assert page["inputs"][0]["name"] == "bRun"
    assert len(page["outputs"]) == 1
    assert page["outputs"][0]["name"] == "bDone"
    assert len(page["methods"]) == 1
    assert page["methods"][0]["name"] == "Reset"
    assert page["requirements"]["library"] == "Tc3_Demo"
