"""File Processor: orchestrates the full format pipeline per file.

Pipeline:
1. Read file (bytes + encoding detection)
2. Parse XML (CDATA-aware)
3. Format ST code in each CDATA block
4. Syntax integrity check (token comparison before/after)
5. Format XML structure (sort, indent, attribute order)
6. Validate XML structure
7. Serialize back to XML (CDATA-preserving)
8. Compare hash: skip write if unchanged
9. Atomic write with backup
"""
from __future__ import annotations

import fnmatch
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

from formatter.config import FormatterConfig, load_config
from formatter.constants import FORMATTABLE_EXTENSIONS, TokenType
from formatter.st_lexer import tokenize
from formatter.diff_reporter import generate_diff
from formatter.safe_writer import SafeFileWriter
from formatter.st_parse_utils import RE_IF_MULTILINE_CALL
from twincat_core.syntax import TokenType as CoreTokenType, tokenize_st, validate_st_syntax_in_xml
from twincat_core.xml import CdataKind, CdataSpan, patch_by_filter, read_tc_xml
from formatter.st_alignment import (
    align_assignments, align_chained_init_assignments, align_init_injection_if_bodies,
    align_pre_chained_true_orphans, align_ref_to_preceding_assign, align_declarations, align_fb_call_params, align_array_struct_inits, align_inline_comments,
    normalize_multi_var_name_commas,
    align_for_body_assignments,
    compact_orphan_overpadded_assigns, compact_same_col_outlier_assigns,
    normalize_case_arm_single_assignments,
    expand_tight_assignment_spacing,
    normalize_header_and_comment_spacing,
    _find_assign_pos, _is_simple_assignment,
)
from formatter.st_formatter import format_st_code, split_disable_regions, fix_end_if_indent_safe
from formatter.st_line_wrapper import (
    join_wrapped_assignments,
    wrap_chained_binary_expression,
    wrap_long_lines,
)
from formatter.st_statement_normalize import did_normalize, normalize_statements, normalize_and_check
from formatter.types import BatchResult, FormatResult, FormatScope, FormatRegion, MemberFilter, ValidationIssue
from formatter.utils import compute_sha256, normalize_line_endings, safe_read_file
from formatter.xml_formatter import format_xml_structure, restore_cdata
from formatter.xml_validator import validate_twincat_xml


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_file(
    path: str,
    config: FormatterConfig,
    *,
    dry_run: bool = False,
    validate: bool = True,
    format_st: bool = True,
    format_xml: bool = True,
    sort_xml: bool = False,
    scope: FormatScope | None = None,
) -> FormatResult:
    """Process a single TwinCAT file through the format pipeline.

    scope: Optional FormatScope to limit formatting to specific regions/members.
           None or FormatScope() means format everything (default).
           When scope targets specific regions/members, XML formatting is
           automatically disabled to avoid whole-file restructuring.
    """
    # When scope is set (partial formatting), disable XML formatting/sorting
    # to only touch the targeted ST code regions.
    _scoped = scope is not None and (
        scope.region != FormatRegion.ALL or scope.member_name or scope.member_filter
    )
    if _scoped:
        format_xml = False
        sort_xml = False

    try:
        raw_bytes, encoding = safe_read_file(path)
        original_text = raw_bytes.decode(encoding)
        original_hash = compute_sha256(raw_bytes)
    except (OSError, UnicodeDecodeError) as e:
        return FormatResult(
            path=path, success=False, changed=False,
            errors=(f"Read error: {e}",),
        )

    # Detect original line ending for "auto" mode
    if config.line_ending == "auto":
        if b"\r\n" in raw_bytes:
            line_ending = "\r\n"
        else:
            line_ending = "\n"
    elif config.line_ending == "crlf":
        line_ending = "\r\n"
    else:
        line_ending = "\n"
    text = normalize_line_endings(original_text, "\n")

    warnings: list[str] = []
    errors: list[str] = []
    file_issues: list[ValidationIssue] = []

    # 1. Pre-format syntax safety check (reject broken source files, leave untouched)
    if format_st and config.safety.syntax_check:
        pre_syntax_errors = validate_st_syntax_in_xml(text)
        if pre_syntax_errors:
            return FormatResult(
                path=path, success=False, changed=False,
                errors=tuple(f"Pre-format syntax error: {e}" for e in pre_syntax_errors),
                warnings=tuple(warnings),
            )

    if validate:
        issues = validate_twincat_xml(
            text, path,
            check_name_match=config.validation.check_name_match,
            check_guids=config.validation.check_guids,
            check_structure=config.validation.check_structure,
        )
        file_issues.extend(issues)
        for issue in issues:
            if issue.level == "error":
                errors.append(f"[{issue.rule}] {issue.message}")
            else:
                warnings.append(f"[{issue.rule}] {issue.message}")

    if format_xml:
        try:
            formatted_xml, cdata_map = format_xml_structure(
                text,
                indent_size=config.xml.indent_size,
                sort_elements=sort_xml,
                line_ending="\n",
            )
        except Exception as e:
            return FormatResult(
                path=path, success=False, changed=False,
                errors=(f"XML format error: {e}",),
            )

        if format_st:
            allowed_keys = _resolve_scope_keys(formatted_xml, cdata_map, scope)
            for key, cdata_content in cdata_map.items():
                if cdata_content.strip() and key in allowed_keys:
                    formatted_st = _format_st_pipeline(cdata_content, config)
                    formatted_st = formatted_st.rstrip("\n") + "\n"
                    cdata_map[key] = formatted_st

        result_text = restore_cdata(formatted_xml, cdata_map)
    elif format_st:
        result_text = _format_st_in_cdata_blocks(text, config, scope)
    else:
        result_text = text

    # Do not write a trailing newline after </TcPlcObject>
    result_text = result_text.rstrip("\n").rstrip("\r")

    # Keep LF version for diff (avoids spurious line-ending changes in output)
    result_text_lf = result_text

    if line_ending != "\n":
        result_text = result_text.replace("\n", line_ending)

    # Syntax integrity check (fast token comparison, <1ms overhead)
    if format_st and config.safety.syntax_check:
        post_syntax_errors = validate_st_syntax_in_xml(result_text)
        if post_syntax_errors:
            return FormatResult(
                path=path, success=False, changed=False,
                errors=tuple(f"Post-format syntax error: {e}" for e in post_syntax_errors),
                warnings=tuple(warnings),
            )

        integrity_errors = check_syntax_integrity(
            normalize_line_endings(original_text, "\n"),
            normalize_line_endings(result_text, "\n"),
        )
        if integrity_errors:
            return FormatResult(
                path=path, success=False, changed=False,
                errors=tuple(f"Syntax integrity: {e}" for e in integrity_errors),
                warnings=tuple(warnings),
            )

    had_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
    write_encoding = "utf-8-sig" if had_bom else "utf-8"
    result_bytes = result_text.encode(write_encoding)
    new_hash = compute_sha256(result_bytes)
    changed = original_hash != new_hash

    diff_text = ""
    if changed and dry_run:
        diff_text = generate_diff(path, text, result_text_lf)

    if changed and not dry_run:
        writer = SafeFileWriter()
        summary = writer.write_safe(
            path, result_bytes,
            backup=config.safety.backup,
            delete_backup_on_success=config.safety.delete_backup_on_success,
        )
        if summary.error:
            return FormatResult(
                path=path, success=False, changed=False,
                original_hash=original_hash, formatted_hash=new_hash,
                errors=(summary.error,), warnings=tuple(warnings),
            )

    return FormatResult(
        path=path,
        success=True,
        changed=changed,
        original_hash=original_hash,
        formatted_hash=new_hash,
        errors=tuple(errors),
        warnings=tuple(warnings),
        diff=diff_text,
        validation_issues=tuple(file_issues),
    )


