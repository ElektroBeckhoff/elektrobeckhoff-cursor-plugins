"""Comprehensive tests for twincat_core.syntax (Lexer, CST, AST, Spans, and Fault Tolerance)."""
import pytest

from twincat_core.syntax import (
    AssignStmt,
    BinaryExpr,
    CallStmt,
    CaseStmt,
    DeclarationParser,
    EnumType,
    ForStmt,
    IdentifierExpr,
    IfStmt,
    InterfaceDecl,
    Lexer,
    LiteralExpr,
    MemberAccessExpr,
    MethodDecl,
    PouDecl,
    Position,
    RepeatStmt,
    ReturnStmt,
    SourceSpan,
    StatementParser,
    StructType,
    TokenType,
    TypeDecl,
    VarBlock,
    WhileStmt,
    parse_declaration,
    parse_implementation,
    tokenize_st,
)


# =========================================================================
# 1. Lexer & Trivia Tests
# =========================================================================

class TestLexer:
    def test_lexer_all_token_types(self):
        source = """// Line comment
(* Multi-line
   nested (* block *) comment *)
{attribute 'hide'}
FUNCTION_BLOCK FB_Test EXTENDS FB_Base IMPLEMENTS I_Test
VAR_INPUT
    bEnable : BOOL := TRUE;
    fValue  : REAL := 12.34;
    sMsg    : STRING := 'Hello $N World';
    wsWide  : WSTRING := "Unicode string";
    tDelay  : TIME := T#500ms;
    nHex    : WORD := 16#FF_AA;
    nBin    : BYTE := 2#1010_0101;
    %I*     : BOOL;
END_VAR
"""
        tokens, diags = tokenize_st(source, include_trivia=True)
        assert len(diags) == 0

        # Verify token sequence preservation and source reconstruction
        reconstructed = "".join(t.value for t in tokens if t.type != TokenType.EOF)
        assert reconstructed == source

        # Check specific tokens found
        types = [t.type for t in tokens]
        assert TokenType.LINE_COMMENT in types
        assert TokenType.BLOCK_COMMENT in types
        assert TokenType.PRAGMA in types
        assert TokenType.KEYWORD_FUNCTION_BLOCK in types
        assert TokenType.KEYWORD_EXTENDS in types
        assert TokenType.KEYWORD_IMPLEMENTS in types
        assert TokenType.TYPED_LITERAL in types
        assert TokenType.DIRECT_ADDRESS in types

    def test_lexer_operators_and_punctuators(self):
        source = "x := y + 10 * (z - 2) / 3.14 <= 100 AND bFlag <> FALSE OR_ELSE NOT ptr^.member[1];"
        tokens, diags = tokenize_st(source, include_trivia=False)
        assert len(diags) == 0
        expected_types = [
            TokenType.IDENTIFIER,        # x
            TokenType.ASSIGN,            # :=
            TokenType.IDENTIFIER,        # y
            TokenType.PLUS,              # +
            TokenType.INT_LITERAL,       # 10
            TokenType.STAR,              # *
            TokenType.PAREN_OPEN,        # (
            TokenType.IDENTIFIER,        # z
            TokenType.MINUS,             # -
            TokenType.INT_LITERAL,       # 2
            TokenType.PAREN_CLOSE,       # )
            TokenType.SLASH,             # /
            TokenType.REAL_LITERAL,      # 3.14
            TokenType.LE,                # <=
            TokenType.INT_LITERAL,       # 100
            TokenType.KEYWORD_AND,       # AND
            TokenType.IDENTIFIER,        # bFlag
            TokenType.NE,                # <>
            TokenType.BOOL_LITERAL,      # FALSE
            TokenType.KEYWORD_OR_ELSE,   # OR_ELSE
            TokenType.KEYWORD_NOT,       # NOT
            TokenType.IDENTIFIER,        # ptr
            TokenType.POINTER_DEREF,     # ^
            TokenType.DOT,               # .
            TokenType.IDENTIFIER,        # member
            TokenType.BRACKET_OPEN,      # [
            TokenType.INT_LITERAL,       # 1
            TokenType.BRACKET_CLOSE,     # ]
            TokenType.SEMICOLON,         # ;
            TokenType.EOF,
        ]
        assert [t.type for t in tokens] == expected_types

    def test_lexer_fault_tolerance(self):
        # Unterminated block comment and string
        source = "VAR b : BOOL; (* unterminated comment \n s := 'unterminated;"
        tokens, diags = tokenize_st(source, include_trivia=True)
        assert len(diags) >= 1
        assert any("Unterminated" in d.message for d in diags)
        # Lexer still produces tokens without crashing
        assert len(tokens) > 0


