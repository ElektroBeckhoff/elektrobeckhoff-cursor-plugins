"""Configuration system for the TwinCAT3 ST Formatter.

Loads from defaults.json, merges with user overrides from .stformat.json.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_DEFAULTS_PATH = Path(__file__).parent / "defaults.json"


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class IndentConfig:
    size: int = 4
    style: str = "spaces"  # "spaces" or "tabs"
    indent_cases_in_case: bool = True
    indent_statements_in_case: bool = True
    indent_else_case: bool = False
    indent_derived_types: bool = True
    indent_do_in_for: bool = False
    indent_then_in_if: bool = False
    indent_last_comment_before_case: bool = False
    indent_last_comment_before_else: bool = False
    continuous_indent_multiplier: int = 1
    reindent: bool = True
    fix_over_indented_end_if: bool = True


@dataclass(slots=True)
class LineLengthConfig:
    wrap_at: int = 230
    wrap_enabled: bool = True
    wrap_after_operator: bool = True


@dataclass(slots=True)
class BlankLinesConfig:
    after_multiline_case: int = 0
    after_multiline_comment: int = 0
    after_multiline_declaration: int = 0
    after_multiline_statement: int = 0
    after_singleline_case: int = 0
    after_singleline_comment: int = 0
    after_singleline_declaration: int = 0
    after_singleline_statement: int = 0
    after_statement_with_body: int = 1
    after_var_blocks: int = 0
    at_implementation_end: int = 1
    at_implementation_start: int = 0
    before_multiline_comment: int = 0
    before_multiline_declaration: int = 0
    before_multiline_statement: int = 0
    before_singleline_comment: int = 0
    before_singleline_declaration: int = 0
    before_singleline_statement: int = 0
    before_statement_with_body: int = 1
    max_consecutive: int = 1


@dataclass(slots=True)
class SpacesConfig:
    after_comma: bool = True
    after_declaration_colon: bool = True
    before_declaration_colon: bool = True
    around_additive_operator: bool = True
    around_assignment_operator: bool = True
    around_assignment_in_call: bool = True
    around_assignment_in_init: bool = True
    around_comment: bool = True
    around_comparison_operator: bool = True
    around_dot: bool = False
    around_equality_operator: bool = True
    around_term_operator: bool = True
    before_array_brackets: bool = False
    before_array_init_brackets: bool = False
    before_comma: bool = False
    before_fb_init_parens: bool = False
    before_invocation_parens: bool = False
    before_semicolon: bool = False
    before_struct_init_parens: bool = False
    before_subrange_parens: bool = False
    between_nested_parens: bool = False
    inside_array_brackets: bool = False
    inside_array_init_brackets: bool = False
    inside_expression_parens: bool = False
    inside_fb_init_parens: bool = False
    inside_invocation_parens: bool = False
    inside_struct_init_parens: bool = False
    inside_subrange_parens: bool = False
    around_pragma: bool = True
    normalize_inline: bool = False  # collapse multi-spaces between tokens


@dataclass(slots=True)
class AlignmentConfig:
    declarations: bool = True
    assignments: bool = True
    fb_call_params: bool = True
    comments: bool = True
    # Align ``name AT %I/%Q`` direct-variable declarations.
    address_assignments: bool = True
    enum_initializers: bool = True
    align_init_operator: bool = True  # Pad type to align ':=' across init group
    max_init_type_spread: int = 999  # Skip ':=' alignment when type length spread exceeds this
    max_assign_spread: int = 999  # Skip group alignment if max-min name length exceeds this
    join_continuations: bool = True  # Join bool chains; re-wrap one-per-line when over limit
    split_overlength_decls: bool = True  # Isolate outlier declarations with blank lines when alignment would exceed line limit


@dataclass(slots=True)
class AlignmentHeuristicsConfig:
    """Advanced alignment heuristics."""

    join_wrapped_assignments: bool = True
    # Generic guard: avoid aligning groups of pure bool literals with tight name spreads.
    bool_literal_min_group_lines: int = 3
    bool_literal_name_spread_max: int = 2
    # Skip re-align when existing padding before ':=' is already tight.
    assign_already_aligned_max_gap: int = 1
    compact_orphan_assign_min_gap: int = 3
    compact_orphan_assign_max_gap: int = 13
    compact_orphan_simple_identifier_only: bool = True
    compact_orphan_expression_rhs_max_gap: int = 13
    # When RHS is not a bare identifier, don't compact unless the padding gap
    # stays within a safe window. The lower bound was previously hard-coded.
    compact_orphan_expression_rhs_min_gap_floor: int = 10
    # Preserve spacing on OR/AND RHS chains (prevents breaking Golden parity noise).
    compact_orphan_skip_rhs_or_and_chain: bool = True
    compact_pair_assigns: bool = True
    compact_pair_min_over_pad: int = 8
    compact_group_min_lines: int = 4
    compact_group_max_over_pad: int = 3
    compact_three_line_count: int = 3
    compact_three_line_over_pad: int = 2
    compact_bool_chain_assigns: bool = True
    compact_same_col_outlier_enabled: bool = False
    compact_same_col_outlier_min_gap: int = 8
    compact_same_col_outlier_lhs_delta: int = 2
    # Declaration comment gap: shorter sibling keeps tight (* *) when source had one space.
    decl_comment_preserve_tight_gap: bool = True
    decl_comment_preserve_source_gap: int = 1
    decl_comment_preserve_max_col_delta: int = 1
    decl_split_outlier_median_multiplier: float = 1.5
    decl_split_outlier_median_add: int = 20
    # CASE label/body split — not wired to lineBreaks.before_statements_in_case alone (enum regressions).
    split_case_inline_statements: bool = True
    split_case_numeric_labels_only: bool = True
    split_case_keep_else_inline_comment: bool = True
    blank_after_assign_before_comment: bool = True
    blank_after_assign_before_for: bool = True
    blank_after_assign_before_related_if: bool = True
    # Skip blank insertion when "related IF" has RHS parentheses (prevents reflow).
    blank_after_assign_before_related_if_skip_if_rhs_contains_paren: bool = True
    blank_after_end_if_before_if: bool = True
    align_for_body_assignments: bool = True
    align_for_body_min_group_lines: int = 3
    # Guards previously hard-coded inside align_for_body_assignments/_should_loose_align_for_group.
    align_for_body_long_rhs_len_threshold: int = 30
    align_for_body_min_lhs_spread_for_alignment: int = 3
    expand_tight_assignment_spacing: bool = True
    # Three-line qualified assign group: max(lhs)+extra_pad when member-access lines share common struct base.
    three_line_assign_group_count: int = 3
    three_line_assign_group_min_spread: int = 12
    three_line_assign_group_max_lhs_len: int = 36
    three_line_assign_group_min_qualified_count: int = 2
    three_line_assign_group_extra_pad: int = 2
    # Init-method alignment passes (after align_assignments).
    align_chained_init_assignments: bool = True
    align_ref_to_preceding_assign: bool = True
    align_init_injection_if_bodies: bool = True
    align_pre_chained_true_orphans: bool = True


@dataclass(slots=True)
class AlignMultilineConfig:
    array_initializers: bool = True
    chained_binary: bool = True
    fb_init_assignments: bool = True
    fb_init_params: bool = True
    invocation_params: bool = True
    invocation_assignments: bool = True
    struct_init_assignments: bool = True
    struct_init_params: bool = True


@dataclass(slots=True)
class LineBreaksConfig:
    keep_existing: bool = False
    after_if: bool = False
    before_then: bool = True
    before_do_in_for: bool = False
    before_statements_in_case: bool = True
    after_pragma: str = "keep_existing"  # "keep_existing" or int (0=no forced break, 1=one blank)
    after_type_keyword: bool = False
    place_struct_on_new_line: bool = True
    place_simple_if_single_line: bool = False
    wrap_before_comma: bool = False
    after_left_paren_invocation: bool = True
    after_left_paren_struct_init: bool = True
    after_left_paren_fb_init: bool = False
    after_left_paren_enum: bool = False
    after_left_bracket_array: bool = False
    before_left_paren_invocation: bool = False
    before_left_paren_struct_init: bool = False
    before_left_paren_fb_init: bool = False
    before_left_paren_enum: bool = False
    before_left_bracket_array: bool = False
    before_right_paren_invocation: bool = False
    before_right_paren_struct_init: bool = False
    before_right_paren_fb_init: bool = False
    before_right_paren_enum: bool = False
    before_right_bracket_array: bool = False


@dataclass(slots=True)
class CallsConfig:
    max_params_single_line: int = 4
    max_struct_init_single_line: int = 3
    max_fb_init_single_line: int = 3
    max_array_init_single_line: int = 30
    # Split comma-separated enum members when count exceeds this.
    max_enum_single_line: int = 5
    multiline_indent: int = 8
    normalize_param_indent: bool = True  # Normalize already-multiline FB call param indentation
    join_single_line_when_fits: bool = True  # Inverse of wrap: join multiline invocations when <= wrap_at and <= max_params


@dataclass(slots=True)
class ParenthesesConfig:
    array_init_style: int = 2
    fb_init_style: int = 2
    function_call_style: int = 2
    enum_style: int = 2
    struct_init_style: int = 2


@dataclass(slots=True)
class KeywordsConfig:
    uppercase: bool = True


@dataclass(slots=True)
class XmlConfig:
    indent_size: int = 2
    sort_methods: bool = True
    sort_actions: bool = True
    sort_properties: bool = True


@dataclass(slots=True)
class ValidationConfig:
    check_name_match: bool = True
    check_guids: bool = True
    check_structure: bool = True


@dataclass(slots=True)
class SafetyConfig:
    backup: bool = True
    delete_backup_on_success: bool = True
    syntax_check: bool = True


@dataclass(slots=True)
class FormatterConfig:
    indent: IndentConfig = field(default_factory=IndentConfig)
    line_length: LineLengthConfig = field(default_factory=LineLengthConfig)
    blank_lines: BlankLinesConfig = field(default_factory=BlankLinesConfig)
    spaces: SpacesConfig = field(default_factory=SpacesConfig)
    alignment: AlignmentConfig = field(default_factory=AlignmentConfig)
    alignment_heuristics: AlignmentHeuristicsConfig = field(
        default_factory=AlignmentHeuristicsConfig,
    )
    align_multiline: AlignMultilineConfig = field(default_factory=AlignMultilineConfig)
    line_breaks: LineBreaksConfig = field(default_factory=LineBreaksConfig)
    calls: CallsConfig = field(default_factory=CallsConfig)
    parentheses: ParenthesesConfig = field(default_factory=ParenthesesConfig)
    keywords: KeywordsConfig = field(default_factory=KeywordsConfig)
    xml: XmlConfig = field(default_factory=XmlConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    line_ending: str = "auto"
    # Descriptions from defaults.json ``$meta`` (dot-path keys); not formatter settings.
    meta: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Loading & Merging
# ---------------------------------------------------------------------------


def load_config(
    config_path: str | Path | None = None,
    project_root: str | Path | None = None,
) -> FormatterConfig:
    """Load formatter configuration.

    Priority (highest wins):
    1. Explicit config_path (CLI --config)
    2. .stformat.json in project_root
    3. Built-in defaults.json
    """
    defaults = _load_json(_DEFAULTS_PATH)

    overrides: dict[str, Any] = {}
    if config_path:
        overrides = _load_json(Path(config_path))
    elif project_root:
        user_config = Path(project_root) / ".stformat.json"
        if user_config.exists():
            overrides = _load_json(user_config)

    merged = _deep_merge(defaults, overrides)
    meta = _extract_meta(defaults, overrides)
    return _dict_to_config(merged, meta=meta)


def config_to_dict(cfg: FormatterConfig) -> dict[str, Any]:
    """Serialize config back to dict (for display / MCP response)."""
    return {
        "$meta": dict(cfg.meta),
        "indent": {
            "size": cfg.indent.size,
            "style": cfg.indent.style,
            "indent_cases_in_case": cfg.indent.indent_cases_in_case,
            "indent_statements_in_case": cfg.indent.indent_statements_in_case,
            "indent_else_case": cfg.indent.indent_else_case,
            "indent_derived_types": cfg.indent.indent_derived_types,
            "indent_do_in_for": cfg.indent.indent_do_in_for,
            "indent_then_in_if": cfg.indent.indent_then_in_if,
            "indent_last_comment_before_case": cfg.indent.indent_last_comment_before_case,
            "indent_last_comment_before_else": cfg.indent.indent_last_comment_before_else,
            "continuous_indent_multiplier": cfg.indent.continuous_indent_multiplier,
            "reindent": cfg.indent.reindent,
            "fix_over_indented_end_if": cfg.indent.fix_over_indented_end_if,
        },
        "lineLength": {
            "wrap_at": cfg.line_length.wrap_at,
            "wrap_enabled": cfg.line_length.wrap_enabled,
            "wrap_after_operator": cfg.line_length.wrap_after_operator,
        },
        "blankLines": {
            "after_multiline_case": cfg.blank_lines.after_multiline_case,
            "after_multiline_comment": cfg.blank_lines.after_multiline_comment,
            "after_multiline_declaration": cfg.blank_lines.after_multiline_declaration,
            "after_multiline_statement": cfg.blank_lines.after_multiline_statement,
            "after_singleline_case": cfg.blank_lines.after_singleline_case,
            "after_singleline_comment": cfg.blank_lines.after_singleline_comment,
            "after_singleline_declaration": cfg.blank_lines.after_singleline_declaration,
            "after_singleline_statement": cfg.blank_lines.after_singleline_statement,
            "after_statement_with_body": cfg.blank_lines.after_statement_with_body,
            "after_var_blocks": cfg.blank_lines.after_var_blocks,
            "at_implementation_end": cfg.blank_lines.at_implementation_end,
            "at_implementation_start": cfg.blank_lines.at_implementation_start,
            "before_multiline_comment": cfg.blank_lines.before_multiline_comment,
            "before_multiline_declaration": cfg.blank_lines.before_multiline_declaration,
            "before_multiline_statement": cfg.blank_lines.before_multiline_statement,
            "before_singleline_comment": cfg.blank_lines.before_singleline_comment,
            "before_singleline_declaration": cfg.blank_lines.before_singleline_declaration,
            "before_singleline_statement": cfg.blank_lines.before_singleline_statement,
            "before_statement_with_body": cfg.blank_lines.before_statement_with_body,
            "max_consecutive": cfg.blank_lines.max_consecutive,
        },
        "spaces": {
            "after_comma": cfg.spaces.after_comma,
            "after_declaration_colon": cfg.spaces.after_declaration_colon,
            "before_declaration_colon": cfg.spaces.before_declaration_colon,
            "around_additive_operator": cfg.spaces.around_additive_operator,
            "around_assignment_operator": cfg.spaces.around_assignment_operator,
            "around_assignment_in_call": cfg.spaces.around_assignment_in_call,
            "around_assignment_in_init": cfg.spaces.around_assignment_in_init,
            "around_comment": cfg.spaces.around_comment,
            "around_comparison_operator": cfg.spaces.around_comparison_operator,
            "around_dot": cfg.spaces.around_dot,
            "around_equality_operator": cfg.spaces.around_equality_operator,
            "around_term_operator": cfg.spaces.around_term_operator,
            "before_array_brackets": cfg.spaces.before_array_brackets,
            "before_array_init_brackets": cfg.spaces.before_array_init_brackets,
            "before_comma": cfg.spaces.before_comma,
            "before_fb_init_parens": cfg.spaces.before_fb_init_parens,
            "before_invocation_parens": cfg.spaces.before_invocation_parens,
            "before_semicolon": cfg.spaces.before_semicolon,
            "before_struct_init_parens": cfg.spaces.before_struct_init_parens,
            "before_subrange_parens": cfg.spaces.before_subrange_parens,
            "between_nested_parens": cfg.spaces.between_nested_parens,
            "inside_array_brackets": cfg.spaces.inside_array_brackets,
            "inside_array_init_brackets": cfg.spaces.inside_array_init_brackets,
            "inside_expression_parens": cfg.spaces.inside_expression_parens,
            "inside_fb_init_parens": cfg.spaces.inside_fb_init_parens,
            "inside_invocation_parens": cfg.spaces.inside_invocation_parens,
            "inside_struct_init_parens": cfg.spaces.inside_struct_init_parens,
            "inside_subrange_parens": cfg.spaces.inside_subrange_parens,
            "around_pragma": cfg.spaces.around_pragma,
            "normalize_inline": cfg.spaces.normalize_inline,
        },
        "alignment": {
            "declarations": cfg.alignment.declarations,
            "assignments": cfg.alignment.assignments,
            "fb_call_params": cfg.alignment.fb_call_params,
            "comments": cfg.alignment.comments,
            "address_assignments": cfg.alignment.address_assignments,
            "enum_initializers": cfg.alignment.enum_initializers,
            "align_init_operator": cfg.alignment.align_init_operator,
            "max_init_type_spread": cfg.alignment.max_init_type_spread,
            "max_assign_spread": cfg.alignment.max_assign_spread,
            "join_continuations": cfg.alignment.join_continuations,
            "split_overlength_decls": cfg.alignment.split_overlength_decls,
        },
        "alignmentHeuristics": {
            "join_wrapped_assignments": cfg.alignment_heuristics.join_wrapped_assignments,
            "bool_literal_min_group_lines": cfg.alignment_heuristics.bool_literal_min_group_lines,
            "bool_literal_name_spread_max": cfg.alignment_heuristics.bool_literal_name_spread_max,
            "assign_already_aligned_max_gap": cfg.alignment_heuristics.assign_already_aligned_max_gap,
            "compact_orphan_assign_min_gap": cfg.alignment_heuristics.compact_orphan_assign_min_gap,
            "compact_orphan_assign_max_gap": cfg.alignment_heuristics.compact_orphan_assign_max_gap,
            "compact_orphan_simple_identifier_only": (
                cfg.alignment_heuristics.compact_orphan_simple_identifier_only
            ),
            "compact_orphan_expression_rhs_max_gap": (
                cfg.alignment_heuristics.compact_orphan_expression_rhs_max_gap
            ),
            "compact_orphan_expression_rhs_min_gap_floor": (
                cfg.alignment_heuristics.compact_orphan_expression_rhs_min_gap_floor
            ),
            "compact_orphan_skip_rhs_or_and_chain": (
                cfg.alignment_heuristics.compact_orphan_skip_rhs_or_and_chain
            ),
            "compact_pair_assigns": cfg.alignment_heuristics.compact_pair_assigns,
            "compact_pair_min_over_pad": cfg.alignment_heuristics.compact_pair_min_over_pad,
            "compact_group_min_lines": cfg.alignment_heuristics.compact_group_min_lines,
            "compact_group_max_over_pad": cfg.alignment_heuristics.compact_group_max_over_pad,
            "compact_three_line_count": cfg.alignment_heuristics.compact_three_line_count,
            "compact_three_line_over_pad": cfg.alignment_heuristics.compact_three_line_over_pad,
            "compact_bool_chain_assigns": cfg.alignment_heuristics.compact_bool_chain_assigns,
            "compact_same_col_outlier_enabled": (
                cfg.alignment_heuristics.compact_same_col_outlier_enabled
            ),
            "compact_same_col_outlier_min_gap": (
                cfg.alignment_heuristics.compact_same_col_outlier_min_gap
            ),
            "compact_same_col_outlier_lhs_delta": (
                cfg.alignment_heuristics.compact_same_col_outlier_lhs_delta
            ),
            "decl_comment_preserve_tight_gap": (
                cfg.alignment_heuristics.decl_comment_preserve_tight_gap
            ),
            "decl_comment_preserve_source_gap": (
                cfg.alignment_heuristics.decl_comment_preserve_source_gap
            ),
            "decl_comment_preserve_max_col_delta": (
                cfg.alignment_heuristics.decl_comment_preserve_max_col_delta
            ),
            "decl_split_outlier_median_multiplier": (
                cfg.alignment_heuristics.decl_split_outlier_median_multiplier
            ),
            "decl_split_outlier_median_add": (
                cfg.alignment_heuristics.decl_split_outlier_median_add
            ),
            "split_case_inline_statements": (
                cfg.alignment_heuristics.split_case_inline_statements
            ),
            "split_case_numeric_labels_only": (
                cfg.alignment_heuristics.split_case_numeric_labels_only
            ),
            "split_case_keep_else_inline_comment": (
                cfg.alignment_heuristics.split_case_keep_else_inline_comment
            ),
            "blank_after_assign_before_comment": (
                cfg.alignment_heuristics.blank_after_assign_before_comment
            ),
            "blank_after_assign_before_for": (
                cfg.alignment_heuristics.blank_after_assign_before_for
            ),
            "blank_after_assign_before_related_if": (
                cfg.alignment_heuristics.blank_after_assign_before_related_if
            ),
            "blank_after_assign_before_related_if_skip_if_rhs_contains_paren": (
                cfg.alignment_heuristics.blank_after_assign_before_related_if_skip_if_rhs_contains_paren
            ),
            "blank_after_end_if_before_if": (
                cfg.alignment_heuristics.blank_after_end_if_before_if
            ),
            "align_for_body_assignments": (
                cfg.alignment_heuristics.align_for_body_assignments
            ),
            "align_for_body_min_group_lines": (
                cfg.alignment_heuristics.align_for_body_min_group_lines
            ),
            "align_for_body_long_rhs_len_threshold": (
                cfg.alignment_heuristics.align_for_body_long_rhs_len_threshold
            ),
            "align_for_body_min_lhs_spread_for_alignment": (
                cfg.alignment_heuristics.align_for_body_min_lhs_spread_for_alignment
            ),
            "expand_tight_assignment_spacing": (
                cfg.alignment_heuristics.expand_tight_assignment_spacing
            ),
            "three_line_assign_group_count": (
                cfg.alignment_heuristics.three_line_assign_group_count
            ),
            "three_line_assign_group_min_spread": (
                cfg.alignment_heuristics.three_line_assign_group_min_spread
            ),
            "three_line_assign_group_max_lhs_len": (
                cfg.alignment_heuristics.three_line_assign_group_max_lhs_len
            ),
            "three_line_assign_group_min_qualified_count": (
                cfg.alignment_heuristics.three_line_assign_group_min_qualified_count
            ),
            "three_line_assign_group_extra_pad": (
                cfg.alignment_heuristics.three_line_assign_group_extra_pad
            ),
            "align_chained_init_assignments": (
                cfg.alignment_heuristics.align_chained_init_assignments
            ),
            "align_ref_to_preceding_assign": (
                cfg.alignment_heuristics.align_ref_to_preceding_assign
            ),
            "align_init_injection_if_bodies": (
                cfg.alignment_heuristics.align_init_injection_if_bodies
            ),
            "align_pre_chained_true_orphans": (
                cfg.alignment_heuristics.align_pre_chained_true_orphans
            ),
        },
        "alignMultiline": {
            "array_initializers": cfg.align_multiline.array_initializers,
            "chained_binary": cfg.align_multiline.chained_binary,
            "fb_init_assignments": cfg.align_multiline.fb_init_assignments,
            "fb_init_params": cfg.align_multiline.fb_init_params,
            "invocation_params": cfg.align_multiline.invocation_params,
            "invocation_assignments": cfg.align_multiline.invocation_assignments,
            "struct_init_assignments": cfg.align_multiline.struct_init_assignments,
            "struct_init_params": cfg.align_multiline.struct_init_params,
        },
        "lineBreaks": {
            "keep_existing": cfg.line_breaks.keep_existing,
            "after_if": cfg.line_breaks.after_if,
            "before_then": cfg.line_breaks.before_then,
            "before_do_in_for": cfg.line_breaks.before_do_in_for,
            "before_statements_in_case": cfg.line_breaks.before_statements_in_case,
            "after_pragma": cfg.line_breaks.after_pragma,
            "after_type_keyword": cfg.line_breaks.after_type_keyword,
            "place_struct_on_new_line": cfg.line_breaks.place_struct_on_new_line,
            "place_simple_if_single_line": cfg.line_breaks.place_simple_if_single_line,
            "wrap_before_comma": cfg.line_breaks.wrap_before_comma,
            "after_left_paren_invocation": cfg.line_breaks.after_left_paren_invocation,
            "after_left_paren_struct_init": cfg.line_breaks.after_left_paren_struct_init,
            "after_left_paren_fb_init": cfg.line_breaks.after_left_paren_fb_init,
            "after_left_paren_enum": cfg.line_breaks.after_left_paren_enum,
            "after_left_bracket_array": cfg.line_breaks.after_left_bracket_array,
            "before_left_paren_invocation": cfg.line_breaks.before_left_paren_invocation,
            "before_left_paren_struct_init": cfg.line_breaks.before_left_paren_struct_init,
            "before_left_paren_fb_init": cfg.line_breaks.before_left_paren_fb_init,
            "before_left_paren_enum": cfg.line_breaks.before_left_paren_enum,
            "before_left_bracket_array": cfg.line_breaks.before_left_bracket_array,
            "before_right_paren_invocation": cfg.line_breaks.before_right_paren_invocation,
            "before_right_paren_struct_init": cfg.line_breaks.before_right_paren_struct_init,
            "before_right_paren_fb_init": cfg.line_breaks.before_right_paren_fb_init,
            "before_right_paren_enum": cfg.line_breaks.before_right_paren_enum,
            "before_right_bracket_array": cfg.line_breaks.before_right_bracket_array,
        },
        "calls": {
            "max_params_single_line": cfg.calls.max_params_single_line,
            "max_struct_init_single_line": cfg.calls.max_struct_init_single_line,
            "max_fb_init_single_line": cfg.calls.max_fb_init_single_line,
            "max_array_init_single_line": cfg.calls.max_array_init_single_line,
            "max_enum_single_line": cfg.calls.max_enum_single_line,
            "multiline_indent": cfg.calls.multiline_indent,
            "normalize_param_indent": cfg.calls.normalize_param_indent,
            "join_single_line_when_fits": cfg.calls.join_single_line_when_fits,
        },
        "parentheses": {
            "array_init_style": cfg.parentheses.array_init_style,
            "fb_init_style": cfg.parentheses.fb_init_style,
            "function_call_style": cfg.parentheses.function_call_style,
            "enum_style": cfg.parentheses.enum_style,
            "struct_init_style": cfg.parentheses.struct_init_style,
        },
        "keywords": {"uppercase": cfg.keywords.uppercase},
        "xml": {
            "indent_size": cfg.xml.indent_size,
            "sort_methods": cfg.xml.sort_methods,
            "sort_actions": cfg.xml.sort_actions,
            "sort_properties": cfg.xml.sort_properties,
        },
        "validation": {
            "check_name_match": cfg.validation.check_name_match,
            "check_guids": cfg.validation.check_guids,
            "check_structure": cfg.validation.check_structure,
        },
        "safety": {
            "backup": cfg.safety.backup,
            "delete_backup_on_success": cfg.safety.delete_backup_on_success,
            "syntax_check": cfg.safety.syntax_check,
        },
        "lineEnding": cfg.line_ending,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON file, return empty dict on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge override into base (override wins). Skips ``$meta`` (handled separately)."""
    result = _strip_documentation_keys(base)
    for key, value in _strip_documentation_keys(override).items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _extract_meta(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, str]:
    """Merge ``$meta`` documentation blocks (defaults ← overrides)."""
    base = defaults.get("$meta", {})
    over = overrides.get("$meta", {})
    if not isinstance(base, dict):
        base = {}
    if not isinstance(over, dict):
        over = {}
    merged: dict[str, str] = {}
    for key, value in {**base, **over}.items():
        if isinstance(key, str) and isinstance(value, str):
            merged[key] = value
    return merged