def _process_file_worker(
    args: tuple[str, FormatterConfig, bool, bool, bool, bool, bool, FormatScope | None],
) -> FormatResult:
    """Helper worker for multi-threaded batch execution."""
    p, config, dry_run, validate, format_st, format_xml, sort_xml, scope = args
    try:
        return process_file(
            p, config,
            dry_run=dry_run, validate=validate,
            format_st=format_st, format_xml=format_xml,
            sort_xml=sort_xml, scope=scope,
        )
    except Exception as exc:
        return FormatResult(
            path=p,
            success=False,
            changed=False,
            errors=(f"Unexpected error: {exc}",),
        )


def process_batch(
    paths: Sequence[str],
    config: FormatterConfig,
    *,
    dry_run: bool = False,
    validate: bool = True,
    format_st: bool = True,
    format_xml: bool = True,
    sort_xml: bool = False,
    max_workers: int | None = None,
    scope: FormatScope | None = None,
) -> BatchResult:
    """Process multiple files with optional parallelism via ThreadPoolExecutor."""
    batch = BatchResult(total=len(paths))

    if len(paths) <= 1 or max_workers == 1:
        for p in paths:
            result = process_file(
                p, config,
                dry_run=dry_run, validate=validate,
                format_st=format_st, format_xml=format_xml,
                sort_xml=sort_xml, scope=scope,
            )
            _accumulate_result(batch, result)
    else:
        effective_workers = max_workers or min(os.cpu_count() or 4, 8)
        tasks = [
            (p, config, dry_run, validate, format_st, format_xml, sort_xml, scope)
            for p in paths
        ]
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            for result in executor.map(_process_file_worker, tasks):
                _accumulate_result(batch, result)

    return batch


_EXCLUDES_LOWER: set[str] = {
    ".git", "node_modules", "_libraries", "_compileinfo", "versions",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "bin", "obj",
}


def discover_files(
    paths: Sequence[str],
    *,
    recursive: bool = True,
    include: str | None = None,
    exclude: str | None = None,
) -> list[str]:
    """Discover formattable TwinCAT files from given paths.

    Supports files, directories, and glob patterns.
    """
    result: list[str] = []

    for p in paths:
        if not p:
            continue
        path = Path(p)
        if path.is_file():
            if _is_formattable(str(path), include, exclude):
                result.append(str(path.resolve()))
        elif path.is_dir():
            if recursive:
                for root, dirs, files in os.walk(path):
                    dirs[:] = [d for d in dirs if d.lower() not in _EXCLUDES_LOWER]
                    for f in sorted(files):
                        full = os.path.join(root, f)
                        if _is_formattable(full, include, exclude):
                            result.append(str(Path(full).resolve()))
            else:
                for f in sorted(path.iterdir()):
                    if f.is_file() and _is_formattable(str(f), include, exclude):
                        result.append(str(f.resolve()))

    return result


def discover_project_files(project_path: str) -> list[str]:
    """Discover all formattable TwinCAT files from a .sln or .plcproj.

    Searches the project directory tree for all TcPOU/TcDUT/TcGVL/TcIO files.
    For .sln: scans the entire solution directory.
    For .plcproj: scans the plcproj parent directory.
    """
    if not project_path:
        return []
    p = Path(project_path)
    if not p.exists():
        return []

    if p.suffix.lower() in (".sln", ".plcproj"):
        search_root = p.parent
    elif p.is_dir():
        search_root = p
    else:
        return []

    result: list[str] = []
    for root, dirs, files in os.walk(search_root):
        dirs[:] = [d for d in dirs if d.lower() not in _EXCLUDES_LOWER]
        for f in sorted(files):
            if _is_formattable(f, None, None):
                result.append(str(Path(os.path.join(root, f)).resolve()))

    return result


def _format_st_pipeline(source: str, config: FormatterConfig) -> str:
    """Run the full ST formatting pipeline on a code block.

    Respects {formatting.disable}/{formatting.enable} regions: disabled regions
    are passed through verbatim without any formatting applied.

    Reindent runs across enabled segments with a persistent stack so TYPE/CASE/IF
    context survives disable-region boundaries.
    """
    segments = split_disable_regions(source)

    if len(segments) == 1 and segments[0][1]:
        return _format_st_segment(source, config)

    parts: list[str] = []
    indent_stack: list | None = [] if config.indent.reindent else None

    for segment_text, should_format in segments:
        if should_format:
            if indent_stack is not None:
                from formatter.st_indent_anchor import apply_column_anchor_indentation

                lines, indent_stack = apply_column_anchor_indentation(
                    segment_text.split("\n"),
                    config.indent,
                    initial_stack=indent_stack,
                    force_all=True,
                )
                segment_text = "\n".join(lines)
            parts.append(_format_st_segment(segment_text, config, reindent=False))
        else:
            parts.append(segment_text)

    return "\n".join(parts)


_RE_FB_CALL_OPEN = re.compile(r"^(\s*)[\w.^]+(?:\s*\[[^\]]+\])*\s*\(\s*$")
_RE_ASSIGN_CALL_OPEN = re.compile(
    r"^(\s*).+:=\s*.+[A-Za-z_]\w*\s*\(\s*$",
)


def _match_multiline_call_opener(line: str) -> re.Match[str] | None:
    """Match standalone ``Fb(`` or assignment/IF call opener lines."""
    if "(" not in line:
        return None
    m = _RE_FB_CALL_OPEN.match(line)
    if m:
        return m
    m = _RE_ASSIGN_CALL_OPEN.match(line)
    if m:
        return m
    if line.rstrip().endswith("("):
        return RE_IF_MULTILINE_CALL.match(line)
    return None


def _normalize_call_param_indent(lines: list[str], call_indent: int) -> list[str]:
    """Normalize indentation of already-multiline FB call parameters.

    When a line is `word(` (opening only), re-indent subsequent param lines
    to parent_indent + call_indent until the matching closing `)` is found.
    Respects nesting: only re-indents at depth 1 (direct params).
    """
    result: list[str] = []
    i = 0
    while i < len(lines):
        m = _match_multiline_call_opener(lines[i])
        if not m:
            result.append(lines[i])
            i += 1
            continue

        parent_indent = m.group(1)
        target_indent = parent_indent + " " * call_indent
        result.append(lines[i])
        i += 1
        depth = 1  # We're inside one open paren

        while i < len(lines) and depth > 0:
            stripped = lines[i].strip()
            if not stripped:
                result.append("")
                i += 1
                continue

            # Only re-indent lines at depth 1 (direct params).
            # Preserve deeper indents (bool-chain continuations aligned to operands).
            if depth == 1:
                line_indent_len = len(lines[i]) - len(lines[i].lstrip())
                if line_indent_len > len(target_indent):
                    result.append(lines[i])
                else:
                    result.append(target_indent + stripped)
            else:
                # Deeper nested: indent relative to depth
                nested_indent = parent_indent + " " * (call_indent * depth)
                result.append(nested_indent + stripped)

            # Track depth changes
            for ch in stripped:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            i += 1

    return result


