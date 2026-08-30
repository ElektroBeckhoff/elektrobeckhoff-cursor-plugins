"""Tests for multi-space collapse with Influx-aware string scanning."""
from __future__ import annotations

from formatter.st_formatter import _collapse_spaces_safe, _normalize_inline_spaces


class TestCollapseSpacesSafe:
    def test_preserves_doubled_single_quote_in_string(self):
        line = "sA  :=  'part1 '' part2';"
        out = _collapse_spaces_safe(line)
        assert "''" in out
        assert "'part1 '' part2'" in out

    def test_preserves_dollar_quote_influx_string(self):
        line = "sE  :=  '$'+AND+time+<=+$'';"
        out = _collapse_spaces_safe(line)
        assert "$'+AND+time+<=+$''" in out

    def test_preserves_assignment_padding(self):
        line = "nA      := 1;"
        assert _collapse_spaces_safe(line) == "nA      := 1;"

    def test_normalize_inline_spaces_preserves_string_internals(self):
        source = "sA  :=  'a '' b';\nsB  :=  '$'+AND+time+<=+$'';"
        out = _normalize_inline_spaces(source)
        assert "''" in out
        assert "$'+AND+time+<=+$''" in out
