"""Unit tests verifying formatter correctness on advanced TwinCAT-3 ST syntax edge cases."""
from __future__ import annotations

import pytest

from formatter.config import load_config
from formatter.file_processor import _format_st_pipeline
from formatter.st_statement_normalize import normalize_statements


@pytest.fixture
def config():
    return load_config()


def test_bit_access_and_pointer_dereference(config):
    code = """
pStruct^.arrData[0].3 := TRUE;
pNested^^.field := 42;
bFlag := nStatus.0 AND NOT nStatus.15;
"""
    formatted = _format_st_pipeline(code, config)
    assert "pStruct^.arrData[0].3 := TRUE;" in formatted
    assert "pNested^^.field       := 42;" in formatted or "pNested^^.field := 42;" in formatted
    assert "bFlag                 := nStatus.0 AND NOT nStatus.15;" in formatted or "bFlag := nStatus.0 AND NOT nStatus.15;" in formatted
    # Idempotence
    assert _format_st_pipeline(formatted, config) == formatted


def test_reference_operations_and_special_operators(config):
    code = """
IF __ISVALIDREF(rTarget) THEN
    rTarget REF= nSource;
    rTarget := 100;
END_IF;

__QUERYINTERFACE(iSource, iTarget);
__QUERYPOINTER(iSource, pTarget);
pBlock := __NEW(ST_Data);
__DELETE(pBlock);
"""
    formatted = _format_st_pipeline(code, config)
    assert "IF __ISVALIDREF(rTarget) THEN" in formatted
    assert "    rTarget REF= nSource;" in formatted
    assert "    rTarget := 100;" in formatted
    assert "__QUERYINTERFACE(iSource, iTarget);" in formatted
    assert "__QUERYPOINTER(iSource, pTarget);" in formatted
    assert "pBlock := __NEW(ST_Data);" in formatted
    assert "__DELETE(pBlock);" in formatted
    # Idempotence
    assert _format_st_pipeline(formatted, config) == formatted


def test_try_catch_finally_blocks(config):
    code = """
__TRY
nCounter := nCounter + 1;
pSample^ := 42;
__CATCH(exc)
nErrors := nErrors + 1;
__FINALLY
pSample := 0;
__ENDTRY
"""
    formatted = _format_st_pipeline(code, config)
    expected = """__TRY
    nCounter := nCounter + 1;
    pSample^ := 42;
__CATCH(exc)
    nErrors := nErrors + 1;
__FINALLY
    pSample := 0;
__ENDTRY
"""
    assert formatted.strip() == expected.strip()
    # Oneliner collapse fixpoint
    collapsed = " ".join(code.split())
    assert _format_st_pipeline(collapsed, config).strip() == expected.strip()


def test_jmp_and_labels(config):
    code = """
IF bSkip THEN
    JMP _endLabel;
END_IF;

nVal := 10;

_endLabel:
nVal := 20;
"""
    formatted = _format_st_pipeline(code, config)
    assert "JMP _endLabel;" in formatted
    assert "_endLabel:" in formatted
    assert _format_st_pipeline(formatted, config) == formatted


def test_string_escaped_quotes_and_dollar_syntax(config):
    code = """
sMsg1 := 'It''s a test with ''escaped'' quotes';
sMsg2 := "Double ""quoted"" string";
sMsg3 := 'Influx query: $\\'select * from "table" where x = 1$\\';
"""
    formatted = _format_st_pipeline(code, config)
    assert "'It''s a test with ''escaped'' quotes'" in formatted
    assert '"Double ""quoted"" string"' in formatted
    # Idempotence
    assert _format_st_pipeline(formatted, config) == formatted


def test_var_config_declarations(config):
    code = """
VAR_CONFIG
MAIN.fbMotor.bEnable AT %QX0.0:BOOL;
MAIN.fbMotor.nSpeed AT %QW2:INT:=1500;
MAIN.fbSensor.fVal AT %MD10:REAL;
END_VAR
"""
    formatted = _format_st_pipeline(code, config)
    assert "VAR_CONFIG" in formatted
    assert "MAIN.fbMotor.bEnable AT %QX0.0 : BOOL;" in formatted
    assert "MAIN.fbMotor.nSpeed  AT %QW2   : INT" in formatted
    assert "MAIN.fbSensor.fVal   AT %MD10  : REAL;" in formatted
    assert "END_VAR" in formatted
    # Idempotence
    assert _format_st_pipeline(formatted, config) == formatted


def test_multivariable_declarations_and_arrays(config):
    code = """
VAR
x, y, z : INT := 0;
arrMatrix : ARRAY[1..cRows, 1..cCols] OF LREAL;
arrSubrange : ARRAY[-10..10] OF SINT;
END_VAR
"""
    formatted = _format_st_pipeline(code, config)
    assert "x, y, z     : INT" in formatted or "x, y, z : INT" in formatted
    assert "arrMatrix   : ARRAY[1..cRows, 1..cCols] OF LREAL;" in formatted
    assert "arrSubrange : ARRAY[-10..10] OF SINT;" in formatted
    assert _format_st_pipeline(formatted, config) == formatted


def test_conditional_compilation_pragmas(config):
    code = """
{IF defined (DEBUG)}
    F_LogDebug('Debug mode active');
{ELSIF defined (SIMULATION)}
    F_LogDebug('Simulation mode active');
{ELSE}
    F_LogDebug('Production mode active');
{END_IF}
"""
    formatted = _format_st_pipeline(code, config)
    assert "{IF defined (DEBUG)}" in formatted
    assert "{ELSIF defined (SIMULATION)}" in formatted
    assert "{ELSE}" in formatted
    assert "{END_IF}" in formatted
    assert _format_st_pipeline(formatted, config) == formatted


def test_disable_formatting_regions(config):
    code = """
// Formatted part
nVal:=1;

{formatting.disable}
nUnformatted:=   1  +   2   ;
{formatting.enable}

// Formatted part again
nVal:=2;
"""
    formatted = _format_st_pipeline(code, config)
    assert "nVal := 1;" in formatted
    assert "nUnformatted:=   1  +   2   ;" in formatted
    assert "nVal := 2;" in formatted
    assert _format_st_pipeline(formatted, config) == formatted