def _join_short_multiline_calls(lines: list[str], max_line: int,
                                max_params: int) -> list[str]:
    """Join multiline FB calls back to single line when the result fits.

    Pattern: `name(` on its own line followed by params and closing `)`.
    Joins only if: total params <= max_params AND joined length <= max_line.
    """
    result: list[str] = []
    i = 0
    while i < len(lines):
        m = _match_multiline_call_opener(lines[i])
        if not m:
            result.append(lines[i])
            i += 1
            continue

        # Collect the call block
        call_start = i
        prefix = lines[i].rstrip()
        i += 1
        depth = 1
        param_lines: list[str] = []

        while i < len(lines) and depth > 0:
            stripped = lines[i].strip()
            if not stripped:
                i += 1
                continue
            for ch in stripped:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            param_lines.append(stripped)
            i += 1

        if depth != 0:
            # Unmatched parens — emit original lines unchanged
            for j in range(call_start, i):
                result.append(lines[j])
            continue

        if param_lines and re.match(r"[A-Za-z_]\w*\s*\(", param_lines[0]):
            # Nested call on first continuation — keep multiline
            for j in range(call_start, i):
                result.append(lines[j])
            continue

        # Check for dangerous line comments (//) that would comment out subsequent code when joined
        has_dangerous_line_comment = "//" in prefix
        if not has_dangerous_line_comment:
            for idx, pl in enumerate(param_lines):
                if "//" in pl:
                    if idx < len(param_lines) - 1:
                        has_dangerous_line_comment = True
                        break
                    # On the last line, check if // is before the closing ')'
                    r_paren = pl.rfind(")")
                    slash_pos = pl.find("//")
                    if slash_pos < r_paren:
                        has_dangerous_line_comment = True
                        break

        if has_dangerous_line_comment:
            for j in range(call_start, i):
                result.append(lines[j])
            continue

        # Try to join: count commas at depth 0 to determine param count
        joined_params = " ".join(param_lines).lstrip()
        candidate = prefix + joined_params
        # Count top-level commas (depth 0) as param separator estimate
        n_commas = 0
        d = 0
        for ch in joined_params:
            if ch == "(":
                d += 1
            elif ch == ")":
                d -= 1
            elif ch == "," and d == 0:
                n_commas += 1
        n_params = n_commas + 1

        if n_params <= max_params and len(candidate) <= max_line:
            candidate = re.sub(r"  +(:=|=>)", r" \1", candidate)
            result.append(candidate)
        else:
            # Keep multiline — re-emit collected lines
            for j in range(call_start, i):
                result.append(lines[j])

    return result


_RE_IF_ELSIF_START = re.compile(
    r"^\s*(?:IF|ELSIF)\b",
    re.IGNORECASE,
)

_RE_BLOCK_COMMENT_MASK = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_RE_STRING_MASK = re.compile(r"'(?:''|\$.|[^'$])*'|\"(?:\"\"|\$.|[^\"$])*\"")


def _code_ends_with_then(line: str) -> int:
    """Return the index where ' THEN' starts in code (not in comment/string), or -1."""
    stripped = line.rstrip()
    if "//" in stripped:
        pos_comment = stripped.find("//")
        code_only = stripped[:pos_comment].rstrip()
    else:
        code_only = stripped

    masked = list(code_only)
    for m in _RE_BLOCK_COMMENT_MASK.finditer(code_only):
        for i in range(m.start(), m.end()):
            masked[i] = "\x01"
    safe = "".join(masked)
    for m in _RE_STRING_MASK.finditer(safe):
        for i in range(m.start(), m.end()):
            masked[i] = "\x01"
    masked_str = "".join(masked).upper()
    # Match trailing ' THEN' at depth 0
    if masked_str.endswith(" THEN"):
        pos = len(code_only) - 5
        if pos > 0 and masked[pos] == " ":
            return pos
    elif masked_str == "THEN":
        return 0
    return -1


def _pre_separate_overlength_then(lines: list[str], max_length: int) -> list[str]:
    """Separate THEN/DO from IF/ELSIF/WHILE lines before wrapping.

    Only when the full line exceeds *max_length* but the condition alone
    fits.  This prevents the chain wrapper from splitting a condition that
    the golden keeps on one line with THEN on a separate line.
    """
    result: list[str] = []
    in_block_comment = False

    for line in lines:
        stripped_raw = line.strip()

        if in_block_comment:
            result.append(line)
            if "*)" in stripped_raw:
                in_block_comment = False
            continue

        if stripped_raw.startswith("(*") and "*)" not in stripped_raw:
            in_block_comment = True
            result.append(line)
            continue

        if len(line) <= max_length:
            result.append(line)
            continue

        then_pos = _code_ends_with_then(line)
        if then_pos < 0:
            result.append(line)
            continue

        code_part = line[:then_pos].rstrip()
        if len(code_part) > max_length:
            result.append(line)
            continue

        code_stripped = _RE_BLOCK_COMMENT_MASK.sub("", line.strip()).strip()
        if not code_stripped.upper().startswith(("IF ", "ELSIF ", "WHILE ")):
            result.append(line)
            continue

        if_indent = " " * (len(line) - len(line.lstrip()))
        result.append(code_part)
        result.append(if_indent + "THEN")

    return result


def _separate_multiline_then(lines: list[str]) -> list[str]:
    """Put THEN on its own line when the IF/ELSIF condition wraps multiple lines."""
    result: list[str] = []
    in_block_comment = False

    for line in lines:
        stripped_raw = line.strip()

        if in_block_comment:
            result.append(line)
            if "*)" in stripped_raw:
                in_block_comment = False
            continue

        if stripped_raw.startswith("(*") and "*)" not in stripped_raw:
            in_block_comment = True
            result.append(line)
            continue

        then_pos = _code_ends_with_then(line)
        if then_pos < 0:
            result.append(line)
            continue

        stripped = line.strip()

        # Already a lone THEN line — fix indent to match IF/ELSIF anchor
        if stripped.upper() == "THEN":
            if_indent = " " * (len(line) - len(line.lstrip()))
            for j in range(len(result) - 1, -1, -1):
                if _RE_IF_ELSIF_START.match(result[j]):
                    if_indent = " " * (len(result[j]) - len(result[j].lstrip()))
                    break
                s = result[j].strip().upper()
                if s.startswith(("END_", "CASE ", "FOR ", "WHILE ", "REPEAT")):
                    break
                if not s:
                    continue
            result.append(if_indent + "THEN")
            continue

        # Single-line IF/ELSIF → keep THEN inline
        code_stripped = _RE_BLOCK_COMMENT_MASK.sub("", stripped).strip()
        if code_stripped.upper().startswith(("IF ", "ELSIF ")):
            result.append(line)
            continue

        code_part = line[:then_pos].rstrip()

        # Find the IF/ELSIF anchor indent by scanning backwards
        if_indent = ""
        for j in range(len(result) - 1, -1, -1):
            if _RE_IF_ELSIF_START.match(result[j]):
                if_indent = " " * (len(result[j]) - len(result[j].lstrip()))
                break
            s = result[j].strip().upper()
            if s.startswith(("END_", "CASE ", "FOR ", "WHILE ", "REPEAT")):
                break
            if not s:
                break

        result.append(code_part)
        result.append(if_indent + "THEN")

    return result


_RE_CASE_INLINE_LABEL_NUMERIC = re.compile(
    r"^(\s*)((?:\d+)\s*:(?!=)\s*)(\S.*)$",
)
_RE_CASE_INLINE_LABEL_ANY = re.compile(
    r"^(\s*)((?:\d+|[A-Za-z_]\w*)\s*:(?!=)\s*)(\S.*)$",
)


_RE_BLOCK_COMMENT_LINE = re.compile(r"^\s*\(\*", re.IGNORECASE)
_RE_FOR_LINE = re.compile(r"^\s*(?:FOR|WHILE|REPEAT)\b", re.IGNORECASE)


def _is_assign_statement(line: str) -> bool:
    """True for any single-line ``:= ... ;`` statement."""
    stripped = line.strip()
    return bool(stripped) and stripped.endswith(";") and _find_assign_pos(line) >= 0


def _is_inline_else_block_comment(body: str) -> bool:
    """True when ``ELSE (* ... *)`` should stay on one line (preserves inline comment)."""
    stripped = body.strip()
    return stripped.startswith("(*") and stripped.endswith("*)")


