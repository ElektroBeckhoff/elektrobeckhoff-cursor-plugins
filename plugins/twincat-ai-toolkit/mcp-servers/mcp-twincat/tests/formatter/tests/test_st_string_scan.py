"""Tests for Influx/SQL-aware ST string literal scanning."""
from __future__ import annotations

from formatter.st_formatter import _uppercase_keywords
from formatter.st_string_scan import iter_st_string_spans, sub_st_string_literals


class TestInfluxDollarQuoteStrings:
    def test_dollar_quote_inside_sql_string(self) -> None:
        line = "sPart := 'SELECT x[$'value$'] y';"
        spans = list(iter_st_string_spans(line))
        assert len(spans) == 1
        assert line[spans[0][0] : spans[0][1]] == "'SELECT x[$'value$'] y'"

    def test_short_dollar_fragment_and_keyword(self) -> None:
        line = "sPart := '$' AND \"';"
        spans = [line[a:b] for a, b in iter_st_string_spans(line)]
        assert spans == ["'$'", '"\';']
        assert _uppercase_keywords(line) == "sPart := '$' AND \"';"

    def test_find_pattern_dollar_quote(self) -> None:
        line = "_sFind    := '$'';"
        spans = [line[a:b] for a, b in iter_st_string_spans(line)]
        assert spans == ["'$''"]

    def test_influx_uri_string_stays_one_literal(self) -> None:
        line = "            _sUri := CONCAT(_sUri, '$'+AND+time+<=+$'');"
        spans = [line[a:b] for a, b in iter_st_string_spans(line)]
        assert len(spans) == 1
        assert "+AND+time+<=+" in spans[0]

    def test_format_string_dollar_quote(self) -> None:
        line = "sFormat := ' AND \"%s\" = $'%s$'';"
        spans = [line[a:b] for a, b in iter_st_string_spans(line)]
        assert len(spans) == 1
        assert "$'%s$'" in spans[0]

    def test_sub_replaces_each_literal(self) -> None:
        line = "a := '$' AND \"'\";"
        out = sub_st_string_literals(line, lambda lit: "X")
        assert out == "a := X AND X;"

    def test_cross_line_does_not_merge_literals(self) -> None:
        chunk = "sPart := '\" = $'';\nsPart := '$' AND \"';"
        spans = list(iter_st_string_spans(chunk))
        assert len(spans) == 3