def _strip_documentation_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Remove ``$meta`` and underscore-prefixed pseudo-comment keys from a config dict."""
    return {
        key: value
        for key, value in data.items()
        if key != "$meta" and not (isinstance(key, str) and key.startswith("_"))
    }


def _dict_to_config(d: dict[str, Any], *, meta: dict[str, str] | None = None) -> FormatterConfig:
    """Convert merged dict to typed FormatterConfig."""
    resolved_meta = meta if meta is not None else _extract_meta(d, {})
    return FormatterConfig(
        indent=_build_dataclass(IndentConfig, d.get("indent", {})),
        line_length=_build_dataclass(LineLengthConfig, d.get("lineLength", {})),
        blank_lines=_build_dataclass(BlankLinesConfig, d.get("blankLines", {})),
        spaces=_build_dataclass(SpacesConfig, d.get("spaces", {})),
        alignment=_build_dataclass(AlignmentConfig, d.get("alignment", {})),
        alignment_heuristics=_build_dataclass(
            AlignmentHeuristicsConfig, d.get("alignmentHeuristics", {}),
        ),
        align_multiline=_build_dataclass(AlignMultilineConfig, d.get("alignMultiline", {})),
        line_breaks=_build_dataclass(LineBreaksConfig, d.get("lineBreaks", {})),
        calls=_build_dataclass(CallsConfig, d.get("calls", {})),
        parentheses=_build_dataclass(ParenthesesConfig, d.get("parentheses", {})),
        keywords=_build_dataclass(KeywordsConfig, d.get("keywords", {})),
        xml=_build_dataclass(XmlConfig, d.get("xml", {})),
        validation=_build_dataclass(ValidationConfig, d.get("validation", {})),
        safety=_build_dataclass(SafetyConfig, d.get("safety", {})),
        line_ending=d.get("lineEnding", "auto"),
        meta=resolved_meta,
    )


def _build_dataclass(cls: type, data: dict[str, Any]) -> Any:
    """Build dataclass from dict, ignoring unknown and documentation keys."""
    import dataclasses

    valid_fields = {f.name for f in dataclasses.fields(cls)}
    filtered = {
        k: v
        for k, v in _strip_documentation_keys(data).items()
        if k in valid_fields
    }
    return cls(**filtered)