def _insert_blank_lines_after_assign(
    lines: list[str],
    *,
    before_comment: bool = True,
    before_for: bool = True,
    before_related_if: bool = True,
    skip_related_if_when_rhs_contains_paren: bool = True,
    after_end_if: bool = True,
) -> list[str]:
    """Insert blank lines after assignments / ``END_IF`` before block openers."""
    result: list[str] = []

    def _prev_non_empty() -> str | None:
        j = len(result) - 1
        while j >= 0 and not result[j].strip():
            j -= 1
        return result[j] if j >= 0 else None

    def _has_blank_before_append() -> bool:
        return bool(result) and not result[-1].strip()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.upper().startswith("ELSIF"):
            prev = _prev_non_empty()
            needs_blank = False
            if prev is not None and not _has_blank_before_append():
                if before_comment and _RE_BLOCK_COMMENT_LINE.match(line):
                    if _is_assign_statement(prev):
                        j = i + 1
                        while j < len(lines) and not lines[j].strip():
                            j += 1
                        if j < len(lines) and lines[j].strip().upper().startswith("IF "):
                            needs_blank = True
                elif before_for and _RE_FOR_LINE.match(line):
                    if _is_assign_statement(prev):
                        prev_indent = len(prev) - len(prev.lstrip())
                        cur_indent = len(line) - len(line.lstrip())
                        if cur_indent == prev_indent:
                            needs_blank = True
                elif before_related_if and stripped.upper().startswith("IF ") and _is_simple_assignment(prev):
                    pos = _find_assign_pos(prev)
                    if pos >= 0:
                        rhs = prev[pos + 2:].strip()
                        if "(" in rhs and skip_related_if_when_rhs_contains_paren:
                            pass
                        else:
                            lhs = prev[:pos].strip()
                            lhs_name = lhs.split()[-1] if lhs else ""
                            if lhs_name and re.match(
                                rf"^\s*IF\s+{re.escape(lhs_name)}\b",
                                line,
                                re.IGNORECASE,
                            ):
                                needs_blank = True
                elif (after_end_if
                      and not stripped.upper().startswith(("END_", "ELSE", "ELSIF", "UNTIL"))
                      and prev.strip().upper() == "END_IF"):
                    prev_indent = len(prev) - len(prev.lstrip())
                    cur_indent = len(line) - len(line.lstrip())
                    if cur_indent == prev_indent:
                        needs_blank = True
            if needs_blank:
                result.append("")
        result.append(line)

    return result


def _normalize_case_inline_body(body: str) -> str:
    """Collapse multi-space padding before ':=' when splitting inline CASE arms."""
    stripped = body.strip()
    if ":=" not in stripped:
        return stripped
    m = re.match(r"^(\s*\S+)\s{2,}:=(.*)$", stripped)
    if m:
        return m.group(1) + " :=" + m.group(2)
    return stripped


def _split_case_inline_statements(
    lines: list[str],
    indent_size: int,
    *,
    numeric_labels_only: bool = True,
    keep_else_inline_comment: bool = True,
) -> list[str]:
    """Split ``label: stmt`` onto separate lines (before_statements_in_case)."""
    label_re = _RE_CASE_INLINE_LABEL_NUMERIC if numeric_labels_only else _RE_CASE_INLINE_LABEL_ANY
    result: list[str] = []
    case_depth = 0
    in_block_comment = False

    for line in lines:
        stripped = line.strip()

        if in_block_comment:
            result.append(line)
            if "*)" in stripped:
                in_block_comment = False
            continue

        if stripped.startswith("(*") and "*)" not in stripped:
            in_block_comment = True
            result.append(line)
            continue

        upper = stripped.upper()
        if upper.startswith("CASE ") and upper.rstrip().endswith(" OF"):
            case_depth += 1
            result.append(line)
            continue
        if upper == "END_CASE":
            case_depth = max(0, case_depth - 1)
            result.append(line)
            continue

        if case_depth > 0:
            if upper.startswith("ELSE ") and not upper.startswith("ELSIF"):
                m = re.match(r"^(\s*)ELSE\s+(\S.*)$", line, re.IGNORECASE)
                if m:
                    body = m.group(2).strip()
                    if keep_else_inline_comment and _is_inline_else_block_comment(body):
                        result.append(line)
                        continue
                    result.append(m.group(1) + "ELSE")
                    result.append(m.group(1) + (" " * indent_size) + _normalize_case_inline_body(body))
                    continue
            m = label_re.match(line)
            if m:
                indent, label, body = m.groups()
                if body.strip() and ":=" in body:
                    result.append(indent + label.rstrip())
                    result.append(indent + (" " * indent_size) + _normalize_case_inline_body(body))
                    continue

        result.append(line)

    return result


