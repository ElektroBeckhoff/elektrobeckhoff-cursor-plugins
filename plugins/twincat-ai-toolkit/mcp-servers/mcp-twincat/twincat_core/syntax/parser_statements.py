"""Fault-tolerant Pratt parser for IEC 61131-3 ST expressions and statements."""
from __future__ import annotations

from typing import List, Optional, Tuple

from .ast import (
    AddressOfExpr,
    AssignStmt,
    BinaryExpr,
    CallArg,
    CallExpr,
    CallStmt,
    CaseBranch,
    CaseStmt,
    ContinueStmt,
    DerefExpr,
    ElseBranch,
    ElsifBranch,
    EmptyStmt,
    ErrorExpr,
    ErrorStmt,
    ExitStmt,
    Expression,
    ForStmt,
    IdentifierExpr,
    IfStmt,
    IndexExpr,
    JmpStmt,
    LabelStmt,
    LiteralExpr,
    MemberAccessExpr,
    RangeExpr,
    RepeatStmt,
    ReturnStmt,
    Statement,
    TryCatchStmt,
    UnaryExpr,
    WhileStmt,
)
from .cst import CstNode, CstNodeKind
from .diagnostics import DiagnosticSeverity, SyntaxDiagnostic
from .lexer import Lexer
from .span import SourceSpan
from .tokens import Token, TokenType


