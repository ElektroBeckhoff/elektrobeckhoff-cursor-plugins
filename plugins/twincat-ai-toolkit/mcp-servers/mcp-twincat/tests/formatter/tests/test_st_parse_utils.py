"""Tests for shared ST parse helpers."""
from __future__ import annotations

from formatter.st_parse_utils import RE_IF_MULTILINE_CALL, is_if_wrapped_call_opener


class TestIfMultilineCallOpener:
    def test_concat2(self):
        line = "IF NOT concat2("
        assert RE_IF_MULTILINE_CALL.match(line) is not None
        assert is_if_wrapped_call_opener(line)

    def test_isvalidref(self):
        line = "IF NOT __ISVALIDREF("
        assert is_if_wrapped_call_opener(line)

    def test_pointer_method(self):
        line = "IF pDyn^.Init("
        assert is_if_wrapped_call_opener(line)

    def test_not_if_expression_only(self):
        line = "IF (nA <> 0) AND_THEN (nB > 0) THEN"
        assert not is_if_wrapped_call_opener(line)