def _format_st_segment(source: str, config: FormatterConfig, *, reindent: bool | None = None) -> str:
    """Format a single segment of ST code (no disable markers inside)."""
    if reindent is None:
        reindent = config.indent.reindent

    source, was_normalized = normalize_and_check(source)
    pre_lines = source.split("\n")

    effective_reindent = reindent
    force_reindent = was_normalized and reindent

    result = format_st_code(
        "\n".join(pre_lines),
        indent_size=config.indent.size,
        indent_config=config.indent,
        uppercase_keywords=config.keywords.uppercase,
        reindent=effective_reindent,
        force_reindent=force_reindent,
        max_consecutive_blanks=config.blank_lines.max_consecutive,
        normalize_spaces=config.spaces.normalize_inline,
        spaces=config.spaces,
    )

    lines = result.split("\n")
    baseline_lines = list(lines)
    heur = config.alignment_heuristics

    if (heur.split_case_inline_statements
            and config.line_breaks.before_statements_in_case):
        lines = _split_case_inline_statements(
            lines,
            config.indent.size,
            numeric_labels_only=heur.split_case_numeric_labels_only,
            keep_else_inline_comment=heur.split_case_keep_else_inline_comment,
        )

    # Join continuation lines (AND_THEN/OR_ELSE/OR at line start)
    if config.alignment.join_continuations:
        lines = _join_bool_continuations(lines, max_line=config.line_length.wrap_at)

    if heur.join_wrapped_assignments:
        lines = join_wrapped_assignments(lines, max_length=config.line_length.wrap_at)

    # Normalize already-multiline FB call param indentation
    if config.calls.normalize_param_indent:
        lines = _normalize_call_param_indent(lines, config.calls.multiline_indent)

    if config.alignment.declarations:
        lines = normalize_header_and_comment_spacing(lines)
        if config.spaces.after_comma:
            lines = normalize_multi_var_name_commas(lines)
        split_limit = (
            config.line_length.wrap_at
            if config.alignment.split_overlength_decls and config.line_length.wrap_enabled
            else 0
        )
        lines = align_declarations(
            lines,
            max_line_length=split_limit,
            align_init_operator=config.alignment.align_init_operator,
            max_init_type_spread=config.alignment.max_init_type_spread,
            align_enum_initializers=config.alignment.enum_initializers,
            align_address_assignments=config.alignment.address_assignments,
            max_enum_members_single_line=config.calls.max_enum_single_line,
            decl_comment_preserve_tight_gap=heur.decl_comment_preserve_tight_gap,
            decl_comment_preserve_source_gap=heur.decl_comment_preserve_source_gap,
            decl_comment_preserve_max_col_delta=heur.decl_comment_preserve_max_col_delta,
            decl_split_outlier_median_multiplier=heur.decl_split_outlier_median_multiplier,
            decl_split_outlier_median_add=heur.decl_split_outlier_median_add,
        )

    if config.alignment.assignments:
        if heur.expand_tight_assignment_spacing:
            lines = expand_tight_assignment_spacing(lines)
        lines = align_assignments(
            lines,
            max_spread=config.alignment.max_assign_spread,
            max_line_length=config.line_length.wrap_at if config.line_length.wrap_enabled else 0,
            bool_literal_min_group_lines=heur.bool_literal_min_group_lines,
            bool_literal_name_spread_max=heur.bool_literal_name_spread_max,
            assign_already_aligned_max_gap=heur.assign_already_aligned_max_gap,
            compact_group_min_lines=heur.compact_group_min_lines,
            compact_group_max_over_pad=heur.compact_group_max_over_pad,
            compact_three_line_count=heur.compact_three_line_count,
            compact_three_line_over_pad=heur.compact_three_line_over_pad,
            compact_pair_assigns=heur.compact_pair_assigns,
            compact_pair_min_over_pad=heur.compact_pair_min_over_pad,
            three_line_assign_group_count=heur.three_line_assign_group_count,
            three_line_assign_group_min_spread=heur.three_line_assign_group_min_spread,
            three_line_assign_group_max_lhs_len=heur.three_line_assign_group_max_lhs_len,
            three_line_assign_group_min_qualified_count=heur.three_line_assign_group_min_qualified_count,
            three_line_assign_group_extra_pad=heur.three_line_assign_group_extra_pad,
        )
        if heur.align_chained_init_assignments:
            lines = align_chained_init_assignments(lines)
        if heur.align_ref_to_preceding_assign:
            lines = align_ref_to_preceding_assign(lines)
        if heur.align_init_injection_if_bodies:
            lines = align_init_injection_if_bodies(lines)
        if heur.align_pre_chained_true_orphans:
            lines = align_pre_chained_true_orphans(lines)
        if heur.compact_orphan_assign_min_gap > 0:
            lines = compact_orphan_overpadded_assigns(
                lines,
                min_gap=heur.compact_orphan_assign_min_gap,
                max_gap=heur.compact_orphan_assign_max_gap,
                simple_identifier_only=heur.compact_orphan_simple_identifier_only,
                expression_rhs_max_gap=heur.compact_orphan_expression_rhs_max_gap,
                expression_rhs_min_gap_floor=heur.compact_orphan_expression_rhs_min_gap_floor,
                skip_rhs_or_and_chain=heur.compact_orphan_skip_rhs_or_and_chain,
            )
        if heur.normalize_case_arm_single_assignments:
            lines = normalize_case_arm_single_assignments(lines)
        if heur.compact_same_col_outlier_enabled:
            lines = compact_same_col_outlier_assigns(
                lines,
                min_gap=heur.compact_same_col_outlier_min_gap,
                lhs_delta=heur.compact_same_col_outlier_lhs_delta,
            )

    if config.alignment.comments:
        lines = align_inline_comments(lines)

    if config.alignment.fb_call_params:
        lines = align_fb_call_params(lines)

    if config.align_multiline.array_initializers:
        lines = align_array_struct_inits(
            lines,
            field_indent_step=config.indent.size,
        )

    # Compact := padding on boolean chain lines before wrapping
    if heur.compact_bool_chain_assigns:
        lines = _compact_bool_chain_assigns(lines)

    # Join multiline FB calls back to single line when they fit (inverse of wrap_long_lines)
    if config.calls.join_single_line_when_fits and config.line_length.wrap_enabled:
        lines = _join_short_multiline_calls(lines, config.line_length.wrap_at,
                                            config.calls.max_params_single_line)

    if config.line_length.wrap_enabled:
        if config.line_breaks.before_then:
            lines = _pre_separate_overlength_then(lines, config.line_length.wrap_at)
        lines = wrap_long_lines(
            lines,
            max_length=config.line_length.wrap_at,
            max_params_single=config.calls.max_params_single_line,
            call_indent=config.calls.multiline_indent,
        )

    if config.line_breaks.before_then:
        lines = _separate_multiline_then(lines)

    # Post-wrap: re-normalize and re-align FB call params created by wrap
    if config.calls.normalize_param_indent:
        lines = _normalize_call_param_indent(lines, config.calls.multiline_indent)
    if config.alignment.fb_call_params:
        lines = align_fb_call_params(lines)

    if config.alignment.assignments:
        lines = _compact_post_wrap_orphans(lines)

    if heur.join_wrapped_assignments:
        lines = join_wrapped_assignments(lines, max_length=config.line_length.wrap_at)

    if heur.align_for_body_assignments and config.alignment.assignments:
        lines = align_for_body_assignments(
            lines,
            indent_size=config.indent.size,
            max_spread=config.alignment.max_assign_spread,
            bool_literal_min_group_lines=heur.bool_literal_min_group_lines,
            bool_literal_name_spread_max=heur.bool_literal_name_spread_max,
            assign_already_aligned_max_gap=heur.assign_already_aligned_max_gap,
            align_for_body_min_group_lines=heur.align_for_body_min_group_lines,
            align_for_body_long_rhs_len_threshold=heur.align_for_body_long_rhs_len_threshold,
            align_for_body_min_lhs_spread_for_alignment=heur.align_for_body_min_lhs_spread_for_alignment,
            compact_pair_assigns=heur.compact_pair_assigns,
            compact_pair_min_over_pad=heur.compact_pair_min_over_pad,
        )

    if (heur.blank_after_assign_before_comment
            or heur.blank_after_assign_before_for
            or heur.blank_after_assign_before_related_if
            or heur.blank_after_end_if_before_if):
        lines = _insert_blank_lines_after_assign(
            lines,
            before_comment=heur.blank_after_assign_before_comment,
            before_for=heur.blank_after_assign_before_for,
            before_related_if=heur.blank_after_assign_before_related_if,
            skip_related_if_when_rhs_contains_paren=heur.blank_after_assign_before_related_if_skip_if_rhs_contains_paren,
            after_end_if=heur.blank_after_end_if_before_if,
        )

    if not config.indent.indent_last_comment_before_else:
        lines = _normalize_control_anchor_comments(lines)

    if config.indent.fix_over_indented_end_if:
        lines = fix_end_if_indent_safe(
            lines,
            config.indent.size,
            rebuilt=_rebuilt_line_flags(baseline_lines, lines),
        )

    return "\n".join(lines)


def _rebuilt_line_flags(
    baseline_lines: list[str],
    lines: list[str],
) -> list[bool] | None:
    """Mark lines whose stripped content changed since the core format pass."""
    if len(baseline_lines) != len(lines):
        return None

    flags: list[bool] = []
    for base, current in zip(baseline_lines, lines):
        flags.append(base.strip() != current.strip())
    return flags


_RE_BOOL_CONTINUATION = re.compile(
    r"^\s+(AND_THEN|OR_ELSE|AND|OR|XOR)\s", re.IGNORECASE
)

_BOOL_OPS_END = ("AND_THEN", "OR_ELSE", "AND", "OR", "XOR")


def _code_before_line_comment(line: str) -> str:
    """Return ST code portion before an end-of-line ``//`` comment."""
    if "//" in line:
        return line.split("//", 1)[0].rstrip()
    return line.rstrip()


def _line_code_upper(line: str) -> str:
    return _code_before_line_comment(line).upper()


def _ends_with_bool_op(line: str) -> bool:
    code_upper = _line_code_upper(line)
    return any(code_upper.endswith(op) for op in _BOOL_OPS_END)


def _is_code_expression_context(prev: str) -> bool:
    """Check if previous line is code that allows bool continuation joining."""
    prev_stripped = _code_before_line_comment(prev)
    prev_upper = prev_stripped.upper()
    if prev_stripped.endswith(";"):
        return False
    if prev_upper.endswith("THEN") or prev_upper.endswith("DO"):
        return False
    if "(*" in prev and "*)" not in prev:
        return False
    if ":=" in prev:
        return True
    lhs = prev_upper.lstrip()
    if lhs.startswith(("IF ", "ELSIF ", "WHILE ", "UNTIL ")):
        return True
    for op in _BOOL_OPS_END:
        if prev_upper.endswith(op):
            return True
    return False


def _in_block_comment(lines: list[str], idx: int) -> bool:
    """Check if the line at idx is inside a block comment."""
    depth = 0
    for i in range(idx):
        line = lines[i]
        depth += line.count("(*") - line.count("*)")
    return depth > 0


_RE_LONE_THEN_DO = re.compile(r"^\s*(THEN|DO)\s*$", re.IGNORECASE)


def _join_lines_as_expression(lines: list[str]) -> str:
    """Join wrapped expression lines into one logical line."""
    joined = lines[0].rstrip()
    for part in lines[1:]:
        joined += " " + part.strip()
    return joined


def _emit_joined_or_chain_wrap(
    group: list[str],
    max_line: int,
    *,
    trailing: list[str] | None = None,
) -> list[str]:
    """Join *group* lines; collapse when short else chained-binary wrap."""
    trailing = trailing or []
    joined = _join_lines_as_expression(group)
    suffix = ""
    if trailing:
        suffix = " " + " ".join(part.strip() for part in trailing)

    if len(joined + suffix) <= max_line:
        return [joined + suffix]

    wrapped = wrap_chained_binary_expression(joined, max_line, force=True)
    if wrapped:
        return [*wrapped, *trailing]
    return [*group, *trailing]