class StatementParser:
    """Parses ST statements and expressions with fault tolerance and recovery."""

    def __init__(self, tokens: list[Token], diagnostics: list[SyntaxDiagnostic]) -> None:
        self.all_tokens = tokens
        self.diagnostics = diagnostics
        self.tokens = [t for t in tokens if not t.is_trivia]
        self.pos = 0
        self.loop_depth = 0
        self.defined_labels: set[str] = set()
        self.used_jmps: list[tuple[str, SourceSpan]] = []

    @classmethod
    def from_source(cls, source: str) -> "StatementParser":
        lexer = Lexer(source)
        tokens = lexer.tokenize_all(include_trivia=True)
        return cls(tokens, lexer.diagnostics)

    def is_eof(self) -> bool:
        return self.pos >= len(self.tokens) or self.tokens[self.pos].type == TokenType.EOF

    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if 0 <= idx < len(self.tokens):
            return self.tokens[idx]
        eof_span = self.tokens[-1].span if self.tokens else SourceSpan.from_bounds(1, 1, 0, 1, 1, 0)
        return Token(type=TokenType.EOF, value="", span=eof_span)

    def advance(self) -> Token:
        tok = self.peek()
        if not self.is_eof():
            self.pos += 1
        return tok

    def match(self, *expected_types: TokenType) -> bool:
        if self.peek().type in expected_types:
            self.advance()
            return True
        return False

    def expect(self, expected_type: TokenType, err_msg: str) -> Optional[Token]:
        tok = self.peek()
        if tok.type == expected_type:
            return self.advance()
        self.diagnostics.append(
            SyntaxDiagnostic(
                message=f"{err_msg}. Found '{tok.value}'",
                span=tok.span,
                severity=DiagnosticSeverity.ERROR,
            )
        )
        return None

    # =========================================================================
    # Statements
    # =========================================================================

    def parse_statements(self, stop_tokens: tuple[TokenType, ...] = ()) -> tuple[list[Statement], list[CstNode]]:
        statements: list[Statement] = []
        cst_nodes: list[CstNode] = []

        while not self.is_eof():
            tok = self.peek()
            if stop_tokens and tok.type in stop_tokens:
                break

            try:
                stmt, cst = self.parse_single_statement()
                if stmt:
                    statements.append(stmt)
                if cst:
                    cst_nodes.append(cst)
            except Exception as ex:
                # Fatal safety net: recover to next semicolon
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message=f"Syntax recovery triggered: {ex}",
                        span=tok.span,
                    )
                )
                self._recover_to_semicolon()

        if not stop_tokens and self.is_eof():
            # TC-STMT-004: Validate undefined JMP target labels at top level
            for jmp_target, jmp_span in self.used_jmps:
                if jmp_target.lower() not in self.defined_labels:
                    self.diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"Undefined JMP target label '{jmp_target}'",
                            span=jmp_span,
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-STMT-004",
                        )
                    )

        return statements, cst_nodes

    @staticmethod
    def _is_valid_assignment_target(target: Expression) -> bool:
        if isinstance(target, (IdentifierExpr, MemberAccessExpr, IndexExpr, DerefExpr)):
            return True
        return False

    def parse_single_statement(self) -> tuple[Optional[Statement], Optional[CstNode]]:
        tok = self.peek()

        if tok.type == TokenType.SEMICOLON:
            # Empty statement ;
            semi = self.advance()
            return EmptyStmt(span=semi.span), CstNode(kind=CstNodeKind.STATEMENT_BLOCK, span=semi.span)

        if tok.type == TokenType.KEYWORD_IF:
            return self.parse_if_statement()

        if tok.type == TokenType.KEYWORD_CASE:
            return self.parse_case_statement()

        if tok.type == TokenType.KEYWORD_FOR:
            return self.parse_for_statement()

        if tok.type == TokenType.KEYWORD_WHILE:
            return self.parse_while_statement()

        if tok.type == TokenType.KEYWORD_REPEAT:
            return self.parse_repeat_statement()

        if tok.type == TokenType.KEYWORD_RETURN:
            ret_tok = self.advance()
            self.match(TokenType.SEMICOLON)
            return ReturnStmt(span=ret_tok.span), CstNode(kind=CstNodeKind.RETURN_STMT, span=ret_tok.span)

        if tok.type == TokenType.KEYWORD_EXIT:
            exit_tok = self.advance()
            self.match(TokenType.SEMICOLON)
            if self.loop_depth <= 0:
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message="Statement 'EXIT' is only allowed inside a loop (FOR, WHILE, REPEAT)",
                        span=exit_tok.span,
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-STMT-001",
                    )
                )
            return ExitStmt(span=exit_tok.span), CstNode(kind=CstNodeKind.EXIT_STMT, span=exit_tok.span)

        if tok.type == TokenType.KEYWORD_CONTINUE:
            cont_tok = self.advance()
            self.match(TokenType.SEMICOLON)
            if self.loop_depth <= 0:
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message="Statement 'CONTINUE' is only allowed inside a loop (FOR, WHILE, REPEAT)",
                        span=cont_tok.span,
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-STMT-002",
                    )
                )
            return ContinueStmt(span=cont_tok.span), CstNode(kind=CstNodeKind.CONTINUE_STMT, span=cont_tok.span)

        if tok.type == TokenType.KEYWORD_JMP:
            jmp_tok = self.advance()
            label_tok = self.expect(TokenType.IDENTIFIER, "Expected label identifier after JMP")
            label_name = label_tok.value if label_tok else ""
            self.match(TokenType.SEMICOLON)
            span = SourceSpan.merge(jmp_tok.span, label_tok.span if label_tok else jmp_tok.span)
            if label_name:
                self.used_jmps.append((label_name, span))
            return JmpStmt(span=span, label=label_name), CstNode(kind=CstNodeKind.JMP_STMT, span=span)

        if tok.type == TokenType.KEYWORD_TRY:
            return self.parse_try_catch_statement()

        # Label: <identifier>: or <int_literal>:
        if (
            tok.type in (TokenType.IDENTIFIER, TokenType.INT_LITERAL)
            and self.peek(1).type == TokenType.COLON
            and self.peek(2).type not in (TokenType.ASSIGN, TokenType.REF_ASSIGN, TokenType.OUTPUT_ASSIGN)
        ):
            lbl_tok = self.advance()
            colon_tok = self.advance()
            self.defined_labels.add(lbl_tok.value.lower())
            span = SourceSpan.merge(lbl_tok.span, colon_tok.span)
            return LabelStmt(span=span, label=lbl_tok.value), CstNode(kind=CstNodeKind.LABEL_STMT, span=span)

        # Assignment or Call statement
        expr = self.parse_expression()
        end_span = expr.span

        if isinstance(expr, BinaryExpr) and expr.op.upper() in (":=", "REF=", "=>", "?="):
            if self.peek().type == TokenType.SEMICOLON:
                semi = self.advance()
                end_span = semi.span
            else:
                end_span = expr.span
                if self.peek().type not in (
                    TokenType.EOF,
                    TokenType.KEYWORD_END_IF,
                    TokenType.KEYWORD_END_FOR,
                    TokenType.KEYWORD_END_WHILE,
                    TokenType.KEYWORD_END_REPEAT,
                    TokenType.KEYWORD_END_CASE,
                    TokenType.KEYWORD_ELSIF,
                    TokenType.KEYWORD_ELSE,
                    TokenType.KEYWORD_UNTIL,
                ):
                    self.diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"Syntax error: ';' expected before '{self.peek().value}'",
                            span=self.peek().span,
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-STMT-003",
                        )
                    )

            total_span = SourceSpan.merge(expr.span, end_span)
            if not self._is_valid_assignment_target(expr.left):
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message="Invalid assignment target: cannot assign to literal or non-variable expression",
                        span=expr.left.span,
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-EXPR-002",
                    )
                )
            stmt = AssignStmt(
                span=total_span,
                target=expr.left,
                value=expr.right,
                assign_op=expr.op,
            )
            cst = CstNode(kind=CstNodeKind.ASSIGN_STMT, span=total_span)
            return stmt, cst

        elif self.peek().type in (TokenType.ASSIGN, TokenType.REF_ASSIGN):
            assign_op_tok = self.advance()
            val_expr = self.parse_expression()
            if self.peek().type == TokenType.SEMICOLON:
                semi = self.advance()
                end_span = semi.span
            else:
                end_span = val_expr.span
                if self.peek().type not in (
                    TokenType.EOF,
                    TokenType.KEYWORD_END_IF,
                    TokenType.KEYWORD_END_FOR,
                    TokenType.KEYWORD_END_WHILE,
                    TokenType.KEYWORD_END_REPEAT,
                    TokenType.KEYWORD_END_CASE,
                    TokenType.KEYWORD_ELSIF,
                    TokenType.KEYWORD_ELSE,
                    TokenType.KEYWORD_UNTIL,
                ):
                    self.diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"Syntax error: ';' expected before '{self.peek().value}'",
                            span=self.peek().span,
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-STMT-003",
                        )
                    )

            total_span = SourceSpan.merge(expr.span, end_span)
            if not self._is_valid_assignment_target(expr):
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message="Invalid assignment target: cannot assign to literal or non-variable expression",
                        span=expr.span,
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-EXPR-002",
                    )
                )
            stmt = AssignStmt(
                span=total_span,
                target=expr,
                value=val_expr,
                assign_op=assign_op_tok.value,
            )
            cst = CstNode(kind=CstNodeKind.ASSIGN_STMT, span=total_span)
            return stmt, cst

        elif isinstance(expr, CallExpr):
            if self.peek().type == TokenType.SEMICOLON:
                semi = self.advance()
                end_span = semi.span
            else:
                if self.peek().type not in (
                    TokenType.EOF,
                    TokenType.KEYWORD_END_IF,
                    TokenType.KEYWORD_END_FOR,
                    TokenType.KEYWORD_END_WHILE,
                    TokenType.KEYWORD_END_REPEAT,
                    TokenType.KEYWORD_END_CASE,
                    TokenType.KEYWORD_ELSIF,
                    TokenType.KEYWORD_ELSE,
                    TokenType.KEYWORD_UNTIL,
                ):
                    self.diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"Syntax error: ';' expected before '{self.peek().value}'",
                            span=self.peek().span,
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-STMT-003",
                        )
                    )

            total_span = SourceSpan.merge(expr.span, end_span)
            stmt = CallStmt(span=total_span, call=expr)
            cst = CstNode(kind=CstNodeKind.CALL_STMT, span=total_span)
            return stmt, cst

        else:
            # Trailing semicolon or unparsed expression
            if self.peek().type == TokenType.SEMICOLON:
                semi = self.advance()
                end_span = semi.span

            total_span = SourceSpan.merge(expr.span, end_span)
            # Standalone expression / statement
            if isinstance(expr, ErrorExpr):
                return ErrorStmt(span=total_span, raw_text=expr.raw_text), CstNode(kind=CstNodeKind.ERROR_NODE, span=total_span)

            if not isinstance(expr, (CallExpr, IdentifierExpr)):
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message=f"Syntax error: '{getattr(expr, 'name', '') or getattr(expr, 'op', '') or 'expression'}' is not a valid statement",
                        span=total_span,
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-STMT-005",
                    )
                )

            stmt = CallStmt(span=total_span, call=CallExpr(span=total_span, callee=expr) if not isinstance(expr, CallExpr) else expr)
            return stmt, CstNode(kind=CstNodeKind.STATEMENT_BLOCK, span=total_span)

    # -------------------------------------------------------------------------
    # IF Statement
    # -------------------------------------------------------------------------
    def parse_if_statement(self) -> tuple[IfStmt, CstNode]:
        if_tok = self.advance()  # IF
        cond = self.parse_expression()
        self.expect(TokenType.KEYWORD_THEN, "Expected 'THEN' after IF condition")

        then_body, then_cst = self.parse_statements(
            stop_tokens=(TokenType.KEYWORD_ELSIF, TokenType.KEYWORD_ELSE, TokenType.KEYWORD_END_IF)
        )

        elsifs: list[ElsifBranch] = []
        elsif_csts: list[CstNode] = []

        while self.peek().type == TokenType.KEYWORD_ELSIF:
            elsif_tok = self.advance()
            elsif_cond = self.parse_expression()
            self.expect(TokenType.KEYWORD_THEN, "Expected 'THEN' after ELSIF condition")
            elsif_body, _ = self.parse_statements(
                stop_tokens=(TokenType.KEYWORD_ELSIF, TokenType.KEYWORD_ELSE, TokenType.KEYWORD_END_IF)
            )
            branch_span = SourceSpan.merge(
                elsif_tok.span,
                elsif_body[-1].span if elsif_body else elsif_cond.span,
            )
            elsifs.append(ElsifBranch(span=branch_span, condition=elsif_cond, body=elsif_body))
            elsif_csts.append(CstNode(kind=CstNodeKind.ELSIF_BRANCH, span=branch_span))

        else_branch = None
        else_cst = None
        if self.peek().type == TokenType.KEYWORD_ELSE:
            else_tok = self.advance()
            else_body, _ = self.parse_statements(stop_tokens=(TokenType.KEYWORD_END_IF,))
            branch_span = SourceSpan.merge(
                else_tok.span,
                else_body[-1].span if else_body else else_tok.span,
            )
            else_branch = ElseBranch(span=branch_span, body=else_body)
            else_cst = CstNode(kind=CstNodeKind.ELSE_BRANCH, span=branch_span)

        end_tok = self.expect(TokenType.KEYWORD_END_IF, "Expected 'END_IF'")
        if self.peek().type == TokenType.SEMICOLON:
            semi = self.advance()
            end_span = semi.span
        else:
            end_span = end_tok.span if end_tok else if_tok.span

        total_span = SourceSpan.merge(if_tok.span, end_span)
        ast_node = IfStmt(
            span=total_span,
            condition=cond,
            then_body=then_body,
            elsifs=elsifs,
            else_branch=else_branch,
        )
        children = list(then_cst) + elsif_csts
        if else_cst:
            children.append(else_cst)
        cst_node = CstNode(kind=CstNodeKind.IF_STMT, span=total_span, children=children)
        return ast_node, cst_node

    # -------------------------------------------------------------------------
    # CASE Statement
    # -------------------------------------------------------------------------
    def _is_case_label_ahead(self) -> bool:
        """Check if looking ahead at a case label, e.g. 10: or 10, 20: or 30..50: or E_State.Running:"""
        tok0 = self.peek()
        if tok0.type in (TokenType.KEYWORD_END_CASE, TokenType.KEYWORD_ELSE):
            return True

        valid_label_tokens = (
            TokenType.IDENTIFIER,
            TokenType.INT_LITERAL,
            TokenType.REAL_LITERAL,
            TokenType.TYPED_LITERAL,
            TokenType.STRING_LITERAL,
            TokenType.BOOL_LITERAL,
            TokenType.DOT,
            TokenType.RANGE,
            TokenType.COMMA,
            TokenType.PLUS,
            TokenType.MINUS,
            TokenType.PAREN_OPEN,
            TokenType.PAREN_CLOSE,
        )

        i = 0
        has_at_least_one_val = False
        while self.pos + i < len(self.tokens):
            tok = self.tokens[self.pos + i]
            if tok.type == TokenType.COLON:
                return has_at_least_one_val
            if tok.type not in valid_label_tokens:
                return False
            if tok.type in (
                TokenType.IDENTIFIER,
                TokenType.INT_LITERAL,
                TokenType.REAL_LITERAL,
                TokenType.TYPED_LITERAL,
                TokenType.STRING_LITERAL,
                TokenType.BOOL_LITERAL,
            ):
                has_at_least_one_val = True
            i += 1
        return False

    def parse_case_statement(self) -> tuple[CaseStmt, CstNode]:
        case_tok = self.advance()  # CASE
        expr = self.parse_expression()
        self.expect(TokenType.KEYWORD_OF, "Expected 'OF' after CASE expression")

        branches: list[CaseBranch] = []
        cst_branches: list[CstNode] = []
        else_branch = None
        else_cst = None

        while not self.is_eof() and self.peek().type not in (TokenType.KEYWORD_END_CASE,):
            if self.peek().type == TokenType.KEYWORD_ELSE:
                else_tok = self.advance()
                else_body, _ = self.parse_statements(stop_tokens=(TokenType.KEYWORD_END_CASE,))
                b_span = SourceSpan.merge(else_tok.span, else_body[-1].span if else_body else else_tok.span)
                else_branch = ElseBranch(span=b_span, body=else_body)
                else_cst = CstNode(kind=CstNodeKind.ELSE_BRANCH, span=b_span)
                break

            # Parse branch values: 1, 2, 5..10 :
            vals: list[Expression] = []
            while not self.is_eof():
                val_expr = self.parse_expression()
                if self.peek().type == TokenType.RANGE:
                    range_tok = self.advance()
                    end_val_expr = self.parse_expression()
                    r_span = SourceSpan.merge(val_expr.span, end_val_expr.span)
                    vals.append(RangeExpr(span=r_span, start=val_expr, end=end_val_expr))
                else:
                    vals.append(val_expr)

                if self.peek().type == TokenType.COMMA:
                    self.advance()
                elif self.peek().type == TokenType.COLON:
                    self.advance()
                    break
                else:
                    break

            # Parse statements in this case branch until next case label, ELSE, or END_CASE
            branch_body: list[Statement] = []
            while not self.is_eof() and self.peek().type not in (TokenType.KEYWORD_ELSE, TokenType.KEYWORD_END_CASE):
                if self._is_case_label_ahead():
                    break
                try:
                    stmt, _ = self.parse_single_statement()
                    if stmt:
                        branch_body.append(stmt)
                except Exception as ex:
                    self.diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"Syntax recovery in case branch: {ex}",
                            span=self.peek().span,
                        )
                    )
                    self._recover_to_semicolon()

            start_span = vals[0].span if vals else case_tok.span
            end_span = branch_body[-1].span if branch_body else start_span
            b_span = SourceSpan.merge(start_span, end_span)
            branches.append(CaseBranch(span=b_span, values=vals, body=branch_body))
            cst_branches.append(CstNode(kind=CstNodeKind.CASE_BRANCH, span=b_span))

        end_tok = self.expect(TokenType.KEYWORD_END_CASE, "Expected 'END_CASE'")
        if self.peek().type == TokenType.SEMICOLON:
            semi = self.advance()
            end_span = semi.span
        else:
            end_span = end_tok.span if end_tok else case_tok.span

        total_span = SourceSpan.merge(case_tok.span, end_span)
        ast_node = CaseStmt(
            span=total_span,
            expression=expr,
            branches=branches,
            else_branch=else_branch,
        )
        children = list(cst_branches)
        if else_cst:
            children.append(else_cst)
        cst_node = CstNode(kind=CstNodeKind.CASE_STMT, span=total_span, children=children)
        return ast_node, cst_node

    # -------------------------------------------------------------------------
    # FOR Statement
    # -------------------------------------------------------------------------
    def parse_for_statement(self) -> tuple[ForStmt, CstNode]:
        for_tok = self.advance()  # FOR
        var_tok = self.expect(TokenType.IDENTIFIER, "Expected loop variable after FOR")
        loop_var = var_tok.value if var_tok else ""

        self.expect(TokenType.ASSIGN, "Expected ':=' after FOR loop variable")
        start_expr = self.parse_expression()
        self.expect(TokenType.KEYWORD_TO, "Expected 'TO' after FOR start expression")
        end_expr = self.parse_expression()

        by_expr = None
        if self.peek().type == TokenType.KEYWORD_BY:
            self.advance()
            by_expr = self.parse_expression()

        self.expect(TokenType.KEYWORD_DO, "Expected 'DO' in FOR loop")
        self.loop_depth += 1
        body, body_cst = self.parse_statements(stop_tokens=(TokenType.KEYWORD_END_FOR,))
        self.loop_depth -= 1
        end_tok = self.expect(TokenType.KEYWORD_END_FOR, "Expected 'END_FOR'")

        if self.peek().type == TokenType.SEMICOLON:
            semi = self.advance()
            end_span = semi.span
        else:
            end_span = end_tok.span if end_tok else for_tok.span

        total_span = SourceSpan.merge(for_tok.span, end_span)
        ast_node = ForStmt(
            span=total_span,
            loop_var=loop_var,
            start_expr=start_expr,
            end_expr=end_expr,
            by_expr=by_expr,
            body=body,
        )
        cst_node = CstNode(kind=CstNodeKind.FOR_STMT, span=total_span, children=body_cst)
        return ast_node, cst_node

    # -------------------------------------------------------------------------
    # WHILE & REPEAT Statements
    # -------------------------------------------------------------------------
    def parse_while_statement(self) -> tuple[WhileStmt, CstNode]:
        while_tok = self.advance()  # WHILE
        cond = self.parse_expression()
        self.expect(TokenType.KEYWORD_DO, "Expected 'DO' after WHILE condition")

        self.loop_depth += 1
        body, body_cst = self.parse_statements(stop_tokens=(TokenType.KEYWORD_END_WHILE,))
        self.loop_depth -= 1
        end_tok = self.expect(TokenType.KEYWORD_END_WHILE, "Expected 'END_WHILE'")

        if self.peek().type == TokenType.SEMICOLON:
            semi = self.advance()
            end_span = semi.span
        else:
            end_span = end_tok.span if end_tok else while_tok.span

        total_span = SourceSpan.merge(while_tok.span, end_span)
        ast_node = WhileStmt(span=total_span, condition=cond, body=body)
        cst_node = CstNode(kind=CstNodeKind.WHILE_STMT, span=total_span, children=body_cst)
        return ast_node, cst_node

    def parse_repeat_statement(self) -> tuple[RepeatStmt, CstNode]:
        repeat_tok = self.advance()  # REPEAT
        self.loop_depth += 1
        body, body_cst = self.parse_statements(stop_tokens=(TokenType.KEYWORD_UNTIL,))
        self.loop_depth -= 1
        self.expect(TokenType.KEYWORD_UNTIL, "Expected 'UNTIL' in REPEAT statement")
        cond = self.parse_expression()
        end_tok = self.expect(TokenType.KEYWORD_END_REPEAT, "Expected 'END_REPEAT'")

        if self.peek().type == TokenType.SEMICOLON:
            semi = self.advance()
            end_span = semi.span
        else:
            end_span = end_tok.span if end_tok else cond.span

        total_span = SourceSpan.merge(repeat_tok.span, end_span)
        ast_node = RepeatStmt(span=total_span, condition=cond, body=body)
        cst_node = CstNode(kind=CstNodeKind.REPEAT_STMT, span=total_span, children=body_cst)
        return ast_node, cst_node

    def parse_try_catch_statement(self) -> tuple[TryCatchStmt, CstNode]:
        try_tok = self.advance()  # __TRY
        try_body, try_cst = self.parse_statements(
            stop_tokens=(TokenType.KEYWORD_CATCH, TokenType.KEYWORD_FINALLY, TokenType.KEYWORD_ENDTRY)
        )

        catch_var = None
        catch_body: list[Statement] = []
        catch_cst: list[CstNode] = []
        if self.peek().type == TokenType.KEYWORD_CATCH:
            self.advance()  # __CATCH
            if self.peek().type == TokenType.PAREN_OPEN:
                self.advance()
                var_tok = self.expect(TokenType.IDENTIFIER, "Expected exception variable in __CATCH(...)")
                if var_tok:
                    catch_var = var_tok.value
                self.expect(TokenType.PAREN_CLOSE, "Expected ')' after exception variable in __CATCH")
            catch_body, catch_cst = self.parse_statements(
                stop_tokens=(TokenType.KEYWORD_FINALLY, TokenType.KEYWORD_ENDTRY)
            )

        finally_body: list[Statement] = []
        finally_cst: list[CstNode] = []
        if self.peek().type == TokenType.KEYWORD_FINALLY:
            self.advance()  # __FINALLY
            finally_body, finally_cst = self.parse_statements(
                stop_tokens=(TokenType.KEYWORD_ENDTRY,)
            )

        end_tok = self.expect(TokenType.KEYWORD_ENDTRY, "Expected '__ENDTRY'")
        if self.peek().type == TokenType.SEMICOLON:
            semi = self.advance()
            end_span = semi.span
        else:
            end_span = end_tok.span if end_tok else try_tok.span

        total_span = SourceSpan.merge(try_tok.span, end_span)
        ast_node = TryCatchStmt(
            span=total_span,
            try_body=try_body,
            catch_var=catch_var,
            catch_body=catch_body,
            finally_body=finally_body,
        )
        cst_node = CstNode(
            kind=CstNodeKind.TRY_CATCH_STMT,
            span=total_span,
            children=list(try_cst) + list(catch_cst) + list(finally_cst),
        )
        return ast_node, cst_node

    def _recover_to_semicolon(self) -> None:
        while not self.is_eof() and self.peek().type not in (
            TokenType.SEMICOLON,
            TokenType.KEYWORD_END_IF,
            TokenType.KEYWORD_END_CASE,
            TokenType.KEYWORD_END_FOR,
            TokenType.KEYWORD_END_WHILE,
            TokenType.KEYWORD_END_REPEAT,
            TokenType.KEYWORD_ENDTRY,
            TokenType.KEYWORD_CATCH,
            TokenType.KEYWORD_FINALLY,
        ):
            self.advance()
        if self.peek().type == TokenType.SEMICOLON:
            self.advance()

    # =========================================================================
    # Pratt Expression Parser
    # =========================================================================

    def parse_expression(self, rbp: int = 0) -> Expression:
        tok = self.peek()
        left = self._nud(tok)

        while not self.is_eof() and rbp < self._lbp(self.peek()):
            tok = self.peek()
            left = self._led(tok, left)

        return left

    def _lbp(self, tok: Token) -> int:
        """Left binding power for operators."""
        mapping = {
            TokenType.ASSIGN: 5,
            TokenType.REF_ASSIGN: 5,
            TokenType.KEYWORD_OR: 10,
            TokenType.KEYWORD_OR_ELSE: 10,
            TokenType.KEYWORD_XOR: 20,
            TokenType.KEYWORD_AND: 30,
            TokenType.KEYWORD_AND_THEN: 30,
            TokenType.EQ: 40,
            TokenType.NE: 40,
            TokenType.LT: 40,
            TokenType.LE: 40,
            TokenType.GT: 40,
            TokenType.GE: 40,
            TokenType.PLUS: 50,
            TokenType.MINUS: 50,
            TokenType.STAR: 60,
            TokenType.SLASH: 60,
            TokenType.KEYWORD_MOD: 60,
            TokenType.POWER: 70,
            TokenType.KEYWORD_EXPT: 70,
            TokenType.POINTER_DEREF: 80,
            TokenType.DOT: 90,
            TokenType.BRACKET_OPEN: 90,
            TokenType.PAREN_OPEN: 90,
        }
        return mapping.get(tok.type, 0)

    def _nud(self, tok: Token) -> Expression:
        """Null denotation for prefix operators / primary expressions."""
        # 1. Unary prefix operators
        if tok.type in (TokenType.PLUS, TokenType.MINUS, TokenType.KEYWORD_NOT):
            op_tok = self.advance()
            operand = self.parse_expression(rbp=70)
            span = SourceSpan.merge(op_tok.span, operand.span)
            return UnaryExpr(span=span, op=op_tok.value, operand=operand)

        # ADR / REF / ADRREF → AddressOfExpr (pointer/reference operators)
        if tok.type in (
            TokenType.KEYWORD_ADR,
            TokenType.KEYWORD_REF,
            TokenType.KEYWORD_ADRREF,
        ):
            op_tok = self.advance()
            if self.peek().type == TokenType.PAREN_OPEN:
                self.advance()
                target = self.parse_expression()
                close_tok = self.expect(TokenType.PAREN_CLOSE, f"Expected ')' closing {op_tok.value}")
                end_span = close_tok.span if close_tok else target.span
                span = SourceSpan.merge(op_tok.span, end_span)
                return AddressOfExpr(
                    span=span,
                    target=target,
                    is_ref=(op_tok.type in (TokenType.KEYWORD_REF, TokenType.KEYWORD_ADRREF)),
                )
            return IdentifierExpr(span=op_tok.span, name=op_tok.value)

        # SIZEOF / XSIZEOF / BITADR / INDEXOF → CallExpr so type inference returns UDINT/DINT
        # (must not reuse AddressOfExpr — that yields POINTER TO <arg> and false TC-SEM-006)
        if tok.type in (
            TokenType.KEYWORD_SIZEOF,
            TokenType.KEYWORD_XSIZEOF,
            TokenType.KEYWORD_BITADR,
            TokenType.KEYWORD_INDEXOF,
        ):
            op_tok = self.advance()
            if self.peek().type == TokenType.PAREN_OPEN:
                self.advance()
                target = self.parse_expression()
                close_tok = self.expect(TokenType.PAREN_CLOSE, f"Expected ')' closing {op_tok.value}")
                end_span = close_tok.span if close_tok else target.span
                span = SourceSpan.merge(op_tok.span, end_span)
                return CallExpr(
                    span=span,
                    callee=IdentifierExpr(span=op_tok.span, name=op_tok.value),
                    args=[CallArg(span=target.span, value=target)],
                )
            return IdentifierExpr(span=op_tok.span, name=op_tok.value)

        # 2. Parenthesized expressions (expr)
        if tok.type == TokenType.PAREN_OPEN:
            open_tok = self.advance()
            expr = self.parse_expression()
            close_tok = self.expect(TokenType.PAREN_CLOSE, "Expected ')'")
            end_span = close_tok.span if close_tok else expr.span
            return expr

        # 3. Literals
        if tok.type in (
            TokenType.INT_LITERAL,
            TokenType.REAL_LITERAL,
            TokenType.TYPED_LITERAL,
            TokenType.STRING_LITERAL,
            TokenType.WSTRING_LITERAL,
            TokenType.BOOL_LITERAL,
        ):
            lit_tok = self.advance()
            return LiteralExpr(
                span=lit_tok.span,
                value=lit_tok.value,
                literal_type=lit_tok.type.name,
            )

        # 4. Identifiers & Keywords used as variables or functions/operators
        if tok.type in (
            TokenType.IDENTIFIER,
            TokenType.KEYWORD_THIS,
            TokenType.KEYWORD_SUPER,
            TokenType.KEYWORD_NEW,
            TokenType.KEYWORD_DELETE,
            TokenType.KEYWORD_QUERYINTERFACE,
            TokenType.KEYWORD_QUERYPOINTER,
            TokenType.KEYWORD_ISVALIDREF,
            TokenType.KEYWORD_VARINFO,
            TokenType.KEYWORD_POUNAME,
            TokenType.KEYWORD_POSITION,
            TokenType.KEYWORD_EXPT,
            TokenType.KEYWORD_LOWER_BOUND,
            TokenType.KEYWORD_UPPER_BOUND,
        ):
            id_tok = self.advance()
            return IdentifierExpr(span=id_tok.span, name=id_tok.value)

        # 5. Direct Address or Partial Access
        if tok.type in (TokenType.DIRECT_ADDRESS, TokenType.PARTIAL_ACCESS):
            addr_tok = self.advance()
            return IdentifierExpr(span=addr_tok.span, name=addr_tok.value)

        # Error fallback
        self.diagnostics.append(
            SyntaxDiagnostic(
                message=f"Unexpected expression token: '{tok.value}'",
                span=tok.span,
            )
        )
        bad_tok = self.advance()
        return ErrorExpr(span=bad_tok.span, raw_text=bad_tok.value)

    def _led(self, tok: Token, left: Expression) -> Expression:
        """Left denotation for infix operators / postfix selectors."""
        # 1. Member access (left.member, left.0, left.%X0, left.%B1, etc.)
        if tok.type == TokenType.DOT:
            dot_tok = self.advance()
            if self.peek().type in (
                TokenType.IDENTIFIER,
                TokenType.INT_LITERAL,
                TokenType.PARTIAL_ACCESS,
                TokenType.KEYWORD_THIS,
                TokenType.KEYWORD_SUPER,
            ):
                member_tok = self.advance()
                member_name = member_tok.value
                span = SourceSpan.merge(left.span, member_tok.span)
                return MemberAccessExpr(span=span, target=left, member_name=member_name)
            else:
                member_tok = self.expect(TokenType.IDENTIFIER, "Expected identifier after '.'")
                member_name = member_tok.value if member_tok else ""
                span = SourceSpan.merge(left.span, member_tok.span if member_tok else dot_tok.span)
                return MemberAccessExpr(span=span, target=left, member_name=member_name)

        # 2. Array indexing (left[i, j])
        if tok.type == TokenType.BRACKET_OPEN:
            self.advance()
            indices: list[Expression] = []
            while not self.is_eof():
                idx_expr = self.parse_expression()
                indices.append(idx_expr)
                if self.peek().type == TokenType.COMMA:
                    self.advance()
                else:
                    break
            close_tok = self.expect(TokenType.BRACKET_CLOSE, "Expected ']'")
            span = SourceSpan.merge(left.span, close_tok.span if close_tok else indices[-1].span)
            return IndexExpr(span=span, target=left, indices=indices)

        # 3. Pointer dereference (left^)
        if tok.type == TokenType.POINTER_DEREF:
            deref_tok = self.advance()
            span = SourceSpan.merge(left.span, deref_tok.span)
            return DerefExpr(span=span, target=left)

        # 4. Function / Method / FB Call (left(arg1, arg2 := 5, out => var))
        if tok.type == TokenType.PAREN_OPEN:
            self.advance()
            args: list[CallArg] = []
            while not self.is_eof() and self.peek().type != TokenType.PAREN_CLOSE:
                arg = self._parse_call_arg()
                if arg:
                    args.append(arg)
                if self.peek().type == TokenType.COMMA:
                    self.advance()
                else:
                    break
            close_tok = self.expect(TokenType.PAREN_CLOSE, "Expected ')' closing argument list")
            span = SourceSpan.merge(left.span, close_tok.span if close_tok else left.span)
            return CallExpr(span=span, callee=left, args=args)

        # 5. Assignment operators in expressions / chained assignments (:=, REF=)
        if tok.type in (TokenType.ASSIGN, TokenType.REF_ASSIGN):
            op_tok = self.advance()
            lbp = self._lbp(op_tok)
            # right-associative: pass rbp = lbp - 1
            right = self.parse_expression(rbp=lbp - 1)
            span = SourceSpan.merge(left.span, right.span)
            return BinaryExpr(span=span, op=op_tok.value, left=left, right=right)

        # 6. Standard Binary operators (+, -, *, /, AND, OR, =, <>, etc.)
        op_tok = self.advance()
        lbp = self._lbp(op_tok)
        right = self.parse_expression(rbp=lbp)
        span = SourceSpan.merge(left.span, right.span)
        return BinaryExpr(span=span, op=op_tok.value, left=left, right=right)

    def _parse_call_arg(self) -> Optional[CallArg]:
        start_tok = self.peek()
        if start_tok.type in (TokenType.COMMA, TokenType.PAREN_CLOSE):
            return None

        # Check if named argument: name := val or out => val or ref REF= val
        if (
            (start_tok.type == TokenType.IDENTIFIER or (start_tok.value and start_tok.value.isidentifier()))
            and self.peek(1).type in (TokenType.ASSIGN, TokenType.OUTPUT_ASSIGN, TokenType.REF_ASSIGN)
        ):
            name_tok = self.advance()
            op_tok = self.advance()
            # If value is omitted (e.g. `nColorTempKelvin => ,` or `bIn := ,` or `out => )`):
            if self.peek().type in (TokenType.COMMA, TokenType.PAREN_CLOSE):
                span = SourceSpan.merge(name_tok.span, op_tok.span)
                return CallArg(span=span, name=name_tok.value, assign_op=op_tok.value, value=None)
            val_expr = self.parse_expression()
            span = SourceSpan.merge(name_tok.span, val_expr.span if val_expr else op_tok.span)
            return CallArg(span=span, name=name_tok.value, assign_op=op_tok.value, value=val_expr)
        else:
            val_expr = self.parse_expression()
            return CallArg(span=val_expr.span if val_expr else start_tok.span, name=None, assign_op=":=", value=val_expr)
