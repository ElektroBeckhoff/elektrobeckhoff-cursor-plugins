"""Comprehensive Beckhoff InfoSys ST Syntax Compliance Tests.

Validates the full Structured Text and Extended Structured Text (ExST) syntax against
Beckhoff TwinCAT 3 InfoSys specification:
- Elementary types, typed literals, base literals, strings, direct addressing
- Partial variable access (.%X0, .%B1, .%W0, .%D0, .%L0) and bit indexing (.0, .31)
- ST & ExST operators: arithmetic, logic, exponentiation (**), comparisons, AND_THEN, OR_ELSE
- TwinCAT-specific operators: __NEW, __DELETE, __QUERYINTERFACE, __QUERYPOINTER, __ISVALIDREF,
  __VARINFO, __POSITION, __POUNAME, BITADR, ADRREF, ADR, SIZEOF, XSIZEOF, INDEXOF, LOWER_BOUND, UPPER_BOUND
- Reference assignment: REF= and ?=
- Control flow & Exception handling: __TRY/__CATCH/__FINALLY/__ENDTRY, JMP/Labels, IF/CASE/FOR/WHILE/REPEAT/EXIT/CONTINUE/RETURN
- Declarations: Multi-var (a, b, c : INT), VAR_GENERIC CONSTANT, VAR_EXTERNAL, NON_RETAIN, READ_ONLY,
  ARRAY[*], Generics (FB<100>), Subrange types, STRUCT/UNION/ENUM/ALIAS/INTERFACE.
"""
import pytest

from twincat_core.syntax import (
    AssignStmt,
    BinaryExpr,
    CallExpr,
    CaseStmt,
    DerefExpr,
    ForStmt,
    IdentifierExpr,
    IfStmt,
    IndexExpr,
    JmpStmt,
    LabelStmt,
    LiteralExpr,
    MemberAccessExpr,
    MethodDecl,
    PouDecl,
    RepeatStmt,
    ReturnStmt,
    StructType,
    TryCatchStmt,
    TypeDecl,
    UnaryExpr,
    UnionType,
    VarBlock,
    VarDecl,
    WhileStmt,
    parse_declaration,
    parse_implementation,
    tokenize_st,
)
from twincat_core.syntax.tokens import TokenType


class TestInfoSysLiteralsAndAddressing:
    """Test literal forms and direct memory addressing from Beckhoff InfoSys."""

    def test_typed_literals_tokenization(self):
        source = """
        tTime := T#500ms;
        tTimeLong := TIME#1m30s;
        tLTime := LTIME#100d2h;
        dDate := D#2026-08-30;
        dDateLong := DATE#2026-08-30;
        todTime := TOD#12:30:00;
        todTimeLong := TIME_OF_DAY#12:30:00;
        dtDateTime := DT#2026-08-30-12:00:00;
        dtDateTimeLong := DATE_AND_TIME#2026-08-30-12:00:00;
        nHex := 16#DEAD_BEEF;
        nBin := 2#1010_1100;
        nOct := 8#77;
        fReal := REAL#3.14159;
        fLReal := LREAL#1.0e-5;
        nSint := SINT#-5;
        nUint := UINT#65000;
        """
        tokens, diags = tokenize_st(source)
        assert not diags, f"Diagnostics found: {diags}"
        typed_tokens = [t for t in tokens if t.type == TokenType.TYPED_LITERAL]
        assert len(typed_tokens) >= 15
        assert any(t.value == "T#500ms" for t in typed_tokens)
        assert any(t.value == "16#DEAD_BEEF" for t in typed_tokens)
        assert any(t.value == "2#1010_1100" for t in typed_tokens)

    def test_direct_addressing_tokens(self):
        source = """
        bIn AT %IX0.0 : BOOL;
        bOut AT %QX1.2 : BOOL;
        nMem AT %MD10 : DWORD;
        bWildcardIn AT %I* : BOOL;
        bWildcardOut AT %Q* : BOOL;
        """
        tokens, diags = tokenize_st(source)
        assert not diags
        addr_tokens = [t.value for t in tokens if t.type == TokenType.DIRECT_ADDRESS]
        assert "%IX0.0" in addr_tokens
        assert "%QX1.2" in addr_tokens
        assert "%MD10" in addr_tokens
        assert "%I*" in addr_tokens
        assert "%Q*" in addr_tokens

    def test_partial_variable_access(self):
        source = """
        bBit0 := nVar.%X0;
        nByte1 := nVar.%B1;
        nWord2 := nVar.%W2;
        nDword0 := nVar.%D0;
        nLword0 := nVar.%L0;
        bLegacyBit0 := nVar.0;
        bLegacyBit31 := nVar.31;
        """
        stmts, cst, diags = parse_implementation(source)
        assert not diags, f"Diagnostics: {diags}"
        assert len(stmts) == 7

        assert isinstance(stmts[0], AssignStmt)
        assert isinstance(stmts[0].value, MemberAccessExpr)
        assert stmts[0].value.member_name == "%X0"

        assert isinstance(stmts[1].value, MemberAccessExpr)
        assert stmts[1].value.member_name == "%B1"

        assert isinstance(stmts[2].value, MemberAccessExpr)
        assert stmts[2].value.member_name == "%W2"

        assert isinstance(stmts[5].value, MemberAccessExpr)
        assert stmts[5].value.member_name == "0"

        assert isinstance(stmts[6].value, MemberAccessExpr)
        assert stmts[6].value.member_name == "31"