# =========================================================================
# 2. Declaration Parsing Tests (POU, METHOD, TYPE, STRUCT, ENUM, GVL)
# =========================================================================

class TestDeclarationParsing:
    def test_parse_pou_declaration_with_var_blocks(self):
        source = """{attribute 'reflection'}
FUNCTION_BLOCK PUBLIC FB_Sensor EXTENDS FB_Device IMPLEMENTS I_Sensor, I_Device
VAR_INPUT
    bEnable : BOOL := TRUE;
    {attribute 'TcEncoding' := 'UTF-8'}
    sName : STRING(50);
END_VAR
VAR_OUTPUT
    fMeasurement : REAL;
    bError : BOOL;
END_VAR
VAR
    _nStep : INT := 0;
    _fbTimer : TON;
END_VAR
END_FUNCTION_BLOCK
"""
        ast_node, cst_nodes, diags = parse_declaration(source)
        assert len(diags) == 0
        assert isinstance(ast_node, PouDecl)
        assert ast_node.name == "FB_Sensor"
        assert ast_node.pou_type == "FUNCTION_BLOCK"
        assert ast_node.extends_name == "FB_Device"
        assert ast_node.implements_names == ["I_Sensor", "I_Device"]
        assert len(ast_node.var_blocks) == 3
        assert ast_node.var_blocks[0].block_type == "VAR_INPUT"
        assert len(ast_node.var_blocks[0].variables) == 2
        assert ast_node.var_blocks[0].variables[0].name == "bEnable"
        assert ast_node.var_blocks[0].variables[0].type_name == "BOOL"
        assert ast_node.var_blocks[0].variables[0].initial_value == "TRUE"
        assert len(ast_node.pragmas) >= 1
        assert ast_node.span.start.line == 1

    def test_parse_method_declaration(self):
        source = """METHOD PUBLIC M_Calculate : LREAL
VAR_INPUT
    fIn1 : LREAL;
    fIn2 : LREAL;
END_VAR
VAR
    fTemp : LREAL;
END_VAR
"""
        ast_node, cst_nodes, diags = parse_declaration(source)
        assert len(diags) == 0
        assert isinstance(ast_node, MethodDecl)
        assert ast_node.name == "M_Calculate"
        assert ast_node.return_type == "LREAL"
        assert ast_node.access_modifier == "PUBLIC"
        assert len(ast_node.var_blocks) == 2

    def test_parse_interface_declaration(self):
        source = """INTERFACE I_Motor EXTENDS I_Device, I_Actuator
"""
        ast_node, cst_nodes, diags = parse_declaration(source)
        assert len(diags) == 0
        assert isinstance(ast_node, InterfaceDecl)
        assert ast_node.name == "I_Motor"
        assert ast_node.extends_interfaces == ["I_Device", "I_Actuator"]

    def test_parse_struct_type(self):
        source = """TYPE ST_Header EXTENDS ST_Base :
STRUCT
    nId : UDINT;
    sTopic : STRING(80);
    arrPayload : ARRAY[0..99] OF BYTE;
END_STRUCT
END_TYPE
"""
        ast_node, cst_nodes, diags = parse_declaration(source)
        assert len(diags) == 0
        assert isinstance(ast_node, TypeDecl)
        assert ast_node.name == "ST_Header"
        assert ast_node.extends_type == "ST_Base"
        assert isinstance(ast_node.definition, StructType)
        assert len(ast_node.definition.fields) == 3
        assert ast_node.definition.fields[0].name == "nId"
        assert ast_node.definition.fields[0].type_name == "UDINT"
        assert ast_node.definition.fields[2].name == "arrPayload"
        assert ast_node.definition.fields[2].type_name == "ARRAY [ 0 .. 99 ] OF BYTE"

    def test_parse_enum_type(self):
        source = """{attribute 'qualified_only'}
TYPE E_State :
(
    Init := 0,
    Running := 10,
    Error := 99
) DINT := Init;
END_TYPE
"""
        ast_node, cst_nodes, diags = parse_declaration(source)
        assert len(diags) == 0
        assert isinstance(ast_node, TypeDecl)
        assert ast_node.name == "E_State"
        assert isinstance(ast_node.definition, EnumType)
        assert ast_node.definition.base_type == "DINT"
        assert len(ast_node.definition.members) == 3
        assert ast_node.definition.members[0].name == "Init"
        assert ast_node.definition.members[0].value == "0"
        assert ast_node.definition.members[1].name == "Running"
        assert ast_node.definition.members[1].value == "10"

    def test_parse_gvl_var_blocks(self):
        source = """VAR_GLOBAL CONSTANT
    cMaxBuffer : UDINT := 4096;
    cVersion   : STRING := '1.0.0';
END_VAR
VAR_GLOBAL
    g_bSystemReady : BOOL;
END_VAR
"""
        ast_node, cst_nodes, diags = parse_declaration(source)
        assert len(diags) == 0
        # Multi-block GVL wrapped in synthetic container
        assert isinstance(ast_node, PouDecl)
        assert len(ast_node.var_blocks) == 2
        assert ast_node.var_blocks[0].is_constant is True
        assert len(ast_node.var_blocks[0].variables) == 2
        assert ast_node.var_blocks[1].variables[0].name == "g_bSystemReady"


