"""Tests for config system."""
import json
import pytest
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.config import load_config, config_to_dict, FormatterConfig, _dict_to_config
from formatter import constants


_DEFAULTS_PATH = Path(__file__).resolve().parents[3] / "formatter" / "defaults.json"


def _flatten_config(d: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in d.items():
        if key == "$meta" or (isinstance(key, str) and key.startswith("_")):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten_config(value, path))
        else:
            out[path] = value
    return out


class TestDefaultConfig:
    def test_loads_defaults(self):
        cfg = load_config()
        assert cfg.indent.size == 4
        assert cfg.line_length.wrap_at == 230
        assert cfg.keywords.uppercase is True
        assert cfg.xml.indent_size == 2

    def test_config_to_dict(self):
        cfg = load_config()
        d = config_to_dict(cfg)
        assert d["indent"]["size"] == 4
        assert d["lineLength"]["wrap_at"] == 230
        assert "$meta" in d
        assert "alignment.address_assignments" in d["$meta"]

    def test_meta_loaded_from_defaults(self):
        cfg = load_config()
        assert cfg.meta.get("alignmentHeuristics.three_line_assign_group_max_lhs_len")
        assert cfg.meta.get("alignMultiline.array_initializers")

    def test_config_to_dict_matches_defaults_json(self):
        defaults = json.loads(_DEFAULTS_PATH.read_text(encoding="utf-8"))
        cfg_dict = config_to_dict(load_config())
        flat_defaults = _flatten_config(defaults)
        flat_cfg = _flatten_config(cfg_dict)
        assert flat_defaults == flat_cfg

    def test_constants_match_defaults_json(self):
        defaults = json.loads(_DEFAULTS_PATH.read_text(encoding="utf-8"))
        assert constants.MAX_LINE_LENGTH_DEFAULT == defaults["lineLength"]["wrap_at"]
        assert constants.MAX_PARAMS_SINGLE_LINE == defaults["calls"]["max_params_single_line"]
        assert constants.MULTILINE_CALL_INDENT == defaults["calls"]["multiline_indent"]

    def test_syntax_check_roundtrip(self):
        cfg = load_config()
        assert cfg.safety.syntax_check is True
        d = config_to_dict(cfg)
        cfg2 = _dict_to_config(d)
        assert cfg2.safety.syntax_check is True

    def test_underscore_pseudo_keys_ignored(self):
        import json
        import tempfile
        from formatter.config import _dict_to_config

        payload = {
            "alignment": {
                "_note": "ignored",
                "assignments": False,
            }
        }
        cfg = _dict_to_config(payload)
        assert cfg.alignment.assignments is False


class TestUserOverride:
    def test_override_merges(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"indent": {"size": 2}}, f)
            f.flush()
            cfg = load_config(config_path=f.name)

        os.unlink(f.name)
        assert cfg.indent.size == 2
        assert cfg.line_length.wrap_at == 230  # default preserved

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("not json")
            f.flush()
            cfg = load_config(config_path=f.name)

        os.unlink(f.name)
        assert cfg.indent.size == 4  # falls back to defaults