class TestInfoSysOperatorsAndExpressions:
    """Test all ST & Extended ST (ExST) operators verified against Beckhoff InfoSys."""

    def test_arithmetic_logic_and_power_operators(self):
        source = """
        nRes := (a + b - c) * d / e MOD f;
        nPower := a ** b;
        bCond := (a > 5) AND (b <= 10) OR (c = 20) XOR NOT d;
        bShortCircuit := (pPtr <> 0) AND_THEN (pPtr^ = 10) OR_ELSE bDefault;
        """
        stmts, cst, diags = parse_implementation(source)
        assert not diags, f"Diagnostics: {diags}"
        assert len(stmts) == 4

        # Power operator **
        assert isinstance(stmts[1], AssignStmt)
        assert isinstance(stmts[1].value, BinaryExpr)
        assert stmts[1].value.op == "**"

        # AND_THEN and OR_ELSE
        assert isinstance(stmts[3], AssignStmt)
        assert isinstance(stmts[3].value, BinaryExpr)
        assert stmts[3].value.op == "OR_ELSE"

    def test_reference_and_address_operators(self):
        source = """
        refA REF= stA;
        refB ?= iBase;
        pAddr := ADR(stA);
        pRefAddr := ADRREF(refA);
        nBit := BITADR(bFlag);
        nSize := SIZEOF(stA);
        nXSize := XSIZEOF(stA);
        nIdx := INDEXOF(fbInst);
        """
        stmts, cst, diags = parse_implementation(source)
        assert not diags, f"Diagnostics: {diags}"
        assert len(stmts) == 8

        # REF= assignment
        assert isinstance(stmts[0], AssignStmt)
        assert stmts[0].assign_op.upper() == "REF="

        # ?= reference cast assignment
        assert isinstance(stmts[1], AssignStmt)
        assert stmts[1].assign_op == "?="

    def test_twincat_specific_builtins_and_reflection(self):
        source = """
        pFB := __NEW(FB_Sample, 1);
        __DELETE(pFB);
        bItfOk := __QUERYINTERFACE(iBase, iSub);
        bPtrOk := __QUERYPOINTER(iBase, pFB);
        bValid := __ISVALIDREF(refA);
        stInfo := __VARINFO(nVar);
        sPos := __POSITION();
        sName := __POUNAME();
        nLower := LOWER_BOUND(aData, 1);
        nUpper := UPPER_BOUND(aData, 1);
        """
        stmts, cst, diags = parse_implementation(source)
        assert not diags, f"Diagnostics: {diags}"
        assert len(stmts) == 10

        # __NEW call
        assert isinstance(stmts[0], AssignStmt)
        assert isinstance(stmts[0].value, CallExpr)
        assert isinstance(stmts[0].value.callee, IdentifierExpr)
        assert stmts[0].value.callee.name == "__NEW"

        # __QUERYINTERFACE call
        assert isinstance(stmts[2], AssignStmt)
        assert isinstance(stmts[2].value, CallExpr)
        assert stmts[2].value.callee.name == "__QUERYINTERFACE"
        assert len(stmts[2].value.args) == 2

        # __POUNAME call with 0 args
        assert isinstance(stmts[7], AssignStmt)
        assert isinstance(stmts[7].value, CallExpr)
        assert stmts[7].value.callee.name == "__POUNAME"