# =========================================================================
# 3. Statement & Expression Parsing Tests
# =========================================================================

class TestStatementParsing:
    def test_parse_assignment_and_calls(self):
        source = """
        x := y + 10;
        fbTon(IN := bStart, PT => tPreset);
        stData.nStatus := E_State.Running;
        arrBuffer[nIndex] := pData^;
        """
        stmts, cst_nodes, diags = parse_implementation(source)
        assert len(diags) == 0
        assert len(stmts) == 4

        # 1. Assignment
        assert isinstance(stmts[0], AssignStmt)
        assert isinstance(stmts[0].target, IdentifierExpr)
        assert stmts[0].target.name == "x"
        assert isinstance(stmts[0].value, BinaryExpr)

        # 2. Call
        assert isinstance(stmts[1], CallStmt)
        assert stmts[1].call.callee.name == "fbTon"
        assert len(stmts[1].call.args) == 2
        assert stmts[1].call.args[0].name == "IN"
        assert stmts[1].call.args[1].name == "PT"
        assert stmts[1].call.args[1].assign_op == "=>"

        # 3. Member access
        assert isinstance(stmts[2], AssignStmt)
        assert isinstance(stmts[2].target, MemberAccessExpr)

        # 4. Array indexing and pointer deref
        assert isinstance(stmts[3], AssignStmt)

    def test_parse_if_elsif_else(self):
        source = """
        IF nVal > 100 THEN
            bHigh := TRUE;
        ELSIF nVal < 0 THEN
            bLow := TRUE;
        ELSE
            bNormal := TRUE;
        END_IF;
        """
        stmts, cst_nodes, diags = parse_implementation(source)
        assert len(diags) == 0
        assert len(stmts) == 1
        if_stmt = stmts[0]
        assert isinstance(if_stmt, IfStmt)
        assert len(if_stmt.then_body) == 1
        assert len(if_stmt.elsifs) == 1
        assert if_stmt.else_branch is not None
        assert len(if_stmt.else_branch.body) == 1

    def test_parse_case_statement(self):
        source = """
        CASE _nStep OF
            0:
                bReady := FALSE;
            10, 20:
                bBusy := TRUE;
            30..50:
                bProcessing := TRUE;
            ELSE
                bError := TRUE;
        END_CASE;
        """
        stmts, cst_nodes, diags = parse_implementation(source)
        assert len(diags) == 0
        assert len(stmts) == 1
        case_stmt = stmts[0]
        assert isinstance(case_stmt, CaseStmt)
        assert len(case_stmt.branches) == 3
        assert case_stmt.else_branch is not None

    def test_parse_loops_for_while_repeat(self):
        source = """
        FOR i := 0 TO 9 BY 2 DO
            arr[i] := i * 10;
        END_FOR;

        WHILE bActive DO
            nCount := nCount + 1;
            IF nCount > 100 THEN
                EXIT;
            END_IF;
        END_WHILE;

        REPEAT
            nVal := nVal - 1;
        UNTIL nVal <= 0
        END_REPEAT;
        """
        stmts, cst_nodes, diags = parse_implementation(source)
        assert len(diags) == 0
        assert len(stmts) == 3
        assert isinstance(stmts[0], ForStmt)
        assert stmts[0].loop_var == "i"
        assert isinstance(stmts[1], WhileStmt)
        assert isinstance(stmts[2], RepeatStmt)


