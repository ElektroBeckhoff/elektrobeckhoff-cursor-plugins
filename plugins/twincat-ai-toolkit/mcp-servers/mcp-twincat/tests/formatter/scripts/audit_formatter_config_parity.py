"""Audit defaults.json vs FormatterConfig / constants parity."""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_MCP_ROOT))

from formatter.config import (  # noqa: E402
    AlignMultilineConfig,
    AlignmentConfig,
    AlignmentHeuristicsConfig,
    BlankLinesConfig,
    CallsConfig,
    FormatterConfig,
    IndentConfig,
    KeywordsConfig,
    LineBreaksConfig,
    LineLengthConfig,
    ParenthesesConfig,
    SafetyConfig,
    SpacesConfig,
    ValidationConfig,
    XmlConfig,
    config_to_dict,
    load_config,
)
from formatter import constants  # noqa: E402

DEFAULTS_PATH = _MCP_ROOT / "formatter" / "defaults.json"

CONSTANT_MAP = {
    "MAX_LINE_LENGTH_DEFAULT": ("lineLength", "wrap_at"),
    "MAX_PARAMS_SINGLE_LINE": ("calls", "max_params_single_line"),
    "MAX_STRUCT_INIT_SINGLE_LINE": ("calls", "max_struct_init_single_line"),
    "MAX_ARRAY_INIT_SINGLE_LINE": ("calls", "max_array_init_single_line"),
    "MAX_ENUM_MEMBERS_SINGLE_LINE": ("calls", "max_enum_single_line"),
    "INDENT_SIZE_DEFAULT": ("indent", "size"),
    "XML_INDENT_SIZE_DEFAULT": ("xml", "indent_size"),
    "MULTILINE_CALL_INDENT": ("calls", "multiline_indent"),
}


def _flatten(d: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in d.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        else:
            out[path] = value
    return out


def main() -> int:
    defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    cfg = load_config()
    cfg_dict = config_to_dict(cfg)

    fd = _flatten({k: v for k, v in defaults.items() if k != "$meta"})
    fc = _flatten({k: v for k, v in cfg_dict.items() if k != "$meta"})

    missing_in_cfg = sorted(set(fd) - set(fc))
    missing_in_json = sorted(set(fc) - set(fd))
    value_diffs = sorted(k for k in fd if k in fc and fd[k] != fc[k])

    print("=== config_to_dict vs defaults.json ===")
    print("missing in config_to_dict:", missing_in_cfg or "(none)")
    print("missing in defaults.json:", missing_in_json or "(none)")
    print("value diffs:", value_diffs or "(none)")

    print("\n=== constants.py vs defaults.json ===")
    const_mismatches: list[str] = []
    for const_name, (section, key) in CONSTANT_MAP.items():
        expected = defaults[section][key]
        actual = getattr(constants, const_name)
        if actual != expected:
            const_mismatches.append(f"{const_name}: constant={actual} defaults={expected}")

    if const_mismatches:
        for line in const_mismatches:
            print(line)
    else:
        print("(all mapped constants match)")

    sections: list[tuple[str, type, object, dict]] = [
        ("indent", IndentConfig, cfg.indent, defaults.get("indent", {})),
        ("lineLength", LineLengthConfig, cfg.line_length, defaults.get("lineLength", {})),
        ("blankLines", BlankLinesConfig, cfg.blank_lines, defaults.get("blankLines", {})),
        ("spaces", SpacesConfig, cfg.spaces, defaults.get("spaces", {})),
        ("alignment", AlignmentConfig, cfg.alignment, defaults.get("alignment", {})),
        (
            "alignmentHeuristics",
            AlignmentHeuristicsConfig,
            cfg.alignment_heuristics,
            defaults.get("alignmentHeuristics", {}),
        ),
        ("alignMultiline", AlignMultilineConfig, cfg.align_multiline, defaults.get("alignMultiline", {})),
        ("lineBreaks", LineBreaksConfig, cfg.line_breaks, defaults.get("lineBreaks", {})),
        ("calls", CallsConfig, cfg.calls, defaults.get("calls", {})),
        ("parentheses", ParenthesesConfig, cfg.parentheses, defaults.get("parentheses", {})),
        ("keywords", KeywordsConfig, cfg.keywords, defaults.get("keywords", {})),
        ("xml", XmlConfig, cfg.xml, defaults.get("xml", {})),
        ("validation", ValidationConfig, cfg.validation, defaults.get("validation", {})),
        ("safety", SafetyConfig, cfg.safety, defaults.get("safety", {})),
    ]

    json_key_gaps: list[str] = []
    for sec_name, cls, inst, json_sec in sections:
        for field in dataclasses.fields(cls):
            if field.name not in json_sec:
                json_key_gaps.append(f"{sec_name}.{field.name}")

    print("\n=== dataclass fields missing in defaults.json ===")
    print(json_key_gaps or "(none)")

    if cfg.line_ending != defaults.get("lineEnding"):
        print(f"\nlineEnding mismatch: loaded={cfg.line_ending} json={defaults.get('lineEnding')}")

    failed = bool(missing_in_cfg or missing_in_json or value_diffs or const_mismatches or json_key_gaps)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