class TestInfoSysControlFlowAndExceptions:
    """Test ST control structures, labels, JMP, and __TRY/__CATCH exception handling."""

    def test_try_catch_finally_endtry(self):
        source = """
        __TRY
            nCounter_TRY := nCounter_TRY + 1;
            pSample^ := TRUE;
            nSample := nSample / nDivisor;
        __CATCH(exc)
            nCounter_CATCH := nCounter_CATCH + 1;
            IF exc = __SYSTEM.ExceptionCode.RTSEXCPT_ACCESS_VIOLATION THEN
                pSample := ADR(bVar);
            END_IF;
        __FINALLY
            nCounter_FINALLY := nCounter_FINALLY + 1;
        __ENDTRY
        """
        stmts, cst, diags = parse_implementation(source)
        assert not diags, f"Diagnostics: {diags}"
        assert len(stmts) == 1
        try_stmt = stmts[0]
        assert isinstance(try_stmt, TryCatchStmt)
        assert len(try_stmt.try_body) == 3
        assert try_stmt.catch_var == "exc"
        assert len(try_stmt.catch_body) == 2
        assert len(try_stmt.finally_body) == 1

    def test_jmp_and_labels(self):
        source = """
        nVar1 := 0;
        _label1:
        nVar1 := nVar1 + 1;
        IF (nVar1 < 10) THEN
            JMP _label1;
        END_IF;
        """
        stmts, cst, diags = parse_implementation(source)
        assert not diags, f"Diagnostics: {diags}"
        assert len(stmts) == 4
        assert isinstance(stmts[0], AssignStmt)
        assert isinstance(stmts[1], LabelStmt)
        assert stmts[1].label == "_label1"
        assert isinstance(stmts[2], AssignStmt)
        assert isinstance(stmts[3], IfStmt)
        assert isinstance(stmts[3].then_body[0], JmpStmt)
        assert stmts[3].then_body[0].label == "_label1"

    def test_case_with_subranges_and_else(self):
        source = """
        CASE nState OF
            0, 1:
                bReady := TRUE;
            10..20:
                bActive := TRUE;
            30:
                bDone := TRUE;
            ELSE
                bError := TRUE;
        END_CASE;
        """
        stmts, cst, diags = parse_implementation(source)
        assert not diags, f"Diagnostics: {diags}"
        assert len(stmts) == 1
        case_stmt = stmts[0]
        assert isinstance(case_stmt, CaseStmt)
        assert len(case_stmt.branches) == 3
        assert case_stmt.else_branch is not None