# =========================================================================
# 4. Fault-Tolerance and Recovery Tests
# =========================================================================

class TestFaultTolerance:
    def test_declaration_recovery_on_missing_colon(self):
        source = """
        VAR
            bValid : BOOL := TRUE;
            bBroken BOOL; (* missing colon *)
            bAfter : INT := 42;
        END_VAR
        """
        ast_node, cst_nodes, diags = parse_declaration(source)
        assert len(diags) >= 1
        assert any("Expected ':'" in d.message for d in diags)
        assert isinstance(ast_node, VarBlock)
        # Should have successfully parsed bValid and recovered to parse bAfter
        var_names = [v.name for v in ast_node.variables]
        assert "bValid" in var_names
        assert "bAfter" in var_names

    def test_statement_recovery_on_syntax_error(self):
        source = """
        x := 10;
        THIS IS INVALID CODE GARBAGE HERE !!! ;
        y := 20;
        """
        stmts, cst_nodes, diags = parse_implementation(source)
        # Diagnostics collected
        assert len(diags) >= 1
        # Parser does not crash and recovers after semicolon to parse y := 20
        assert len(stmts) >= 2
        assert isinstance(stmts[0], AssignStmt)
        assert isinstance(stmts[-1], AssignStmt)
        assert stmts[-1].target.name == "y"


# =========================================================================
# 5. Syntax Edge Cases & False Positive Elimination Tests
# =========================================================================

class TestSyntaxEdgeCasesAndNoFalsePositives:
    def test_chained_assignments_parse_cleanly(self):
        source = """
        bCmdA := bCmdB := FALSE;
        bCmdA := bCmdB := TRUE;
        nVal1 := nVal2 := nVal3 := 42;
        """
        stmts, cst_nodes, diags = parse_implementation(source)
        assert len(diags) == 0, f"Unexpected diagnostics in chained assignments: {diags}"
        assert len(stmts) == 3
        assert isinstance(stmts[0], AssignStmt)
        assert isinstance(stmts[0].value, BinaryExpr)
        assert stmts[0].value.op == ":="

    def test_nested_case_statements_parse_cleanly(self):
        source = """
        case nSelector of
        1, 2, 3:
            nResult := 10;
        4..7:
            case nSub of
            0:
                nResult := 20;
            1..3:
                nResult := 30;
            else
                nResult := -1;
            end_case
        8..10, 15:
            nResult := 40;
        else
            nResult := 0;
        end_case
        """
        stmts, cst_nodes, diags = parse_implementation(source)
        assert len(diags) == 0, f"Unexpected diagnostics in nested case: {diags}"
        assert len(stmts) == 1
        assert isinstance(stmts[0], CaseStmt)
        assert len(stmts[0].branches) == 3

    def test_array_of_fb_with_fb_init_params_and_inits(self):
        source = """
        VAR
            arrFbInitSingleLine : ARRAY[1..2] OF FB_Syntax_FBInitMethods[(nInitialId := 1, sInitialName := 'MotorA'), (nInitialId := 2, sInitialName := 'MotorB')];
            arrStructSingleLine : ARRAY[1..2] OF ST_Syntax_Mini := [(nId := 1, bActive := TRUE), (nId := 2, bActive := FALSE)];
        END_VAR
        """
        ast_node, cst_nodes, diags = parse_declaration(source)
        assert len(diags) == 0, f"Unexpected diagnostics in FB_init array: {diags}"
        assert isinstance(ast_node, VarBlock)
        assert len(ast_node.variables) == 2
        assert "FB_Syntax_FBInitMethods" in ast_node.variables[0].type_name
        assert "nInitialId := 1" in ast_node.variables[0].type_name

    def test_typed_enum_with_negative_values_and_defaults(self):
        source = """
        TYPE E_Syntax_TypedExplicit : (
            Idle       := 0,
            Starting   := 10,
            Running    := 100,
            FatalError := -1
        ) DINT := Idle;
        END_TYPE
        """
        ast_node, cst_nodes, diags = parse_declaration(source)
        assert len(diags) == 0, f"Unexpected diagnostics in enum: {diags}"
        assert isinstance(ast_node, TypeDecl)
        assert ast_node.definition.base_type == "DINT"
        assert len(ast_node.definition.members) == 4
        assert ast_node.definition.members[-1].value == "- 1" or ast_node.definition.members[-1].value == "-1"

    def test_var_config_dotted_variable_names(self):
        source = """
        VAR_CONFIG
            MAIN.fbMotor.bEnable AT %QX0.0 : BOOL;
            MAIN.fbMotor.nSpeed  AT %QW2   : INT;
        END_VAR
        """
        ast_node, cst_nodes, diags = parse_declaration(source)
        assert len(diags) == 0, f"Unexpected diagnostics in VAR_CONFIG: {diags}"
        assert isinstance(ast_node, VarBlock)
        assert len(ast_node.variables) == 2
        assert ast_node.variables[0].name == "MAIN.fbMotor.bEnable"
        assert ast_node.variables[1].name == "MAIN.fbMotor.nSpeed"


