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
def test_parse_param_table_noise_filtering():
    section_html = (
        "<table>"
        "<tr><th>Name</th><th>Type</th><th>Description</th></tr>"
        "<tr><td>bExecute</td><td>BOOL</td><td>Rising edge starts operation</td></tr>"
        "<tr><td>0</td><td></td><td>OK</td></tr>"
        "<tr><td>> 0</td><td></td><td>Error code</td></tr>"
        "<tr><td>Return parameter</td><td>UDINT</td><td>Internal status</td></tr>"
        "<tr><td>Meaning of flags</td><td></td><td>Table note</td></tr>"
        "<tr><td>nLimit</td><td>INT</td><td>Upper boundary</td></tr>"
        "</table>"
    )
    params = parse_param_table(section_html)
    assert len(params) == 2
    assert params[0]["name"] == "bExecute"
    assert params[0]["type"] == "BOOL"
    assert params[1]["name"] == "nLimit"
    assert params[1]["type"] == "INT"


def test_extract_properties_and_return_type():
    from infosys_mshc.html_parser import extract_properties, extract_return_type, extract_canonical_name_and_type

    prop_html = (
        "<table>"
        "<tr><th>Property</th><th>Type</th><th>Description</th><th>Access</th></tr>"
        "<tr><td>bConnected</td><td>BOOL</td><td>Connection status</td><td>Get</td></tr>"
        "<tr><td>nTimeout</td><td>UDINT</td><td>Timeout in ms</td><td>Get/Set</td></tr>"
        "</table>"
    )
    props = extract_properties(prop_html)
    assert len(props) == 2
    assert props[0]["name"] == "bConnected"
    assert props[0]["type"] == "BOOL"
    assert props[0]["access"] == "Get"
    assert props[1]["name"] == "nTimeout"
    assert props[1]["type"] == "UDINT"
    assert props[1]["access"] == "Get/Set"

    # Return type extraction
    syntax_fn = "FUNCTION MEMCPY : UDINT\nVAR_INPUT\n    destAddr : PVOID;\nEND_VAR"
    assert extract_return_type(syntax_fn) == "UDINT"

    syntax_str = "FUNCTION CONCAT : STRING(255)\nVAR_INPUT\n    STR1 : STRING(255);\nEND_VAR"
    assert extract_return_type(syntax_str) == "STRING"

    # Canonical name and prefix stripping
    canon, sym_type = extract_canonical_name_and_type("Interface ITcUnknown")
    assert canon == "ITcUnknown"
    assert sym_type == "INTERFACE"

    canon_fb, sym_fb = extract_canonical_name_and_type("Funktionsbaustein FB_Demo")
    assert canon_fb == "FB_Demo"
    assert sym_fb == "FUNCTION_BLOCK"


def test_parse_page_with_properties_and_canonical():
    raw_html = (
        "<html><head>"
        "<title>Interface ITcIoServer</title>"
        '<meta name="Description" content="TwinCAT I/O server interface" />'
        "</head><body>"
        "<h2>Properties</h2>"
        "<table><tr><td>bActive</td><td>BOOL</td><td>Server active flag</td></tr></table>"
        "<h2>Methods</h2>"
        "<table><tr><td>M_Start</td><td>Starts server</td></tr></table>"
        "</body></html>"
    )
    page = parse_page(raw_html, "tc3_system/1033/999.html")
    assert page["title"] == "Interface ITcIoServer"
    assert page["canonical_name"] == "ITcIoServer"
    assert page["type"] == "INTERFACE"
    assert len(page["properties"]) == 1
    assert page["properties"][0]["name"] == "bActive"
    assert len(page["methods"]) == 1
    assert page["methods"][0]["name"] == "M_Start"

