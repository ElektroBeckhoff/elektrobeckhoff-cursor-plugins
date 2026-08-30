"""Comprehensive tests for all VAR block modifier combinations.

Verifies the formatter correctly handles:
- VAR CONSTANT, VAR PERSISTENT, VAR RETAIN
- VAR PERSISTENT RETAIN, VAR RETAIN PERSISTENT
- VAR_INPUT CONSTANT
- VAR_IN_OUT CONSTANT (read-only pass-by-reference, TwinCAT 3.1.4024+)
- VAR_GLOBAL CONSTANT, VAR_GLOBAL PERSISTENT, VAR_GLOBAL RETAIN
- VAR_GLOBAL PERSISTENT RETAIN
- VAR_STAT PERSISTENT, VAR_STAT RETAIN
- Combined modifiers on all VAR types
- Alignment inside modified VAR blocks
- Keyword casing of modifiers
"""
import pytest

from formatter.st_formatter import format_st_code
from formatter.st_alignment import align_declarations, align_assignments
from formatter.file_processor import _format_st_pipeline
from formatter.config import FormatterConfig


@pytest.fixture
def config():
    return FormatterConfig()


def _assert_idempotent(source: str, config: FormatterConfig) -> str:
    r1 = _format_st_pipeline(source, config)
    r2 = _format_st_pipeline(r1, config)
    assert r1 == r2, f"Not idempotent!\nFirst:\n{r1}\nSecond:\n{r2}"
    return r1


# ---------------------------------------------------------------------------
# Basic VAR + single modifier
# ---------------------------------------------------------------------------