# =========================================================================
# 6. Exhaustive Syntax & ExST Language Features Battery
# =========================================================================

class TestExhaustiveSyntaxAndExSTEdgeCases:
    @pytest.mark.parametrize(
        "code,is_decl",
        [
            # Pragmas inside declaration & implementation
            (
                """
                {attribute 'qualified_only'}
                {attribute 'strict'}
                VAR_GLOBAL CONSTANT
                    {attribute 'hide'}
                    cMaxVal : INT := 100;
                    {region 'Config Section'}
                    cConfigVal : DINT := 16#FFFF;
                    {endregion}
                END_VAR
                """,
                True,
            ),
            # ExST Dynamic memory allocation and pointers
            (
                """
                pMotor := __NEW(FB_Motor, nInitId := 10);
                IF pMotor <> 0 THEN
                    pMotor^.M_Start();
                    __DELETE(pMotor);
                END_IF;
                """,
                False,
            ),
            # ExST QueryInterface, QueryPointer, IsValidRef, Position macros
            (
                """
                __QUERYINTERFACE(iDevice, iWidget);
                __QUERYPOINTER(iDevice, pMotor);
                bValid := __ISVALIDREF(refA);
                sName := __POUNAME();
                sPos := __POSITION__();
                """,
                False,
            ),
            # ExST Interlocked functions
            (
                """
                __XADD(ADR(_nAtomicVal), 1);
                TEST_AND_SET(_dwSpinLock);
                """,
                False,
            ),
            # Multidimensional array indexing and slice/deref chains
            (
                """
                arrMatrix[nRow, nCol] := 42;
                pStructArray^[nIdx].stNested.arrData[1, 2] := 100;
                arr3D[1, 2, 3] := arr3D[3, 2, 1] + 1;
                """,
                False,
            ),
            # Method chaining with arguments
            (
                """
                fbBuilder.SetGain(1.5).SetOffset(0.0).Build();
                pBase^.M_Execute(bStart := TRUE).M_Reset();
                """,
                False,
            ),
            # Unary not, minus, plus, deref, bit access
            (
                """
                bFlag := NOT bIn;
                nNeg := -nVal;
                nPos := +nVal;
                bBit := nWord.%X0;
                nByte := nDword.%B1;
                nBitLegacy := nWord.0;
                """,
                False,
            ),
            # All binary operators
            (
                """
                x := a AND b OR c XOR d AND_THEN e OR_ELSE f;
                bCmp := (x = y) AND (x <> y) AND (x < y) AND (x <= y) AND (x > y) AND (x >= y);
                nMath := (a + b - c * d / e MOD f) ** 2;
                """,
                False,
            ),
            # Bounds operators
            (
                """
                nLower := LOWER_BOUND(arrData, 1);
                nUpper := UPPER_BOUND(arrData, 1);
                """,
                False,
            ),
            # Repeat / While / For / If / Case combinations
            (
                """
                FOR i := 1 TO 10 BY 2 DO
                    IF i = 5 THEN
                        CONTINUE;
                    ELSIF i = 9 THEN
                        EXIT;
                    END_IF;
                END_FOR;

                WHILE bRunning DO
                    nCnt := nCnt + 1;
                    IF nCnt > 100 THEN
                        RETURN;
                    END_IF;
                END_WHILE;

                REPEAT
                    nCnt := nCnt - 1;
                UNTIL nCnt <= 0
                END_REPEAT;
                """,
                False,
            ),
            # Empty statements and standalone semicolons
            (
                """
                ;
                ;
                nVal := 1;
                ;
                """,
                False,
            ),
            # JMP and Labels
            (
                """
                JMP JumpTarget;
                JumpTarget:
                nVal := 10;
                100:
                nVal := 20;
                """,
                False,
            ),
            # Interface declaration with multiple EXTENDS
            (
                """
                INTERFACE I_Advanced EXTENDS I_Base1, I_Base2
                """,
                True,
            ),
            # Function declaration with modifiers and return type
            (
                """
                FUNCTION INTERNAL F_Calculate : LREAL
                VAR_INPUT
                    fParamA : LREAL;
                    fParamB : LREAL;
                END_VAR
                """,
                True,
            ),
            # POU with EXTENDS and multiple IMPLEMENTS
            (
                """
                FUNCTION_BLOCK PUBLIC ABSTRACT FB_SpecialDevice EXTENDS FB_BaseDevice IMPLEMENTS I_Device, I_Diagnostics, I_Observer
                VAR_INPUT
                    bEnable : BOOL;
                END_VAR
                VAR_OUTPUT
                    bActive : BOOL;
                END_VAR
                VAR
                    _nState : INT;
                END_VAR
                """,
                True,
            ),
            # Subrange type definition
            (
                """
                TYPE T_Subrange : INT(1..100) := 50;
                END_TYPE
                """,
                True,
            ),
            # Multi-dimensional array alias
            (
                """
                TYPE T_Matrix3D : ARRAY[1..3, 1..4, 1..5] OF LREAL;
                END_TYPE
                """,
                True,
            ),
            # Union declaration
            (
                """
                TYPE U_ByteWord :
                UNION
                    nWord : WORD;
                    stBytes : ARRAY[0..1] OF BYTE;
                END_UNION
                END_TYPE
                """,
                True,
            ),
            # Struct with EXTENDS
            (
                """
                TYPE ST_ExtendedConfig EXTENDS ST_BaseConfig :
                STRUCT
                    fGain : REAL := 1.0;
                    sDescription : STRING(80);
                END_STRUCT
                END_TYPE
                """,
                True,
            ),
            # Varied literals (binary, hex, typed time, typed date, ltime)
            (
                """
                nBin := 2#1010_1100;
                nHex := 16#DEAD_BEEF;
                nOct := 8#77;
                tDuration := T#1D2H3M4S5MS;
                tShort := TIME#500MS;
                ltDuration := LTIME#1000NS;
                dDate := DATE#2026-08-30;
                todTime := TOD#15:30:00;
                dtDateTime := DT#2026-08-30-15:30:00;
                """,
                False,
            ),
            # Function call returning pointer/interface and chained access
            (
                """
                F_GetDevice().M_Start();
                F_GetPointer()^ := 20;
                F_GetArray()[1] := 10;
                F_GetDevice().pNested^.field := 5;
                """,
                False,
            ),
            # Comments inside calls and expressions
            (
                """
                fbMotor(
                    (* enable *)
                    bEnable := TRUE, // inline comment
                    nSpeed := 1000
                );
                """,
                False,
            ),
            # Nested struct and array initializations
            (
                """
                VAR
                    stComplex : ST_Complex := (
                        nId := 1,
                        arrSub := [1, 2, 3],
                        stNested := (sName := 'Test', bFlag := TRUE)
                    );
                END_VAR
                """,
                True,
            ),
            # SUPER^ and THIS^ calls and method invocations
            (
                """
                SUPER^();
                SUPER^.M_Init(bStart := TRUE);
                THIS^.M_LocalAction();
                THIS^.fbSubTimer(IN := TRUE);
                """,
                False,
            ),
            # Pragmas inside IF and CASE bodies
            (
                """
                IF bFlag THEN
                    {region 'Nested Logic'}
                    x := 10;
                    {endregion}
                END_IF;
                """,
                False,
            ),
            # Bit access in complex expressions
            (
                """
                bFlag := stData.arrWords[i].%X5 OR (pWord^.%B0 = 16#FF);
                """,
                False,
            ),
            # Multiple statements on single line
            (
                """
                a := 1; b := 2; c := 3; IF a = 1 THEN b := 10; END_IF;
                """,
                False,
            ),
            # Chained relational / boolean expressions
            (
                """
                bValid := a < b AND b < c AND (c = d OR NOT e);
                """,
                False,
            ),
        ],
    )
    def test_syntax_battery_produces_zero_diagnostics(self, code: str, is_decl: bool):
        if is_decl:
            ast_node, cst_nodes, diags = parse_declaration(code)
            assert not diags, f"Unexpected declaration diagnostics: {diags}"
            assert ast_node is not None or len(cst_nodes) > 0
        else:
            stmts, cst_nodes, diags = parse_implementation(code)
            assert not diags, f"Unexpected implementation diagnostics: {diags}"
            assert len(stmts) > 0