def _join_bool_continuations(lines: list[str], max_line: int = 228) -> list[str]:
    """Join continuation lines starting with boolean operators into single logical lines.

    Strategy differs by context:
    - Assignment (:= present): ALWAYS join continuations (wrap_bool_chain re-wraps)
    - IF/WHILE conditions: ALL-OR-NOTHING — join all if full result fits max_line
    Appends lone THEN/DO to preceding condition (if result fits).
    """
    if not lines:
        return lines

    # Pass 1: handle assignment joins and lone THEN/DO
    pass1: list[str] = [lines[0]]
    joining = False
    comment_depth = lines[0].count("(*") - lines[0].count("*)")

    for line in lines[1:]:
        line_opens = line.count("(*")
        line_closes = line.count("*)")

        if joining:
            if comment_depth > 0:
                pass1.append(line)
                comment_depth += line_opens - line_closes
                joining = False
                continue
            stripped_upper = line.strip().upper()
            pass1[-1] = pass1[-1].rstrip() + " " + line.strip()
            comment_depth += line_opens - line_closes
            if (";" in line
                    or stripped_upper.endswith("THEN")
                    or stripped_upper.endswith("DO")
                    or stripped_upper.endswith(",")):
                joining = False
            continue

        if comment_depth > 0:
            pass1.append(line)
            comment_depth += line_opens - line_closes
            continue

        prev = pass1[-1].rstrip()
        is_assign_context = ":=" in prev

        # Lone THEN/DO: append only when prev is a short IF/WHILE without trailing comment
        if _RE_LONE_THEN_DO.match(line):
            prev_upper = prev.upper().lstrip()
            if (prev_upper.startswith(("IF ", "ELSIF ", "WHILE "))
                    and not prev.rstrip().endswith("*)")):
                candidate = prev + " " + line.strip()
                if len(candidate) <= max_line:
                    pass1[-1] = candidate
                    comment_depth += line_opens - line_closes
                    continue

        # Boolean continuation in assignment context (operator at START): always join
        if (_RE_BOOL_CONTINUATION.match(line)
                and _is_code_expression_context(prev)
                and is_assign_context
                and "//" not in prev):
            pass1[-1] = prev + " " + line.strip()
            comment_depth += line_opens - line_closes
            if ";" not in line and not line.rstrip().endswith(","):
                joining = True
        else:
            pass1.append(line)
            comment_depth += line_opens - line_closes

    # Pass 1.5: ALL-OR-NOTHING join for "operator at end" groups in assignments
    pass15: list[str] = []
    i = 0
    while i < len(pass1):
        line = pass1[i]
        is_assign = ":=" in _code_before_line_comment(line)
        ends_with_op = _ends_with_bool_op(line)

        if ends_with_op and is_assign:
            group = [line]
            j = i + 1
            while j < len(pass1):
                prev_u = _line_code_upper(pass1[j - 1])
                if any(prev_u.endswith(op) for op in _BOOL_OPS_END):
                    group.append(pass1[j])
                    if ";" in pass1[j] or pass1[j].rstrip().endswith(","):
                        j += 1
                        break
                    j += 1
                else:
                    break
            joined = group[0].rstrip()
            for g in group[1:]:
                joined += " " + g.strip()
            pass15.extend(_emit_joined_or_chain_wrap(group, max_line))
            i = j
        else:
            pass15.append(line)
            i += 1

    # Pass 2: ALL-OR-NOTHING join for IF/WHILE continuation groups
    result: list[str] = []
    i = 0
    while i < len(pass15):
        line = pass15[i]
        upper_stripped = line.strip().upper()

        # Detect start of IF/WHILE with continuations on next lines
        if (upper_stripped.startswith(("IF ", "ELSIF ", "WHILE "))
                and ":=" not in line
                and not upper_stripped.endswith("THEN")
                and not upper_stripped.endswith("DO")
                and i + 1 < len(pass15)
                and _RE_BOOL_CONTINUATION.match(pass15[i + 1])):
            # Collect the entire IF group
            group = [line]
            trailing: list[str] = []
            j = i + 1
            while j < len(pass15):
                if _RE_BOOL_CONTINUATION.match(pass15[j]):
                    group.append(pass15[j])
                    j += 1
                elif _RE_LONE_THEN_DO.match(pass15[j]):
                    trailing.append(pass15[j])
                    j += 1
                    break
                else:
                    break

            result.extend(_emit_joined_or_chain_wrap(group, max_line, trailing=trailing))
            i = j
        else:
            result.append(line)
            i += 1

    return result


_RE_BOOL_CHAIN_LINE = re.compile(
    r"^(\s*\S+)\s{2,}(:=\s.+)", re.DOTALL
)


def _has_top_level_bool_op(line: str) -> bool:
    """Check if line has AND_THEN/OR_ELSE at depth 0 in the RHS."""
    assign_pos = line.find(":=")
    if assign_pos < 0:
        return False
    rhs = line[assign_pos + 2:]
    depth = 0
    i = 0
    while i < len(rhs):
        if rhs[i] == "(":
            depth += 1
        elif rhs[i] == ")":
            depth -= 1
        elif depth == 0 and rhs[i:i+8].upper() == "AND_THEN":
            if (i == 0 or not rhs[i-1].isalnum()) and (i+8 >= len(rhs) or not rhs[i+8].isalnum()):
                return True
        elif depth == 0 and rhs[i:i+7].upper() == "OR_ELSE":
            if (i == 0 or not rhs[i-1].isalnum()) and (i+7 >= len(rhs) or not rhs[i+7].isalnum()):
                return True
        i += 1
    return False


_RE_COMMENT_ONLY = re.compile(r"^(\s*)(\(\*(?!\*).+?\*\))\s*$")
_RE_CONTROL_THEN = re.compile(r"^(\s*)(?:IF\b.*\bTHEN|CASE\b.*\bOF)\s*$", re.IGNORECASE)
_RE_BRANCH_KEYWORD = re.compile(r"^\s*(?:ELSIF\b|ELSE\b|END_IF\b|END_CASE\b)", re.IGNORECASE)


_RE_LINE_COMMENT_ONLY = re.compile(r"^(\s*)(//.*)\s*$")


def _normalize_control_anchor_comments(lines: list[str]) -> list[str]:
    """Keep standalone branch comments aligned with IF/CASE anchor, not body indent."""
    result: list[str] = []
    for i, line in enumerate(lines):
        cm = _RE_COMMENT_ONLY.match(line)
        lc = _RE_LINE_COMMENT_ONLY.match(line) if not cm else None
        if not cm and not lc:
            result.append(line)
            continue
        if cm and "(**)" in line:
            result.append(line)
            continue
        comment_text = cm.group(2) if cm else lc.group(2)
        prev_idx = i - 1
        while prev_idx >= 0 and not lines[prev_idx].strip():
            prev_idx -= 1
        next_idx = i + 1
        while next_idx < len(lines) and not lines[next_idx].strip():
            next_idx += 1
        if prev_idx < 0 or next_idx >= len(lines):
            result.append(line)
            continue
        prev = lines[prev_idx]
        nxt = lines[next_idx]
        ctrl = _RE_CONTROL_THEN.match(prev)
        if ctrl and _RE_BRANCH_KEYWORD.match(nxt):
            result.append(ctrl.group(1) + comment_text)
            continue

        nxt_stripped = nxt.lstrip()
        if nxt_stripped.upper().startswith(("ELSIF", "ELSE")):
            nxt_indent = len(nxt) - len(nxt_stripped)
            comment_indent = len(line) - len(line.lstrip())
            if comment_indent > nxt_indent:
                result.append(" " * nxt_indent + comment_text)
                continue

        result.append(line)
    return result


