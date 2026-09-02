"""Parser for Structured Text declarations (POU, METHOD, PROPERTY, TYPE, STRUCT, ENUM, GVL, VAR blocks)."""
from __future__ import annotations

import re
from bisect import bisect_left
from typing import List, Optional, Sequence, Tuple

from .ast import (
    AstNode,
    EnumMember,
    EnumType,
    InterfaceDecl,
    MethodDecl,
    PouDecl,
    PragmaAttribute,
    PropertyDecl,
    StructType,
    TypeDecl,
    UnionType,
    VarBlock,
    VarDecl,
)
from .cst import CstNode, CstNodeKind
from .diagnostics import DiagnosticSeverity, SyntaxDiagnostic
from .lexer import Lexer
from .span import SourceSpan
from .tokens import Token, TokenChannel, TokenType

_RE_PRAGMA_ATTR = re.compile(r"\{\s*attribute\s+'([^']+)'(?:\s*:=\s*'([^']*)')?\s*\}", re.IGNORECASE)


class DeclarationParser:
    """Robust, fault-tolerant parser for IEC 61131-3 & TwinCAT declarations."""

    def __init__(self, tokens: list[Token], diagnostics: list[SyntaxDiagnostic]) -> None:
        self.all_tokens = tokens
        self.diagnostics = diagnostics
        # Non-trivia tokens for parser navigation
        self.tokens = [t for t in tokens if not t.is_trivia]
        self.pos = 0

        # Pre-index token start offsets for O(log N) leading trivia searches
        self._token_start_offsets = [t.span.start.offset for t in tokens]

        # Pre-parse and index pragmas for fast O(1) / O(k) lookups
        self._pragmas: list[tuple[int, PragmaAttribute]] = []
        for t in tokens:
            if t.type == TokenType.PRAGMA:
                raw = t.value
                m = _RE_PRAGMA_ATTR.search(raw)
                if m:
                    attr_name = m.group(1)
                    attr_val = m.group(2)
                    self._pragmas.append(
                        (
                            t.span.start.offset,
                            PragmaAttribute(
                                span=t.span,
                                name=attr_name,
                                value=attr_val,
                                raw_text=raw,
                            ),
                        )
                    )
                else:
                    self._pragmas.append(
                        (
                            t.span.start.offset,
                            PragmaAttribute(
                                span=t.span,
                                name=raw.strip("{} "),
                                value=None,
                                raw_text=raw,
                            ),
                        )
                    )

        # Pre-index comments by line for O(1) trailing doc comment lookups
        self._comments_by_line: dict[int, list[Token]] = {}
        for t in tokens:
            if t.type in (TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT):
                line = t.span.start.line
                if line not in self._comments_by_line:
                    self._comments_by_line[line] = []
                self._comments_by_line[line].append(t)

    @classmethod
    def from_source(cls, source: str) -> "DeclarationParser":
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

    def _extract_pragmas(self, span: SourceSpan) -> list[PragmaAttribute]:
        """Extract pragmas from pre-parsed pragma list that appear within or right before span."""
        if not self._pragmas:
            return []
        pragmas: list[PragmaAttribute] = []
        for start_off, p_obj in self._pragmas:
            if start_off <= span.end.offset:
                pragmas.append(p_obj)
        return pragmas

    @staticmethod
    def _clean_comment_text(raw: str) -> str:
        """Strip comment markers // or (* *) and clean whitespace."""
        raw = raw.strip()
        if raw.startswith("//"):
            return raw[2:].strip()
        if raw.startswith("(*") and raw.endswith("*)"):
            inner = raw[2:-2].strip()
            lines = [l.strip().lstrip("* ").strip() for l in inner.splitlines()]
            return "\n".join(l for l in lines if l).strip()
        return raw

    def _extract_doc_comment(self, span: SourceSpan) -> Optional[str]:
        """Extract doc comment (trailing on same line or leading on immediately preceding lines)."""
        # 1. Trailing comment: same line as span.end, offset >= span.end.offset
        line_comments = self._comments_by_line.get(span.end.line)
        if line_comments:
            trailing_comments: list[str] = []
            for tok in line_comments:
                if tok.span.start.offset >= span.end.offset:
                    cleaned = self._clean_comment_text(tok.value)
                    if cleaned:
                        trailing_comments.append(cleaned)
            if trailing_comments:
                return " ".join(trailing_comments)

        # 2. Leading comments: find comments immediately preceding span.start.offset
        idx = bisect_left(self._token_start_offsets, span.start.offset)
        leading_comments: list[str] = []
        back_idx = idx - 1
        while back_idx >= 0:
            tok = self.all_tokens[back_idx]
            if tok.type in (TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.PRAGMA):
                back_idx -= 1
                continue
            if tok.type in (TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT):
                cleaned = self._clean_comment_text(tok.value)
                if cleaned:
                    leading_comments.insert(0, cleaned)
                back_idx -= 1
                continue
            break

        if leading_comments:
            return "\n".join(leading_comments)

        return None

    # =========================================================================
    # Main Entry Point for Declarations
    # =========================================================================

    def parse_declaration_file(self) -> tuple[Optional[AstNode], list[CstNode]]:
        """Parse whatever top-level declaration exists (POU, METHOD, PROPERTY, TYPE, INTERFACE, or GVL VAR blocks)."""
        cst_nodes: list[CstNode] = []
        ast_node: Optional[AstNode] = None

        while not self.is_eof():
            tok = self.peek()

            # POU (FUNCTION_BLOCK, FUNCTION, PROGRAM)
            if tok.type in (TokenType.KEYWORD_FUNCTION_BLOCK, TokenType.KEYWORD_FUNCTION, TokenType.KEYWORD_PROGRAM):
                ast_node, cst = self.parse_pou_declaration()
                if cst:
                    cst_nodes.append(cst)
                break

            # METHOD
            elif tok.type == TokenType.KEYWORD_METHOD:
                ast_node, cst = self.parse_method_declaration()
                if cst:
                    cst_nodes.append(cst)
                break

            # PROPERTY
            elif tok.type == TokenType.KEYWORD_PROPERTY:
                ast_node, cst = self.parse_property_declaration()
                if cst:
                    cst_nodes.append(cst)
                break

            # INTERFACE
            elif tok.type == TokenType.KEYWORD_INTERFACE:
                ast_node, cst = self.parse_interface_declaration()
                if cst:
                    cst_nodes.append(cst)
                break

            # TYPE (STRUCT, ENUM, ALIAS, UNION)
            elif tok.type == TokenType.KEYWORD_TYPE:
                ast_node, cst = self.parse_type_declaration()
                if cst:
                    cst_nodes.append(cst)
                break

            # VAR / VAR_GLOBAL blocks (e.g. in GVL or bare declaration CDATA)
            elif tok.type in (
                TokenType.KEYWORD_VAR,
                TokenType.KEYWORD_VAR_INPUT,
                TokenType.KEYWORD_VAR_OUTPUT,
                TokenType.KEYWORD_VAR_IN_OUT,
                TokenType.KEYWORD_VAR_GLOBAL,
                TokenType.KEYWORD_VAR_TEMP,
                TokenType.KEYWORD_VAR_STAT,
                TokenType.KEYWORD_VAR_INST,
                TokenType.KEYWORD_VAR_CONFIG,
                TokenType.KEYWORD_VAR_EXTERNAL,
                TokenType.KEYWORD_VAR_GENERIC,
            ):
                var_blocks, block_csts = self.parse_all_var_blocks()
                cst_nodes.extend(block_csts)
                # If there is no enclosing POU, we can wrap var blocks in a synthetic container or return the first block
                if var_blocks and not ast_node:
                    if len(var_blocks) == 1:
                        ast_node = var_blocks[0]
                    else:
                        # Synthetic POU container for multiple GVL var blocks
                        span = SourceSpan.merge(var_blocks[0].span, var_blocks[-1].span)
                        ast_node = PouDecl(
                            span=span,
                            pou_type="GVL",
                            name="GVL",
                            var_blocks=var_blocks,
                        )
                break
            else:
                # Unknown or misplaced token - skip to next recognized anchor
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message=f"Unexpected token in declaration: {tok.value!r}",
                        span=tok.span,
                    )
                )
                self.advance()

        return ast_node, cst_nodes

    def _parse_type_specifier(self) -> tuple[str, SourceSpan]:
        type_tokens: list[str] = []
        bracket_depth = 0
        paren_depth = 0
        start_span = self.peek().span
        end_span = start_span

        VAR_STOP_TYPES = (
            TokenType.KEYWORD_VAR,
            TokenType.KEYWORD_VAR_INPUT,
            TokenType.KEYWORD_VAR_OUTPUT,
            TokenType.KEYWORD_VAR_IN_OUT,
            TokenType.KEYWORD_VAR_TEMP,
            TokenType.KEYWORD_VAR_STAT,
            TokenType.KEYWORD_VAR_INST,
            TokenType.KEYWORD_VAR_CONFIG,
            TokenType.KEYWORD_VAR_GLOBAL,
            TokenType.KEYWORD_VAR_EXTERNAL,
            TokenType.KEYWORD_VAR_GENERIC,
            TokenType.KEYWORD_END_FUNCTION,
            TokenType.KEYWORD_END_METHOD,
            TokenType.KEYWORD_END_PROPERTY,
            TokenType.KEYWORD_END_FUNCTION_BLOCK,
            TokenType.KEYWORD_END_PROGRAM,
            TokenType.KEYWORD_EXTENDS,
            TokenType.KEYWORD_IMPLEMENTS,
            TokenType.SEMICOLON,
        )

        while not self.is_eof():
            t_peek = self.peek()
            if t_peek.type == TokenType.BRACKET_OPEN:
                bracket_depth += 1
            elif t_peek.type == TokenType.BRACKET_CLOSE:
                if bracket_depth > 0:
                    bracket_depth -= 1
            elif t_peek.type == TokenType.PAREN_OPEN:
                paren_depth += 1
            elif t_peek.type == TokenType.PAREN_CLOSE:
                if paren_depth > 0:
                    paren_depth -= 1
            elif bracket_depth == 0 and paren_depth == 0:
                if t_peek.type in VAR_STOP_TYPES:
                    break

            t = self.advance()
            type_tokens.append(t.value)
            end_span = t.span

        raw_type = " ".join(type_tokens).strip()
        raw_type = re.sub(r'\s*\(\s*', '(', raw_type)
        raw_type = re.sub(r'\s*\)', ')', raw_type)
        raw_type = re.sub(r'\s*\[\s*', '[', raw_type)
        raw_type = re.sub(r'\s*\]', ']', raw_type)
        return raw_type, SourceSpan.merge(start_span, end_span)

    # =========================================================================
    # POU Declaration
    # =========================================================================

    def parse_pou_declaration(self) -> tuple[PouDecl, CstNode]:
        start_tok = self.advance()
        pou_type = start_tok.value.upper()
        start_span = start_tok.span
        end_span = start_span

        access = "PUBLIC"
        is_abstract = False
        is_final = False

        # Modifiers before or after name? In IEC / TwinCAT, e.g. FUNCTION_BLOCK ABSTRACT FINAL FB_Test
        while self.peek().type in (
            TokenType.KEYWORD_ABSTRACT,
            TokenType.KEYWORD_FINAL,
            TokenType.KEYWORD_PUBLIC,
            TokenType.KEYWORD_PROTECTED,
            TokenType.KEYWORD_PRIVATE,
            TokenType.KEYWORD_INTERNAL,
        ):
            mod_tok = self.advance()
            if mod_tok.type == TokenType.KEYWORD_ABSTRACT:
                is_abstract = True
            elif mod_tok.type == TokenType.KEYWORD_FINAL:
                is_final = True
            else:
                access = mod_tok.value.upper()

        name_tok = self.expect(TokenType.IDENTIFIER, f"Expected identifier for {pou_type} name")
        name = name_tok.value if name_tok else ""

        # Function return type (e.g. FUNCTION F_Add : INT)
        return_type = None
        if pou_type == "FUNCTION" and self.peek().type == TokenType.COLON:
            self.advance()
            return_type, end_span = self._parse_type_specifier()

        # EXTENDS
        extends_name = None
        if self.peek().type == TokenType.KEYWORD_EXTENDS:
            self.advance()
            ext_tok = self.expect(TokenType.IDENTIFIER, "Expected base class name after EXTENDS")
            if ext_tok:
                extends_name = ext_tok.value
                end_span = ext_tok.span

        # IMPLEMENTS
        implements_names: list[str] = []
        if self.peek().type == TokenType.KEYWORD_IMPLEMENTS:
            self.advance()
            while not self.is_eof():
                itf_tok = self.expect(TokenType.IDENTIFIER, "Expected interface name after IMPLEMENTS")
                if itf_tok:
                    implements_names.append(itf_tok.value)
                    end_span = itf_tok.span
                if self.peek().type == TokenType.COMMA:
                    self.advance()
                else:
                    break

        # Parse VAR blocks inside POU declaration
        var_blocks, var_csts = self.parse_all_var_blocks()
        if var_blocks:
            end_span = var_blocks[-1].span

        # Optional closing END_FUNCTION_BLOCK / END_FUNCTION / END_PROGRAM if present in CDATA
        end_kw_map = {
            "FUNCTION_BLOCK": TokenType.KEYWORD_END_FUNCTION_BLOCK,
            "FUNCTION": TokenType.KEYWORD_END_FUNCTION,
            "PROGRAM": TokenType.KEYWORD_END_PROGRAM,
        }
        if pou_type in end_kw_map and self.peek().type == end_kw_map[pou_type]:
            end_kw = self.advance()
            end_span = end_kw.span

        pou_comment = self._extract_doc_comment(start_tok.span)

        first_token = self.all_tokens[0] if self.all_tokens else None
        if first_token and first_token.span.start.offset < start_span.start.offset:
            start_span = first_token.span

        total_span = SourceSpan.merge(start_span, end_span)
        pragmas = self._extract_pragmas(total_span)

        if pou_type == "FUNCTION" and return_type is None:
            self.diagnostics.append(
                SyntaxDiagnostic(
                    message=f"FUNCTION '{name}' requires an explicit return type",
                    span=total_span,
                    severity=DiagnosticSeverity.ERROR,
                    code="TC-DECL-001",
                )
            )

        ast_node = PouDecl(
            span=total_span,
            pou_type=pou_type,
            name=name,
            return_type=return_type,
            extends_name=extends_name,
            implements_names=implements_names,
            access_modifier=access,
            is_abstract=is_abstract,
            is_final=is_final,
            var_blocks=var_blocks,
            comment=pou_comment,
            pragmas=pragmas,
        )

        cst_node = CstNode(
            kind=CstNodeKind.POU_SIGNATURE,
            span=total_span,
            children=var_csts,
        )
        return ast_node, cst_node

    # =========================================================================
    # Method & Property Declarations
    # =========================================================================

    def parse_method_declaration(self) -> tuple[MethodDecl, CstNode]:
        start_tok = self.advance()
        start_span = start_tok.span
        end_span = start_span

        access = "PUBLIC"
        is_abstract = False
        is_final = False

        while self.peek().type in (
            TokenType.KEYWORD_ABSTRACT,
            TokenType.KEYWORD_FINAL,
            TokenType.KEYWORD_PUBLIC,
            TokenType.KEYWORD_PROTECTED,
            TokenType.KEYWORD_PRIVATE,
            TokenType.KEYWORD_INTERNAL,
        ):
            mod_tok = self.advance()
            if mod_tok.type == TokenType.KEYWORD_ABSTRACT:
                is_abstract = True
            elif mod_tok.type == TokenType.KEYWORD_FINAL:
                is_final = True
            else:
                access = mod_tok.value.upper()

        name_tok = self.expect(TokenType.IDENTIFIER, "Expected identifier for METHOD name")
        name = name_tok.value if name_tok else ""

        return_type = None
        if self.peek().type == TokenType.COLON:
            self.advance()
            return_type, end_span = self._parse_type_specifier()

        var_blocks, var_csts = self.parse_all_var_blocks()
        if var_blocks:
            end_span = var_blocks[-1].span

        if self.peek().type == TokenType.KEYWORD_END_METHOD:
            end_kw = self.advance()
            end_span = end_kw.span

        total_span = SourceSpan.merge(start_span, end_span)
        pragmas = self._extract_pragmas(total_span)
        method_comment = self._extract_doc_comment(start_span)

        ast_node = MethodDecl(
            span=total_span,
            name=name,
            return_type=return_type,
            access_modifier=access,
            is_abstract=is_abstract,
            is_final=is_final,
            var_blocks=var_blocks,
            comment=method_comment,
            pragmas=pragmas,
        )
        cst_node = CstNode(
            kind=CstNodeKind.METHOD_SIGNATURE,
            span=total_span,
            children=var_csts,
        )
        return ast_node, cst_node

    def parse_property_declaration(self) -> tuple[PropertyDecl, CstNode]:
        start_tok = self.advance()
        start_span = start_tok.span
        end_span = start_span

        access = "PUBLIC"
        is_abstract = False

        while self.peek().type in (
            TokenType.KEYWORD_ABSTRACT,
            TokenType.KEYWORD_PUBLIC,
            TokenType.KEYWORD_PROTECTED,
            TokenType.KEYWORD_PRIVATE,
            TokenType.KEYWORD_INTERNAL,
        ):
            mod_tok = self.advance()
            if mod_tok.type == TokenType.KEYWORD_ABSTRACT:
                is_abstract = True
            else:
                access = mod_tok.value.upper()

        name_tok = self.expect(TokenType.IDENTIFIER, "Expected identifier for PROPERTY name")
        name = name_tok.value if name_tok else ""

        type_name = ""
        if self.peek().type == TokenType.COLON:
            self.advance()
            type_name, end_span = self._parse_type_specifier()

        var_blocks, var_csts = self.parse_all_var_blocks()
        if var_blocks:
            end_span = var_blocks[-1].span

        if self.peek().type == TokenType.KEYWORD_END_PROPERTY:
            end_kw = self.advance()
            end_span = end_kw.span

        total_span = SourceSpan.merge(start_span, end_span)
        pragmas = self._extract_pragmas(total_span)
        prop_comment = self._extract_doc_comment(start_span)

        if not type_name:
            self.diagnostics.append(
                SyntaxDiagnostic(
                    message=f"PROPERTY '{name}' requires an explicit data type",
                    span=total_span,
                    severity=DiagnosticSeverity.ERROR,
                    code="TC-DECL-002",
                )
            )

        ast_node = PropertyDecl(
            span=total_span,
            name=name,
            type_name=type_name,
            access_modifier=access,
            is_abstract=is_abstract,
            var_blocks=var_blocks,
            comment=prop_comment,
            pragmas=pragmas,
        )
        cst_node = CstNode(
            kind=CstNodeKind.PROPERTY_SIGNATURE,
            span=total_span,
            children=var_csts,
        )
        return ast_node, cst_node

    # =========================================================================
    # Interface Declaration
    # =========================================================================

    def parse_interface_declaration(self) -> tuple[InterfaceDecl, CstNode]:
        start_tok = self.advance()
        start_span = start_tok.span
        end_span = start_span

        name_tok = self.expect(TokenType.IDENTIFIER, "Expected identifier for INTERFACE name")
        name = name_tok.value if name_tok else ""

        extends_list: list[str] = []
        if self.peek().type == TokenType.KEYWORD_EXTENDS:
            self.advance()
            while not self.is_eof():
                ext_tok = self.expect(TokenType.IDENTIFIER, "Expected base interface name")
                if ext_tok:
                    extends_list.append(ext_tok.value)
                    end_span = ext_tok.span
                if self.peek().type == TokenType.COMMA:
                    self.advance()
                else:
                    break

        if self.peek().type == TokenType.KEYWORD_END_INTERFACE:
            end_kw = self.advance()
            end_span = end_kw.span

        total_span = SourceSpan.merge(start_span, end_span)
        pragmas = self._extract_pragmas(total_span)
        itf_comment = self._extract_doc_comment(start_span)

        ast_node = InterfaceDecl(
            span=total_span,
            name=name,
            extends_interfaces=extends_list,
            comment=itf_comment,
            pragmas=pragmas,
        )
        cst_node = CstNode(kind=CstNodeKind.INTERFACE_SIGNATURE, span=total_span)
        return ast_node, cst_node

    # =========================================================================
    # TYPE / DUT Declaration (STRUCT, ENUM, UNION, ALIAS)
    # =========================================================================

    def parse_type_declaration(self) -> tuple[TypeDecl, CstNode]:
        start_tok = self.advance()  # TYPE
        start_span = start_tok.span
        end_span = start_span

        access = "PUBLIC"
        while self.peek().type in (
            TokenType.KEYWORD_PUBLIC,
            TokenType.KEYWORD_PROTECTED,
            TokenType.KEYWORD_PRIVATE,
            TokenType.KEYWORD_INTERNAL,
        ):
            mod_tok = self.advance()
            access = mod_tok.value.upper()

        name_tok = self.expect(TokenType.IDENTIFIER, "Expected type name after TYPE")
        name = name_tok.value if name_tok else ""

        extends_type: Optional[str] = None
        if self.peek().type == TokenType.KEYWORD_EXTENDS:
            self.advance()
            ext_tok = self.expect(TokenType.IDENTIFIER, "Expected base type name after EXTENDS")
            if ext_tok:
                extends_type = ext_tok.value

        self.expect(TokenType.COLON, "Expected ':' after type name")

        # Now distinguish ENUM ( ... ) or STRUCT or UNION or ALIAS
        tok_body = self.peek()

        if tok_body.type == TokenType.PAREN_OPEN:
            # ENUM: TYPE E_Color : ( Red := 0, Green, Blue ) INT := 0;
            enum_type, enum_cst = self.parse_enum_body()
            body_node: Union[EnumType, StructType, UnionType, str] = enum_type
            cst_body = enum_cst
        elif tok_body.type == TokenType.KEYWORD_STRUCT:
            # STRUCT: TYPE ST_Data : STRUCT ... END_STRUCT
            struct_type, struct_cst = self.parse_struct_body(extends_type)
            body_node = struct_type
            cst_body = struct_cst
        elif tok_body.type == TokenType.KEYWORD_UNION:
            # UNION: TYPE U_Data : UNION ... END_UNION
            union_type, union_cst = self.parse_union_body()
            body_node = union_type
            cst_body = union_cst
        else:
            # ALIAS / SUBRANGE / ARRAY TYPE: e.g. TYPE T_MaxString : STRING(255); END_TYPE
            # or TYPE T_Arr : ARRAY[1..10] OF INT; END_TYPE
            # or TYPE T_Sub : INT(1..10) := 5; END_TYPE
            type_tokens: list[str] = []
            bracket_depth = 0
            paren_depth = 0
            while not self.is_eof():
                t_peek = self.peek()
                if t_peek.type == TokenType.BRACKET_OPEN:
                    bracket_depth += 1
                elif t_peek.type == TokenType.BRACKET_CLOSE:
                    if bracket_depth > 0:
                        bracket_depth -= 1
                elif t_peek.type == TokenType.PAREN_OPEN:
                    paren_depth += 1
                elif t_peek.type == TokenType.PAREN_CLOSE:
                    if paren_depth > 0:
                        paren_depth -= 1
                elif t_peek.type in (TokenType.SEMICOLON, TokenType.KEYWORD_END_TYPE):
                    if bracket_depth == 0 and paren_depth == 0:
                        break
                elif t_peek.type == TokenType.ASSIGN:
                    if bracket_depth == 0 and paren_depth == 0:
                        break

                t = self.advance()
                type_tokens.append(t.value)
                end_span = t.span
            body_node = " ".join(type_tokens).strip()
            cst_body = CstNode(kind=CstNodeKind.TYPE_SIGNATURE, span=SourceSpan.merge(start_span, end_span))

            # Initial value e.g. := 5;
            if self.peek().type == TokenType.ASSIGN:
                self.advance()
                init_tokens: list[str] = []
                bracket_depth = 0
                paren_depth = 0
                while not self.is_eof():
                    t_peek = self.peek()
                    if t_peek.type == TokenType.BRACKET_OPEN:
                        bracket_depth += 1
                    elif t_peek.type == TokenType.BRACKET_CLOSE:
                        if bracket_depth > 0:
                            bracket_depth -= 1
                    elif t_peek.type == TokenType.PAREN_OPEN:
                        paren_depth += 1
                    elif t_peek.type == TokenType.PAREN_CLOSE:
                        if paren_depth > 0:
                            paren_depth -= 1
                    elif t_peek.type in (TokenType.SEMICOLON, TokenType.KEYWORD_END_TYPE):
                        if bracket_depth == 0 and paren_depth == 0:
                            break

                    t = self.advance()
                    init_tokens.append(t.value)
                    end_span = t.span

        if self.peek().type == TokenType.SEMICOLON:
            self.advance()

        if self.peek().type == TokenType.KEYWORD_END_TYPE:
            end_kw = self.advance()
            end_span = end_kw.span

        total_span = SourceSpan.merge(start_span, end_span)
        pragmas = self._extract_pragmas(total_span)
        type_comment = self._extract_doc_comment(start_span)

        # TC-DECL-007: Array bound check on type definition
        if isinstance(body_node, str) and "ARRAY" in body_node.upper():
            import re
            for m in re.finditer(r'(-?\d+)\s*\.\.\s*(-?\d+)', body_node):
                low_b = int(m.group(1))
                high_b = int(m.group(2))
                if low_b > high_b:
                    self.diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"Array lower bound {low_b} exceeds upper bound {high_b}",
                            span=total_span,
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-DECL-007",
                        )
                    )

        ast_node = TypeDecl(
            span=total_span,
            name=name,
            definition=body_node,
            extends_type=extends_type,
            access_modifier=access,
            comment=type_comment,
            pragmas=pragmas,
        )
        cst_node = CstNode(
            kind=CstNodeKind.TYPE_SIGNATURE,
            span=total_span,
            children=[cst_body],
        )
        return ast_node, cst_node

    def parse_enum_body(self) -> tuple[EnumType, CstNode]:
        start_tok = self.advance()  # (
        start_span = start_tok.span
        end_span = start_span

        members: list[EnumMember] = []
        cst_members: list[CstNode] = []

        while not self.is_eof() and self.peek().type != TokenType.PAREN_CLOSE:
            m_name_tok = self.expect(TokenType.IDENTIFIER, "Expected enum member identifier")
            if not m_name_tok:
                # Recovery: skip token
                self.advance()
                continue

            m_name = m_name_tok.value
            m_val = None
            m_span = m_name_tok.span

            if self.peek().type == TokenType.ASSIGN:
                self.advance()
                val_tokens: list[Token] = []
                while not self.is_eof() and self.peek().type not in (
                    TokenType.COMMA,
                    TokenType.PAREN_CLOSE,
                    TokenType.SEMICOLON,
                    TokenType.KEYWORD_END_TYPE,
                ):
                    val_tokens.append(self.advance())
                if val_tokens:
                    m_val = " ".join(t.value for t in val_tokens).strip()
                    m_span = SourceSpan.merge(m_name_tok.span, val_tokens[-1].span)

            m_pragmas = self._extract_pragmas(m_span)
            m_comment = self._extract_doc_comment(m_span)
            member_node = EnumMember(
                span=m_span,
                name=m_name,
                value=m_val,
                comment=m_comment,
                pragmas=m_pragmas,
            )
            members.append(member_node)
            cst_members.append(CstNode(kind=CstNodeKind.ENUM_MEMBER, span=m_span))

            if self.peek().type == TokenType.COMMA:
                self.advance()
            else:
                break

        close_tok = self.expect(TokenType.PAREN_CLOSE, "Expected ')' closing enum definition")
        if close_tok:
            end_span = close_tok.span

        # Optional base type after ')' e.g. ) DINT := 0; or ) DINT := Idle; or ) DINT;
        base_type = "INT"
        if not self.is_eof() and self.peek().type not in (
            TokenType.SEMICOLON,
            TokenType.KEYWORD_END_TYPE,
        ):
            b_tok = self.advance()
            base_type = b_tok.value
            end_span = b_tok.span

            # Optional default initial value after enum base type: e.g. := Idle; or := 0;
            if self.peek().type == TokenType.ASSIGN:
                self.advance()
                while not self.is_eof() and self.peek().type not in (
                    TokenType.SEMICOLON,
                    TokenType.KEYWORD_END_TYPE,
                ):
                    init_tok = self.advance()
                    end_span = init_tok.span

        total_span = SourceSpan.merge(start_span, end_span)
        ast_enum = EnumType(span=total_span, base_type=base_type, members=members)
        cst_enum = CstNode(kind=CstNodeKind.ENUM_BLOCK, span=total_span, children=cst_members)
        return ast_enum, cst_enum

    def parse_struct_body(self, extends_type: Optional[str]) -> tuple[StructType, CstNode]:
        start_tok = self.advance()  # STRUCT
        start_span = start_tok.span
        end_span = start_span

        fields: list[VarDecl] = []
        cst_fields: list[CstNode] = []

        while not self.is_eof() and self.peek().type != TokenType.KEYWORD_END_STRUCT:
            if self.peek().type == TokenType.KEYWORD_END_TYPE:
                break
            var_decls, var_csts = self.parse_single_var_decl()
            if var_decls:
                fields.extend(var_decls)
                if var_csts:
                    cst_fields.extend(var_csts)

        if self.peek().type == TokenType.KEYWORD_END_STRUCT:
            end_kw = self.advance()
            end_span = end_kw.span

        total_span = SourceSpan.merge(start_span, end_span)
        ast_struct = StructType(span=total_span, fields=fields, extends_type=extends_type)
        cst_struct = CstNode(kind=CstNodeKind.STRUCT_BLOCK, span=total_span, children=cst_fields)
        return ast_struct, cst_struct

    def parse_union_body(self) -> tuple[UnionType, CstNode]:
        start_tok = self.advance()  # UNION
        start_span = start_tok.span
        end_span = start_span

        fields: list[VarDecl] = []
        cst_fields: list[CstNode] = []

        while not self.is_eof() and self.peek().type != TokenType.KEYWORD_END_UNION:
            if self.peek().type == TokenType.KEYWORD_END_TYPE:
                break
            var_decls, var_csts = self.parse_single_var_decl()
            if var_decls:
                fields.extend(var_decls)
                if var_csts:
                    cst_fields.extend(var_csts)

        if self.peek().type == TokenType.KEYWORD_END_UNION:
            end_kw = self.advance()
            end_span = end_kw.span

        total_span = SourceSpan.merge(start_span, end_span)
        ast_union = UnionType(span=total_span, fields=fields)
        cst_union = CstNode(kind=CstNodeKind.UNION_BLOCK, span=total_span, children=cst_fields)
        return ast_union, cst_union

    # =========================================================================
    # VAR Blocks & Variables
    # =========================================================================

    def parse_all_var_blocks(self) -> tuple[list[VarBlock], list[CstNode]]:
        var_blocks: list[VarBlock] = []
        cst_blocks: list[CstNode] = []

        while not self.is_eof():
            tok = self.peek()
            if tok.type in (
                TokenType.KEYWORD_VAR,
                TokenType.KEYWORD_VAR_INPUT,
                TokenType.KEYWORD_VAR_OUTPUT,
                TokenType.KEYWORD_VAR_IN_OUT,
                TokenType.KEYWORD_VAR_GLOBAL,
                TokenType.KEYWORD_VAR_TEMP,
                TokenType.KEYWORD_VAR_STAT,
                TokenType.KEYWORD_VAR_INST,
                TokenType.KEYWORD_VAR_CONFIG,
                TokenType.KEYWORD_VAR_EXTERNAL,
                TokenType.KEYWORD_VAR_GENERIC,
            ):
                block, cst = self.parse_var_block()
                var_blocks.append(block)
                cst_blocks.append(cst)
            else:
                break

        return var_blocks, cst_blocks

    def parse_var_block(self) -> tuple[VarBlock, CstNode]:
        start_tok = self.advance()
        block_type = start_tok.value.upper()
        start_span = start_tok.span
        end_span = start_span

        is_constant = False
        is_retain = False
        is_persistent = False
        is_non_retain = False
        is_read_only = False

        if start_tok.type == TokenType.KEYWORD_VAR_GENERIC and self.peek().type == TokenType.KEYWORD_CONSTANT:
            self.advance()
            block_type = "VAR_GENERIC CONSTANT"
            is_constant = True

        # Modifiers e.g. VAR_GLOBAL CONSTANT RETAIN NON_RETAIN READ_ONLY
        while self.peek().type in (
            TokenType.KEYWORD_CONSTANT,
            TokenType.KEYWORD_RETAIN,
            TokenType.KEYWORD_PERSISTENT,
            TokenType.KEYWORD_NON_RETAIN,
            TokenType.KEYWORD_READ_ONLY,
            TokenType.KEYWORD_READ_WRITE,
        ):
            mod_tok = self.advance()
            if mod_tok.type == TokenType.KEYWORD_CONSTANT:
                is_constant = True
                block_type = f"{block_type} CONSTANT"
            elif mod_tok.type == TokenType.KEYWORD_RETAIN:
                is_retain = True
            elif mod_tok.type == TokenType.KEYWORD_PERSISTENT:
                is_persistent = True
            elif mod_tok.type == TokenType.KEYWORD_NON_RETAIN:
                is_non_retain = True
            elif mod_tok.type in (TokenType.KEYWORD_READ_ONLY, TokenType.KEYWORD_READ_WRITE):
                is_read_only = (mod_tok.type == TokenType.KEYWORD_READ_ONLY)

        variables: list[VarDecl] = []
        cst_vars: list[CstNode] = []

        while not self.is_eof() and self.peek().type != TokenType.KEYWORD_END_VAR:
            # Check if encountering a new block or end keyword by accident
            if self.peek().type in (
                TokenType.KEYWORD_VAR,
                TokenType.KEYWORD_VAR_INPUT,
                TokenType.KEYWORD_VAR_OUTPUT,
                TokenType.KEYWORD_VAR_IN_OUT,
                TokenType.KEYWORD_VAR_GLOBAL,
                TokenType.KEYWORD_VAR_TEMP,
                TokenType.KEYWORD_VAR_STAT,
                TokenType.KEYWORD_VAR_INST,
                TokenType.KEYWORD_VAR_CONFIG,
                TokenType.KEYWORD_VAR_EXTERNAL,
                TokenType.KEYWORD_VAR_GENERIC,
                TokenType.KEYWORD_END_FUNCTION_BLOCK,
                TokenType.KEYWORD_END_FUNCTION,
                TokenType.KEYWORD_END_PROGRAM,
                TokenType.KEYWORD_END_METHOD,
                TokenType.KEYWORD_END_PROPERTY,
            ):
                break

            var_decls, var_csts = self.parse_single_var_decl()
            if var_decls:
                variables.extend(var_decls)
                if var_csts:
                    cst_vars.extend(var_csts)

        if self.peek().type == TokenType.KEYWORD_END_VAR:
            end_kw = self.advance()
            end_span = end_kw.span

        total_span = SourceSpan.merge(start_span, end_span)
        pragmas = self._extract_pragmas(total_span)

        # Validation rules for variables in block
        for v in variables:
            # TC-DECL-003: Constant variables must have an initial value (VAR_IN_OUT CONSTANT is a reference contract, not an initialization)
            if (is_constant or v.is_constant) and not block_type.startswith("VAR_IN_OUT"):
                if not v.initial_value or not v.initial_value.strip():
                    self.diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"Constant variable '{v.name}' must be initialized with a value",
                            span=v.span,
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-DECL-003",
                        )
                    )
            # TC-DECL-004: VAR_IN_OUT variables cannot have an initial value
            if block_type.startswith("VAR_IN_OUT") and v.initial_value:
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message=f"VAR_IN_OUT variable '{v.name}' cannot have an initial value",
                        span=v.span,
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-DECL-004",
                    )
                )
            # TC-DECL-005: VAR_TEMP variables cannot be RETAIN or PERSISTENT
            if block_type == "VAR_TEMP" and (is_retain or is_persistent or v.is_retain or v.is_persistent):
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message=f"VAR_TEMP variable '{v.name}' cannot be declared RETAIN or PERSISTENT",
                        span=v.span,
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-DECL-005",
                    )
                )

        ast_block = VarBlock(
            span=total_span,
            block_type=block_type,
            is_constant=is_constant,
            is_retain=is_retain,
            is_persistent=is_persistent,
            is_non_retain=is_non_retain,
            is_read_only=is_read_only,
            variables=variables,
            pragmas=pragmas,
        )
        cst_block = CstNode(
            kind=CstNodeKind.VAR_BLOCK,
            span=total_span,
            children=cst_vars,
        )
        return ast_block, cst_block

    def parse_single_var_decl(self) -> tuple[list[VarDecl], list[CstNode]]:
        tok = self.peek()
        if tok.type not in (TokenType.IDENTIFIER, TokenType.KEYWORD_CONSTANT):
            # Recovery: advance one token
            self.advance()
            return [], []

        # List of (name, address, span)
        vars_info: list[tuple[str, Optional[str], SourceSpan]] = []
        name_toks = [self.advance()]
        while self.peek().type == TokenType.DOT:
            self.advance()
            if self.peek().type in (TokenType.IDENTIFIER, TokenType.INT_LITERAL):
                name_toks.append(self.advance())

        name_val = ".".join(t.value for t in name_toks)
        start_span = SourceSpan.merge(name_toks[0].span, name_toks[-1].span)

        first_addr = None
        if self.peek().type == TokenType.KEYWORD_AT:
            self.advance()
            addr_tok = self.expect(TokenType.DIRECT_ADDRESS, "Expected direct address e.g. %I* after AT")
            if addr_tok:
                first_addr = addr_tok.value
        vars_info.append((name_val, first_addr, start_span))

        # Comma-separated variable names: a [AT %I*], b [AT %I*], c : INT;
        while self.peek().type == TokenType.COMMA:
            self.advance()
            next_toks: list[Token] = []
            next_name_tok = self.expect(TokenType.IDENTIFIER, "Expected variable name after ','")
            if next_name_tok:
                next_toks.append(next_name_tok)
                while self.peek().type == TokenType.DOT:
                    self.advance()
                    if self.peek().type in (TokenType.IDENTIFIER, TokenType.INT_LITERAL):
                        next_toks.append(self.advance())

                next_val = ".".join(t.value for t in next_toks)
                next_span = SourceSpan.merge(next_toks[0].span, next_toks[-1].span)

                next_addr = None
                if self.peek().type == TokenType.KEYWORD_AT:
                    self.advance()
                    addr_tok = self.expect(TokenType.DIRECT_ADDRESS, "Expected direct address e.g. %I* after AT")
                    if addr_tok:
                        next_addr = addr_tok.value
                vars_info.append((next_val, next_addr, next_span))

        end_span = vars_info[-1][2]

        # Trailing AT %I* direct address after all names (if not specified per variable)
        if self.peek().type == TokenType.KEYWORD_AT:
            self.advance()
            addr_tok = self.expect(TokenType.DIRECT_ADDRESS, "Expected direct address e.g. %I* after AT")
            if addr_tok:
                end_span = addr_tok.span
                for i in range(len(vars_info)):
                    if vars_info[i][1] is None:
                        vars_info[i] = (vars_info[i][0], addr_tok.value, vars_info[i][2])

        # Expect :
        if not self.match(TokenType.COLON):
            self.diagnostics.append(
                SyntaxDiagnostic(
                    message=f"Expected ':' after variable name '{vars_info[0][0]}'",
                    span=self.peek().span,
                )
            )
            # Recovery: skip to semicolon
            self._skip_to_semicolon()
            return [], []

        # Type expression (can be ARRAY[..] OF ..., POINTER TO ..., REFERENCE TO ..., or type name with FB_init params)
        type_tokens: list[str] = []
        bracket_depth = 0
        paren_depth = 0
        while not self.is_eof():
            t_peek = self.peek()
            if t_peek.type == TokenType.BRACKET_OPEN:
                bracket_depth += 1
            elif t_peek.type == TokenType.BRACKET_CLOSE:
                if bracket_depth > 0:
                    bracket_depth -= 1
            elif t_peek.type == TokenType.PAREN_OPEN:
                paren_depth += 1
            elif t_peek.type == TokenType.PAREN_CLOSE:
                if paren_depth > 0:
                    paren_depth -= 1
            elif t_peek.type in (
                TokenType.SEMICOLON,
                TokenType.KEYWORD_END_VAR,
                TokenType.KEYWORD_END_STRUCT,
                TokenType.KEYWORD_END_UNION,
            ):
                if bracket_depth == 0 and paren_depth == 0:
                    break
            elif t_peek.type == TokenType.ASSIGN:
                if bracket_depth == 0 and paren_depth == 0:
                    break

            t = self.advance()
            type_tokens.append(t.value)
            end_span = t.span

        type_name = " ".join(type_tokens).strip()

        # Initial value e.g. := 10; or := [1, 2, 3]; or := (a := 1);
        initial_val = None
        if self.peek().type == TokenType.ASSIGN:
            self.advance()
            init_tokens: list[str] = []
            bracket_depth = 0
            paren_depth = 0
            while not self.is_eof():
                t_peek = self.peek()
                if t_peek.type == TokenType.BRACKET_OPEN:
                    bracket_depth += 1
                elif t_peek.type == TokenType.BRACKET_CLOSE:
                    if bracket_depth > 0:
                        bracket_depth -= 1
                elif t_peek.type == TokenType.PAREN_OPEN:
                    paren_depth += 1
                elif t_peek.type == TokenType.PAREN_CLOSE:
                    if paren_depth > 0:
                        paren_depth -= 1
                elif t_peek.type in (
                    TokenType.SEMICOLON,
                    TokenType.KEYWORD_END_VAR,
                    TokenType.KEYWORD_END_STRUCT,
                    TokenType.KEYWORD_END_UNION,
                ):
                    if bracket_depth == 0 and paren_depth == 0:
                        break

                t = self.advance()
                init_tokens.append(t.value)
                end_span = t.span
            initial_val = " ".join(init_tokens).strip()

        if self.peek().type == TokenType.SEMICOLON:
            semi_tok = self.advance()
            end_span = semi_tok.span

        total_span = SourceSpan.merge(start_span, end_span)
        pragmas = self._extract_pragmas(total_span)
        doc_comment = self._extract_doc_comment(total_span)

        # TC-DECL-007: Array bound check
        if "ARRAY" in type_name.upper():
            import re
            for m in re.finditer(r'(-?\d+)\s*\.\.\s*(-?\d+)', type_name):
                low_b = int(m.group(1))
                high_b = int(m.group(2))
                if low_b > high_b:
                    self.diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"Array lower bound {low_b} exceeds upper bound {high_b}",
                            span=total_span,
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-DECL-007",
                        )
                    )

        decls: list[VarDecl] = []
        csts: list[CstNode] = []
        for name_val, addr_val, n_span in vars_info:
            v_span = SourceSpan.merge(n_span, end_span)
            v_node = VarDecl(
                span=v_span,
                name=name_val,
                type_name=type_name,
                initial_value=initial_val,
                address=addr_val,
                comment=doc_comment,
                pragmas=pragmas,
            )
            decls.append(v_node)
            csts.append(CstNode(kind=CstNodeKind.VAR_DECLARATION, span=v_span))

        return decls, csts

    def _skip_to_semicolon(self) -> None:
        while not self.is_eof() and self.peek().type not in (
            TokenType.SEMICOLON,
            TokenType.KEYWORD_END_VAR,
            TokenType.KEYWORD_END_STRUCT,
            TokenType.KEYWORD_END_UNION,
        ):
            self.advance()
        if self.peek().type == TokenType.SEMICOLON:
            self.advance()