class TestVarConstant:

    def test_var_constant_keyword_casing(self, config):
        code = "var constant\n    cMax : int := 100;\nend_var"
        result = _format_st_pipeline(code, config)
        assert "VAR CONSTANT" in result
        assert "END_VAR" in result
        assert "INT" in result

    def test_var_constant_alignment(self, config):
        code = (
            "VAR CONSTANT\n"
            "    cMaxRetries : UINT := 5;\n"
            "    cTimeout    : TIME := T#10s;\n"
            "    cName       : STRING := 'default';\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR CONSTANT" in result
        assert "cMaxRetries" in result
        assert "cTimeout" in result

    def test_var_constant_with_various_types(self, config):
        code = (
            "VAR CONSTANT\n"
            "    cPi         : LREAL := 3.14159265;\n"
            "    cMaxItems   : UDINT := 1000;\n"
            "    cBufferSize : UINT := 16#FF;\n"
            "    cVersion    : STRING := '1.0.0';\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "16#FF" in result
        assert "'1.0.0'" in result
        assert "LREAL" in result


class TestVarPersistent:

    def test_var_persistent_keyword_casing(self, config):
        code = "var persistent\n    nBootCount : udint;\nend_var"
        result = _format_st_pipeline(code, config)
        assert "VAR PERSISTENT" in result
        assert "UDINT" in result

    def test_var_persistent_alignment(self, config):
        code = (
            "VAR PERSISTENT\n"
            "    nRunHours     : UDINT;\n"
            "    nCycleCount   : ULINT;\n"
            "    dtLastStartup : DT;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR PERSISTENT" in result

    def test_var_persistent_with_init(self, config):
        code = (
            "VAR PERSISTENT\n"
            "    nErrorCount : UDINT := 0;\n"
            "    bFirstRun   : BOOL := TRUE;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "BOOL" in result
        assert "TRUE" in result


class TestVarRetain:

    def test_var_retain_keyword_casing(self, config):
        code = "var retain\n    stState : ST_MachineState;\nend_var"
        result = _format_st_pipeline(code, config)
        assert "VAR RETAIN" in result

    def test_var_retain_alignment(self, config):
        code = (
            "VAR RETAIN\n"
            "    nPosition : DINT;\n"
            "    fSetpoint : REAL;\n"
            "    eMode     : E_OperatingMode;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR RETAIN" in result


# ---------------------------------------------------------------------------
# VAR + combined modifiers
# ---------------------------------------------------------------------------


class TestVarCombinedModifiers:

    def test_var_persistent_retain(self, config):
        code = (
            "VAR PERSISTENT RETAIN\n"
            "    nBootCount    : UDINT;\n"
            "    dtLastPowerOn : DT;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR PERSISTENT RETAIN" in result or "PERSISTENT" in result

    def test_var_retain_persistent(self, config):
        """Both orderings are valid in TwinCAT."""
        code = (
            "var retain persistent\n"
            "    nSavedValue : DINT;\n"
            "end_var"
        )
        result = _format_st_pipeline(code, config)
        assert "RETAIN" in result
        assert "PERSISTENT" in result
        assert "DINT" in result

    def test_var_persistent_retain_with_complex_types(self, config):
        code = (
            "VAR PERSISTENT RETAIN\n"
            "    stConfig  : ST_SystemConfig;\n"
            "    arrParams : ARRAY[0..9] OF REAL;\n"
            "    sHostname : STRING(255);\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..9] OF REAL" in result
        assert "STRING(255)" in result


# ---------------------------------------------------------------------------
# VAR_INPUT / VAR_OUTPUT / VAR_IN_OUT + modifiers
# ---------------------------------------------------------------------------


class TestVarInputOutputModifiers:

    def test_var_input_constant(self, config):
        """VAR_INPUT CONSTANT = read-only input (cannot be written inside FB)."""
        code = (
            "VAR_INPUT CONSTANT\n"
            "    stConfig : ST_Config;\n"
            "    nMaxLen  : UINT;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR_INPUT CONSTANT" in result or ("VAR_INPUT" in result and "CONSTANT" in result)

    def test_var_in_out_constant(self, config):
        """VAR_IN_OUT CONSTANT = read-only by-reference (TwinCAT 3.1.4024+)."""
        code = (
            "VAR_IN_OUT CONSTANT\n"
            "    refData     : ST_LargeDataSet;\n"
            "    refConfig   : ST_SystemConfig;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR_IN_OUT" in result
        assert "CONSTANT" in result

    def test_var_output_retain(self, config):
        code = (
            "VAR_OUTPUT RETAIN\n"
            "    nTotalCount : UDINT;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR_OUTPUT" in result
        assert "RETAIN" in result

    def test_var_input_keyword_casing(self, config):
        code = "var_input constant\n    nMax : uint := 100;\nend_var"
        result = _format_st_pipeline(code, config)
        assert "VAR_INPUT" in result
        assert "CONSTANT" in result
        assert "UINT" in result


# ---------------------------------------------------------------------------
# VAR_GLOBAL + modifiers
# ---------------------------------------------------------------------------


class TestVarGlobalModifiers:

    def test_var_global_constant(self, config):
        code = (
            "VAR_GLOBAL CONSTANT\n"
            "    cSystemVersion : STRING := '2.1.0';\n"
            "    cMaxClients    : UINT := 32;\n"
            "    cTimeout       : TIME := T#30s;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR_GLOBAL CONSTANT" in result or ("VAR_GLOBAL" in result and "CONSTANT" in result)

    def test_var_global_persistent(self, config):
        code = (
            "VAR_GLOBAL PERSISTENT\n"
            "    nGlobalRunHours : ULINT;\n"
            "    stGlobalConfig  : ST_Config;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR_GLOBAL" in result
        assert "PERSISTENT" in result

    def test_var_global_retain(self, config):
        code = (
            "VAR_GLOBAL RETAIN\n"
            "    bSystemInitialized : BOOL;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR_GLOBAL" in result
        assert "RETAIN" in result

    def test_var_global_persistent_retain(self, config):
        code = (
            "VAR_GLOBAL PERSISTENT RETAIN\n"
            "    nMachineHours : ULINT;\n"
            "    nStartCount   : UDINT;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "PERSISTENT" in result
        assert "RETAIN" in result


# ---------------------------------------------------------------------------
# VAR_STAT / VAR_INST / VAR_TEMP + modifiers
# ---------------------------------------------------------------------------


class TestVarStatInstModifiers:

    def test_var_stat_persistent(self, config):
        code = (
            "VAR_STAT PERSISTENT\n"
            "    nCallCount : UDINT;\n"
            "    tLastCall  : TIME;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR_STAT" in result
        assert "PERSISTENT" in result

    def test_var_stat_retain(self, config):
        code = (
            "VAR_STAT RETAIN\n"
            "    nAccumulator : LINT;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR_STAT" in result
        assert "RETAIN" in result

    def test_var_inst_no_modifier(self, config):
        """VAR_INST typically has no modifiers but should still work."""
        code = (
            "VAR_INST\n"
            "    fbInternalTimer : TON;\n"
            "    nInternalState  : INT;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR_INST" in result

    def test_var_temp_no_modifier(self, config):
        """VAR_TEMP cannot have PERSISTENT/RETAIN but must still be recognized."""
        code = (
            "VAR_TEMP\n"
            "    nLocalCalc : INT;\n"
            "    fTempValue : REAL;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "VAR_TEMP" in result


# ---------------------------------------------------------------------------
# Multiple VAR blocks with different modifiers in same POU
# ---------------------------------------------------------------------------


class TestMultipleVarBlocks:

    def test_all_var_types_in_one_pou(self, config):
        """Simulate a realistic FB with many different VAR blocks."""
        code = (
            "VAR_INPUT\n"
            "    bEnable   : BOOL;\n"
            "    nSetpoint : INT;\n"
            "END_VAR\n"
            "VAR_INPUT CONSTANT\n"
            "    stConfig : ST_Config;\n"
            "END_VAR\n"
            "VAR_OUTPUT\n"
            "    bDone    : BOOL;\n"
            "    bError   : BOOL;\n"
            "    nResult  : DINT;\n"
            "END_VAR\n"
            "VAR_IN_OUT\n"
            "    refData : REFERENCE TO ST_Data;\n"
            "END_VAR\n"
            "VAR_IN_OUT CONSTANT\n"
            "    refLargeData : ST_BigBuffer;\n"
            "END_VAR\n"
            "VAR CONSTANT\n"
            "    cMaxRetries : UINT := 5;\n"
            "    cTimeout    : TIME := T#10s;\n"
            "END_VAR\n"
            "VAR PERSISTENT RETAIN\n"
            "    nRunCount : UDINT;\n"
            "END_VAR\n"
            "VAR\n"
            "    _nStep        : INT;\n"
            "    _fbTimer      : TON;\n"
            "    _nRetryCount  : UINT;\n"
            "END_VAR\n"
            "VAR_STAT\n"
            "    nInstanceCount : UDINT;\n"
            "END_VAR\n"
            "VAR_TEMP\n"
            "    nCalc : INT;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)

        # All block headers preserved with correct casing
        assert "VAR_INPUT" in result
        assert "CONSTANT" in result
        assert "VAR_OUTPUT" in result
        assert "VAR_IN_OUT" in result
        assert "PERSISTENT" in result
        assert "RETAIN" in result
        assert "VAR_STAT" in result
        assert "VAR_TEMP" in result

        # All declarations present
        assert "bEnable" in result
        assert "stConfig" in result
        assert "bDone" in result
        assert "refData" in result
        assert "refLargeData" in result
        assert "cMaxRetries" in result
        assert "nRunCount" in result
        assert "_nStep" in result
        assert "nInstanceCount" in result
        assert "nCalc" in result

    def test_alignment_independent_per_block(self, config):
        """Each VAR block should have its own alignment group."""
        code = (
            "VAR_INPUT\n"
            "    bShortName : BOOL;\n"
            "    nVeryLongVariableName : INT;\n"
            "END_VAR\n"
            "VAR CONSTANT\n"
            "    cA : INT := 1;\n"
            "    cLongerName : REAL := 3.14;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        lines = result.split("\n")

        # Find colon positions in each block
        input_colons = []
        const_colons = []
        in_input = False
        in_const = False
        for line in lines:
            su = line.strip().upper()
            if su.startswith("VAR_INPUT"):
                in_input = True
                in_const = False
                continue
            elif "VAR" in su and "CONSTANT" in su:
                in_input = False
                in_const = True
                continue
            elif su.startswith("END_VAR"):
                in_input = False
                in_const = False
                continue

            if ":" in line and ":=" not in line.split(":")[0]:
                colon_idx = line.index(":")
                if in_input:
                    input_colons.append(colon_idx)
                elif in_const:
                    const_colons.append(colon_idx)

        # Within each block, colons should be aligned
        if len(input_colons) >= 2:
            assert len(set(input_colons)) == 1, f"Input colons not aligned: {input_colons}"
        if len(const_colons) >= 2:
            assert len(set(const_colons)) == 1, f"Const colons not aligned: {const_colons}"


# ---------------------------------------------------------------------------
# STRUCT modifiers (inside TYPE declarations)
# ---------------------------------------------------------------------------


class TestStructModifiers:

    def test_type_struct_basic(self, config):
        code = (
            "TYPE ST_Point :\n"
            "STRUCT\n"
            "    fX : REAL;\n"
            "    fY : REAL;\n"
            "    fZ : REAL;\n"
            "END_STRUCT\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        assert "STRUCT" in result
        assert "END_STRUCT" in result
        assert "END_TYPE" in result

    def test_type_struct_alignment(self, config):
        """Variables inside STRUCT should be aligned."""
        code = (
            "TYPE ST_Config :\n"
            "STRUCT\n"
            "    nId : UINT;\n"
            "    sName : STRING(80);\n"
            "    fValue : REAL;\n"
            "    bEnabled : BOOL;\n"
            "END_STRUCT\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        lines = result.split("\n")
        struct_colons = []
        in_struct = False
        for line in lines:
            if "STRUCT" in line.upper() and "END" not in line.upper():
                in_struct = True
                continue
            if "END_STRUCT" in line.upper():
                in_struct = False
                continue
            if in_struct and ":" in line:
                struct_colons.append(line.index(":"))

        if len(struct_colons) >= 2:
            assert len(set(struct_colons)) == 1, f"Struct colons not aligned: {struct_colons}"

    def test_type_struct_extends(self, config):
        """STRUCT with EXTENDS keyword."""
        code = (
            "TYPE ST_ExtendedPoint EXTENDS ST_Point :\n"
            "STRUCT\n"
            "    fW : REAL;\n"
            "END_STRUCT\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        assert "EXTENDS" in result
        assert "ST_Point" in result

    def test_enum_type(self, config):
        """ENUM inside TYPE declaration."""
        code = (
            "TYPE E_State :\n"
            "(\n"
            "    Idle := 0,\n"
            "    Running,\n"
            "    Error := 99\n"
            ");\n"
            "END_TYPE"
        )
        result = _assert_idempotent(code, config)
        assert "Idle" in result
        assert ":= 0" in result
        assert "Running" in result
        assert "Error" in result
        assert ":= 99" in result


# ---------------------------------------------------------------------------
# Edge cases: modifier keyword casing
# ---------------------------------------------------------------------------


class TestModifierCasing:

    def test_all_lowercase_modifiers(self, config):
        code = "var persistent retain\n    n : int;\nend_var"
        result = _format_st_pipeline(code, config)
        assert "VAR" in result
        assert "PERSISTENT" in result
        assert "RETAIN" in result
        assert "INT" in result
        assert "END_VAR" in result

    def test_mixed_case_modifiers(self, config):
        code = "Var_Global Persistent\n    nG : Dint;\nEnd_Var"
        result = _format_st_pipeline(code, config)
        assert "VAR_GLOBAL" in result
        assert "PERSISTENT" in result
        assert "DINT" in result

    def test_constant_in_expression_not_affected(self, config):
        """CONSTANT as modifier vs constant values in code."""
        code = (
            "VAR CONSTANT\n"
            "    cMax : INT := 100;\n"
            "END_VAR\n"
            "IF nValue = cMax THEN\n"
            "    bAtMax := TRUE;\n"
            "END_IF;"
        )
        result = _assert_idempotent(code, config)
        assert "VAR CONSTANT" in result
        assert "cMax" in result


# ---------------------------------------------------------------------------
# Edge case: {attribute} before VAR block with modifier
# ---------------------------------------------------------------------------


class TestAttributeBeforeVarBlock:

    def test_attribute_before_var_constant(self, config):
        code = (
            "{attribute 'qualified_only'}\n"
            "VAR_GLOBAL CONSTANT\n"
            "    cVersion : STRING := '1.0';\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "{attribute 'qualified_only'}" in result
        assert "VAR_GLOBAL" in result
        assert "CONSTANT" in result

    def test_attribute_inside_var_block_with_modifier(self, config):
        code = (
            "VAR PERSISTENT\n"
            "    {attribute 'hide'}\n"
            "    _nInternal : UDINT;\n"
            "    nPublic    : UDINT;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "{attribute 'hide'}" in result
        assert "_nInternal" in result
        assert "nPublic" in result