def _compact_bool_chain_assigns(lines: list[str]) -> list[str]:
    """Compact over-padded := on lines with top-level AND_THEN/OR_ELSE.

    Only affects lines where the bool op is at depth 0 (not inside parens).
    Normalizes multi-space padding before := to single space.
    Skips FB call param lines (comma-terminated).
    Preserves alignment when the neighbor has ':=' at the same column.
    """
    result: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped.endswith(","):
            result.append(line)
            continue
        if not _has_top_level_bool_op(line):
            result.append(line)
            continue
        m = _RE_BOOL_CHAIN_LINE.match(line)
        if m:
            pos = _find_assign_pos(line)
            if pos and _neighbor_has_same_assign_col(lines, i, pos):
                result.append(line)
            else:
                result.append(m.group(1) + " " + m.group(2))
        else:
            result.append(line)
    return result


def _compact_post_wrap_orphans(lines: list[str]) -> list[str]:
    """Compact over-padded assignments whose only `:=` neighbors are wrapped call openers.

    After wrapping, long assignments become multi-line (opener ending with ``(``).
    A short assignment at the same `:=` column has no true alignment peer and should
    be compacted to tight spacing — only when the padding gap is large (>=10).
    """
    result: list[str] = []
    for i, line in enumerate(lines):
        pos = _find_assign_pos(line)
        if pos is None or pos < 0:
            result.append(line)
            continue
        stripped = line.strip()
        if not stripped.endswith(";"):
            result.append(line)
            continue
        lhs = line[:pos].rstrip()
        gap = pos - len(lhs)
        if gap < 10:
            result.append(line)
            continue
        all_neighbors_are_openers = True
        has_any_neighbor = False
        for delta in (-1, 1):
            j = i + delta
            if 0 <= j < len(lines) and lines[j].strip():
                npos = _find_assign_pos(lines[j])
                if npos == pos:
                    has_any_neighbor = True
                    nstripped = lines[j].rstrip()
                    if not nstripped.endswith("("):
                        all_neighbors_are_openers = False
        if has_any_neighbor and all_neighbors_are_openers:
            rhs = line[pos:].lstrip()
            indent = " " * (len(line) - len(line.lstrip()))
            result.append(f"{indent}{lhs.strip()} {rhs}")
        else:
            result.append(line)
    return result


def _neighbor_has_same_assign_col(lines: list[str], idx: int, pos: int) -> bool:
    """Check if an adjacent non-bool-chain line also has ':=' at the same column."""
    for delta in (-1, 1):
        j = idx + delta
        if 0 <= j < len(lines) and lines[j].strip():
            if _has_top_level_bool_op(lines[j]):
                continue
            neighbor_pos = _find_assign_pos(lines[j])
            if neighbor_pos == pos:
                return True
    return False


def _span_matches_scope(span: CdataSpan, scope: FormatScope | None) -> bool:
    """Check if a CDATA span matches the given format scope filter."""
    if not scope or (
        scope.region == FormatRegion.ALL
        and not scope.member_name
        and scope.member_filter is None
    ):
        return True

    if scope.region == FormatRegion.DECLARATION:
        if not span.is_declaration:
            return False
    elif scope.region == FormatRegion.IMPLEMENTATION:
        if not span.is_implementation:
            return False

    if scope.member_name:
        if span.parent_name.casefold() != scope.member_name.casefold():
            return False

    if scope.member_filter == MemberFilter.ALL_METHODS:
        if span.kind not in (CdataKind.METHOD_DECLARATION, CdataKind.METHOD_IMPLEMENTATION):
            return False
    elif scope.member_filter == MemberFilter.ALL_ACTIONS:
        if span.kind not in (CdataKind.ACTION_DECLARATION, CdataKind.ACTION_IMPLEMENTATION):
            return False
    elif scope.member_filter == MemberFilter.ALL_PROPERTIES:
        if span.kind not in (
            CdataKind.PROPERTY_DECLARATION,
            CdataKind.PROPERTY_GET_DECLARATION,
            CdataKind.PROPERTY_GET_IMPLEMENTATION,
            CdataKind.PROPERTY_SET_DECLARATION,
            CdataKind.PROPERTY_SET_IMPLEMENTATION,
        ):
            return False

    return True


def _format_st_in_cdata_blocks(
    text: str, config: FormatterConfig, scope: FormatScope | None = None
) -> str:
    """Format ST code inside CDATA blocks without full XML reformat using twincat_core.xml surgical patching."""
    doc = read_tc_xml(text)

    def _replacer(span: CdataSpan) -> str | None:
        if not span.content.strip():
            return None
        if not _span_matches_scope(span, scope):
            return None
        formatted = _format_st_pipeline(span.content, config)
        return formatted.rstrip("\n") + "\n"

    patched, _ = patch_by_filter(doc, _replacer)
    return patched


def _accumulate_result(batch: BatchResult, result: FormatResult) -> None:
    """Add a single file result to batch totals."""
    batch.results.append(result)
    if result.validation_issues:
        batch.validation_issues.extend(result.validation_issues)
    if result.errors:
        batch.errors += 1
    elif result.changed:
        batch.formatted += 1
    else:
        batch.unchanged += 1


# ---------------------------------------------------------------------------
# Scope / Region Resolution
# ---------------------------------------------------------------------------

_MEMBER_TAGS = {"Method", "Action", "Property"}
_RE_CDATA_KEY = re.compile(r"__CDATA_(\d+)__")


def _resolve_scope_keys(
    formatted_xml: str, cdata_map: dict[str, str], scope: FormatScope | None
) -> set[str]:
    """Determine which CDATA keys should be formatted based on scope.

    Parses the formatted_xml to map CDATA placeholder keys to their
    structural position (Declaration/Implementation of POU vs Method etc.).
    Returns a set of keys that match the scope.
    """
    if not scope or (
        scope.region == FormatRegion.ALL
        and not scope.member_name
        and scope.member_filter is None
    ):
        return set(cdata_map.keys())

    return _match_keys_in_xml(formatted_xml, scope)


def _resolve_scope_keys_from_text(text: str, scope: FormatScope) -> set[str]:
    """Resolve scope from raw text (non-XML-formatted path)."""
    cdata_map: dict[str, str] = {}
    counter = [0]

    def _repl(m: re.Match[str]) -> str:
        key = f"__CDATA_{counter[0]}__"
        cdata_map[key] = m.group(1)
        counter[0] += 1
        return f"<![CDATA[{key}]]>"

    marked = _RE_CDATA_BLOCK.sub(lambda m: _repl(m), text)
    return _match_keys_in_xml(marked, scope)


def _match_keys_in_xml(xml_text: str, scope: FormatScope) -> set[str]:
    """Walk XML structure and return CDATA keys matching the scope."""
    import xml.etree.ElementTree as ET

    allowed: set[str] = set()

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return set()

    for container in _walk_containers(root):
        _collect_matching_keys(container, scope, allowed, is_top_level=True)

    return allowed


def _walk_containers(root: ET.Element):
    """Yield POU/DUT/GVL/Itf container elements."""
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if tag == "TcPlcObject":
        for child in root:
            yield child
    else:
        yield root


def _collect_matching_keys(
    element: ET.Element,
    scope: FormatScope,
    allowed: set[str],
    is_top_level: bool,
) -> None:
    """Recursively collect CDATA keys from elements matching the scope."""
    tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
    name = element.get("Name", "")

    is_member = tag in _MEMBER_TAGS

    if is_top_level and not is_member:
        # Top-level POU/DUT/GVL Declaration/Implementation
        if scope.member_name or scope.member_filter:
            # Specific member requested — do NOT format top-level blocks
            pass
        else:
            # No member filter — apply region filter to top-level
            if scope.region in (FormatRegion.ALL, FormatRegion.DECLARATION):
                _add_cdata_from_child(element, "Declaration", allowed)
            if scope.region in (FormatRegion.ALL, FormatRegion.IMPLEMENTATION):
                _add_cdata_from_child(element, "Implementation", allowed)

    if is_member:
        if _member_matches_scope(tag, name, scope):
            if scope.region in (FormatRegion.ALL, FormatRegion.DECLARATION):
                _add_cdata_from_child(element, "Declaration", allowed)
            if scope.region in (FormatRegion.ALL, FormatRegion.IMPLEMENTATION):
                _add_cdata_from_child(element, "Implementation", allowed)
                for st_el in element.iter():
                    el_tag = st_el.tag.split("}")[-1] if "}" in st_el.tag else st_el.tag
                    if el_tag == "ST":
                        _add_cdata_keys_from_element(st_el, allowed)

    # Recurse into children (Methods, Actions, Properties, Folders)
    for child in element:
        child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if child_tag in _MEMBER_TAGS:
            _collect_matching_keys(child, scope, allowed, is_top_level=False)
        elif child_tag == "Folder":
            for sub in child:
                _collect_matching_keys(sub, scope, allowed, is_top_level=False)