# =========================================================================
# 5. Real Syntax Error Detection Battery (IEC 61131-3 & TwinCAT 3 Verification)
# =========================================================================

class TestSyntaxErrorDiagnostics:
    def test_function_requires_return_type(self):
        decl = "FUNCTION F_NoReturnType\nVAR_INPUT\n    nIn : INT;\nEND_VAR\n"
        _, _, diags = parse_declaration(decl)
        assert any(d.code == "TC-DECL-001" for d in diags)

    def test_property_requires_data_type(self):
        decl = "PROPERTY PropNoType\nVAR\n    _nVal : INT;\nEND_VAR\n"
        _, _, diags = parse_declaration(decl)
        assert any(d.code == "TC-DECL-002" for d in diags)

    def test_constant_requires_initial_value(self):
        decl = "VAR CONSTANT\n    cMaxRetries : INT;\nEND_VAR\n"
        _, _, diags = parse_declaration(decl)
        assert any(d.code == "TC-DECL-003" for d in diags)

    def test_var_in_out_cannot_have_initial_value(self):
        decl = "VAR_IN_OUT\n    stBuffer : ST_Data := (nId := 1);\nEND_VAR\n"
        _, _, diags = parse_declaration(decl)
        assert any(d.code == "TC-DECL-004" for d in diags)

    def test_var_temp_cannot_be_retain(self):
        decl = "VAR_TEMP RETAIN\n    nTemp : INT;\nEND_VAR\n"
        _, _, diags = parse_declaration(decl)
        assert any(d.code == "TC-DECL-005" for d in diags)

    def test_array_lower_bound_exceeds_upper_bound(self):
        decl = "VAR\n    arrInvalid : ARRAY[10..1] OF INT;\nEND_VAR\n"
        _, _, diags = parse_declaration(decl)
        assert any(d.code == "TC-DECL-007" for d in diags)

    def test_exit_outside_loop_diagnostics(self):
        code = "nVal := 10;\nEXIT;\n"
        _, _, diags = parse_implementation(code)
        assert any(d.code == "TC-STMT-001" for d in diags)

    def test_continue_outside_loop_diagnostics(self):
        code = "nVal := 20;\nCONTINUE;\n"
        _, _, diags = parse_implementation(code)
        assert any(d.code == "TC-STMT-002" for d in diags)

    def test_undefined_jmp_label_diagnostics(self):
        code = "IF bError THEN\n    JMP StepError;\nEND_IF;\n"
        _, _, diags = parse_implementation(code)
        assert any(d.code == "TC-STMT-004" for d in diags)

    def test_defined_jmp_label_produces_zero_diagnostics(self):
        code = "IF bError THEN\n    JMP StepError;\nEND_IF;\n\nStepError:\nnState := 99;\n"
        _, _, diags = parse_implementation(code)
        assert not diags

    def test_invalid_assignment_target_literal_diagnostics(self):
        code = "10 := nVal;\n"
        _, _, diags = parse_implementation(code)
        assert any(d.code == "TC-EXPR-002" for d in diags)