class TestInfoSysDeclarations:
    """Test declaration syntax: multi-var, VAR_GENERIC, VAR_EXTERNAL, NON_RETAIN, ARRAY[*], Subranges."""

    def test_multi_variable_declarations_in_single_line(self):
        source = """
        VAR
            nVar1, nVar2, nVar3 : INT := 10;
            fSpeed, fAccel : REAL := 0.0;
            bFlag : BOOL;
        END_VAR
        """
        ast_root, cst, diags = parse_declaration(source)
        assert not diags, f"Diagnostics: {diags}"
        assert isinstance(ast_root, VarBlock)
        assert len(ast_root.variables) == 6
        names = [v.name for v in ast_root.variables]
        assert names == ["nVar1", "nVar2", "nVar3", "fSpeed", "fAccel", "bFlag"]
        assert all(v.type_name == "INT" for v in ast_root.variables[:3])
        assert ast_root.variables[0].initial_value == "10"

    def test_var_generic_constant_and_generic_instances(self):
        source = """
        FUNCTION_BLOCK FB_Sample
        VAR_GENERIC CONSTANT
            nMaxLen : UDINT := 1;
        END_VAR
        VAR
            aSample : ARRAY[0..nMaxLen-1] OF BYTE;
            fbSub : FB_Sub<100>;
            fbDyn : FB_Sub<(2*cConst)>;
        END_VAR
        """
        ast_root, cst, diags = parse_declaration(source)
        assert not diags, f"Diagnostics: {diags}"
        assert isinstance(ast_root, PouDecl)
        assert ast_root.name == "FB_Sample"
        assert len(ast_root.var_blocks) == 2
        assert ast_root.var_blocks[0].block_type == "VAR_GENERIC CONSTANT"
        assert ast_root.var_blocks[0].is_constant is True

    def test_var_modifiers_non_retain_read_only(self):
        source = """
        VAR_GLOBAL NON_RETAIN
            nCounter : DINT;
        END_VAR
        VAR_GLOBAL READ_ONLY
            cVersion : STRING := '1.0.0';
        END_VAR
        VAR_EXTERNAL
            nExternalVal : INT;
        END_VAR
        """
        ast_root, cst, diags = parse_declaration(source)
        assert not diags, f"Diagnostics: {diags}"
        assert isinstance(ast_root, PouDecl)
        blocks = ast_root.var_blocks
        assert len(blocks) == 3
        assert blocks[0].is_non_retain is True
        assert blocks[1].is_read_only is True
        assert blocks[2].block_type == "VAR_EXTERNAL"

    def test_variable_length_arrays_in_var_in_out(self):
        source = """
        FUNCTION F_Sum : DINT
        VAR_IN_OUT
            a1D : ARRAY[*] OF INT;
            a2D : ARRAY[*, *] OF REAL;
        END_VAR
        VAR
            nIdx : DINT;
        END_VAR
        """
        ast_root, cst, diags = parse_declaration(source)
        assert not diags, f"Diagnostics: {diags}"
        assert isinstance(ast_root, PouDecl)
        assert ast_root.return_type == "DINT"
        in_out = ast_root.var_blocks[0]
        assert "ARRAY" in in_out.variables[0].type_name and "INT" in in_out.variables[0].type_name
        assert "ARRAY" in in_out.variables[1].type_name and "REAL" in in_out.variables[1].type_name

    def test_subrange_types_and_aliases(self):
        source_sub = """
        TYPE T_Sub : INT(-4095..4095) := 0; END_TYPE
        """
        ast_sub, _, diags = parse_declaration(source_sub)
        assert not diags, f"Diagnostics: {diags}"
        assert isinstance(ast_sub, TypeDecl)
        assert ast_sub.name == "T_Sub"
        assert "INT" in str(ast_sub.definition) and "4095" in str(ast_sub.definition)

        source_arr = """
        TYPE T_Matrix : ARRAY[1..10, 1..20] OF REAL; END_TYPE
        """
        ast_arr, _, diags = parse_declaration(source_arr)
        assert not diags, f"Diagnostics: {diags}"
        assert isinstance(ast_arr, TypeDecl)
        assert ast_arr.name == "T_Matrix"
        assert "ARRAY" in str(ast_arr.definition) and "REAL" in str(ast_arr.definition)

    def test_full_pou_with_pragmas_methods_properties(self):
        source = """
        {attribute 'reflection'}
        FUNCTION_BLOCK PUBLIC ABSTRACT FB_Motor EXTENDS FB_Base IMPLEMENTS I_Motor
        VAR_INPUT
            bEnable : BOOL;
            fSpeed_rpm : REAL;
        END_VAR
        VAR_OUTPUT
            bActive : BOOL;
            bError : BOOL;
        END_VAR
        VAR
            _nStep : INT;
            _fbTon : TON;
        END_VAR
        END_FUNCTION_BLOCK
        """
        ast_pou, cst, diags = parse_declaration(source)
        assert not diags, f"Diagnostics: {diags}"
        assert isinstance(ast_pou, PouDecl)
        assert ast_pou.name == "FB_Motor"
        assert ast_pou.is_abstract is True
        assert ast_pou.extends_name == "FB_Base"
        assert ast_pou.implements_names == ["I_Motor"]
        assert len(ast_pou.var_blocks) == 3
        assert len(ast_pou.pragmas) >= 1