def _member_matches_scope(tag: str, name: str, scope: FormatScope) -> bool:
    """Check if a member element matches the scope filter."""
    if scope.member_name:
        return name.casefold() == scope.member_name.casefold()

    if scope.member_filter is None or scope.member_filter == MemberFilter.ALL:
        return True

    if scope.member_filter == MemberFilter.ALL_METHODS:
        return tag == "Method"
    if scope.member_filter == MemberFilter.ALL_ACTIONS:
        return tag == "Action"
    if scope.member_filter == MemberFilter.ALL_PROPERTIES:
        return tag == "Property"

    return True


def _add_cdata_from_child(parent: ET.Element, child_tag: str, allowed: set[str]) -> None:
    """Add CDATA keys found in a direct child element (Declaration/Implementation)."""
    for child in parent:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == child_tag:
            _add_cdata_keys_from_element(child, allowed)
            break


def _add_cdata_keys_from_element(element: ET.Element, allowed: set[str]) -> None:
    """Extract __CDATA_N__ keys from element text/tail."""
    for el in element.iter():
        if el.text:
            for m in _RE_CDATA_KEY.finditer(el.text):
                allowed.add(f"__CDATA_{m.group(1)}__")
        if el.tail:
            for m in _RE_CDATA_KEY.finditer(el.tail):
                allowed.add(f"__CDATA_{m.group(1)}__")


def _is_formattable(path: str, include: str | None, exclude: str | None) -> bool:
    """Check if file matches extension and include/exclude patterns."""
    ext = Path(path).suffix.lower()
    if ext not in FORMATTABLE_EXTENSIONS:
        return False
    name = Path(path).name
    if include and not fnmatch.fnmatch(name, include):
        return False
    if exclude and fnmatch.fnmatch(name, exclude):
        return False
    return True


# ---------------------------------------------------------------------------
# Syntax integrity check (lightweight token comparison)
# ---------------------------------------------------------------------------

_RE_CDATA_EXTRACT = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
_RE_BLOCK_COMMENT_TOK = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_RE_LINE_COMMENT_TOK = re.compile(r"//[^\n]*")
_RE_STRING_TOK = re.compile(r"'(?:''|\$.|[^'$\r\n])*'|\"(?:\"\"|\$.|[^\"$\r\n])*\"")
_RE_PRAGMA_TOK = re.compile(r"\{[^}\r\n]*\}")
_RE_IDENT_TOK = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_RE_NUMBER_TOK = re.compile(r"\b\d[\d_]*(?:\.[\d_]+)?(?:[eE][+-]?\d+)?\b|16#[0-9A-Fa-f_]+|2#[01_]+|8#[0-7_]+")
_RE_ASSIGN_TOK = re.compile(r":=|=>")
_RE_SEMI_TOK = re.compile(r";")


def _extract_tokens(cdata: str) -> dict[str, list[str]]:
    """Extract syntax-relevant tokens from ST code using twincat_core.syntax."""
    idents: list[str] = []
    numbers: list[str] = []
    assigns: list[str] = []
    semis: list[str] = []
    strings: list[str] = []
    pragmas: list[str] = []

    tokens, _ = tokenize_st(cdata, include_trivia=True)
    for tok in tokens:
        if (
            tok.type in (CoreTokenType.IDENTIFIER, CoreTokenType.BOOL_LITERAL)
            or tok.type.name.startswith("KEYWORD_")
        ):
            idents.append(tok.value.upper())
        elif tok.type in (
            CoreTokenType.INT_LITERAL,
            CoreTokenType.REAL_LITERAL,
            CoreTokenType.HEX_LITERAL,
            CoreTokenType.BIN_LITERAL,
            CoreTokenType.TYPED_LITERAL,
        ):
            numbers.append(tok.value)
        elif tok.type in (CoreTokenType.ASSIGN, CoreTokenType.OUTPUT_ASSIGN, CoreTokenType.REF_ASSIGN):
            assigns.append(tok.value)
        elif tok.type == CoreTokenType.SEMICOLON:
            semis.append(tok.value)
        elif tok.type in (CoreTokenType.STRING_LITERAL, CoreTokenType.WSTRING_LITERAL):
            strings.append(tok.value)
        elif tok.type == CoreTokenType.PRAGMA:
            pragmas.append(tok.value)

    return {
        "identifiers": sorted(idents),
        "numbers": sorted(n.upper() for n in numbers),
        "assigns": assigns,
        "semicolons": semis,
        "strings": sorted(strings),
        "pragmas": sorted(pragmas),
    }


def check_syntax_integrity(original_text: str, formatted_text: str) -> list[str]:
    """Compare syntax tokens before/after formatting.

    Returns empty list if no semantic changes detected.
    Costs <1ms per file - negligible performance impact.

    When XML sorting reorders CDATA blocks (methods/actions), we compare
    tokens as a combined set across ALL blocks rather than per-index.
    """
    orig_cdatas = [s.content for s in read_tc_xml(original_text).cdata_spans]
    fmt_cdatas = [s.content for s in read_tc_xml(formatted_text).cdata_spans]

    errors: list[str] = []

    if len(orig_cdatas) != len(fmt_cdatas):
        errors.append(f"CDATA block count changed: {len(orig_cdatas)} -> {len(fmt_cdatas)}")
        return errors

    # First: try per-index comparison (fast path, no sorting)
    per_index_ok = True
    for idx, (orig, fmt) in enumerate(zip(orig_cdatas, fmt_cdatas)):
        if not orig.strip():
            continue
        orig_tok = _extract_tokens(orig)
        fmt_tok = _extract_tokens(fmt)
        if orig_tok != fmt_tok:
            per_index_ok = False
            break

    if per_index_ok:
        return []

    # Fallback: XML sorting may have reordered blocks. Compare as combined set.
    orig_combined: dict[str, list[str]] = {
        "identifiers": [], "numbers": [], "assigns": [],
        "semicolons": [], "strings": [], "pragmas": [],
    }
    fmt_combined: dict[str, list[str]] = {
        "identifiers": [], "numbers": [], "assigns": [],
        "semicolons": [], "strings": [], "pragmas": [],
    }

    for orig in orig_cdatas:
        if orig.strip():
            tok = _extract_tokens(orig)
            for cat in orig_combined:
                orig_combined[cat].extend(tok[cat])

    for fmt in fmt_cdatas:
        if fmt.strip():
            tok = _extract_tokens(fmt)
            for cat in fmt_combined:
                fmt_combined[cat].extend(tok[cat])

    for cat in orig_combined:
        orig_sorted = sorted(orig_combined[cat])
        fmt_sorted = sorted(fmt_combined[cat])
        if orig_sorted != fmt_sorted:
            o_set = set(orig_sorted)
            f_set = set(fmt_sorted)
            added = f_set - o_set
            removed = o_set - f_set
            if added or removed:
                msg = f"Combined {cat}: "
                if added:
                    msg += f"+{list(added)[:5]} "
                if removed:
                    msg += f"-{list(removed)[:5]}"
                errors.append(msg)
            else:
                # Same set but different counts
                from collections import Counter
                orig_c = Counter(orig_sorted)
                fmt_c = Counter(fmt_sorted)
                diff = orig_c - fmt_c
                extra = fmt_c - orig_c
                if diff or extra:
                    msg = f"Combined {cat} count mismatch: "
                    if extra:
                        msg += f"+{dict(list(extra.items())[:3])} "
                    if diff:
                        msg += f"-{dict(list(diff.items())[:3])}"
                    errors.append(msg)

    return errors
