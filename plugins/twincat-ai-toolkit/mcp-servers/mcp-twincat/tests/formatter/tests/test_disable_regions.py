"""Tests for formatting disable/enable region handling.

Verifies that the formatter correctly skips formatting in disabled regions,
supports both pragma and comment forms, is case-insensitive, and handles
all edge cases.
"""
import pytest

from formatter.st_formatter import format_st_code, split_disable_regions
from formatter.file_processor import _format_st_pipeline, _format_st_segment
from formatter.config import FormatterConfig


# ---------------------------------------------------------------------------
# split_disable_regions tests
# ---------------------------------------------------------------------------


class TestSplitDisableRegions:
    """Test the low-level region splitting logic."""

    def test_no_markers_returns_single_enabled_segment(self):
        source = "x := 1;\ny := 2;"
        segments = split_disable_regions(source)
        assert segments == [(source, True)]

    def test_pragma_disable_until_end(self):
        source = "x := 1;\n{STweep.Disable}\ny := 2;\nz := 3;"
        segments = split_disable_regions(source)
        assert len(segments) == 2
        assert segments[0] == ("x := 1;", True)
        assert segments[1] == ("{STweep.Disable}\ny := 2;\nz := 3;", False)

    def test_comment_disable_until_end(self):
        source = "x := 1;\n(*STweep.Disable*)\ny := 2;"
        segments = split_disable_regions(source)
        assert len(segments) == 2
        assert segments[0] == ("x := 1;", True)
        assert segments[1] == ("(*STweep.Disable*)\ny := 2;", False)

    def test_pragma_disable_enable_pair(self):
        source = "a := 1;\n{STweep.Disable}\nb := 2;\n{STweep.Enable}\nc := 3;"
        segments = split_disable_regions(source)
        assert len(segments) == 3
        assert segments[0] == ("a := 1;", True)
        assert segments[1] == ("{STweep.Disable}\nb := 2;\n{STweep.Enable}", False)
        assert segments[2] == ("c := 3;", True)

    def test_comment_disable_enable_pair(self):
        source = "a := 1;\n(*STweep.Disable*)\nb := 2;\n(*STweep.Enable*)\nc := 3;"
        segments = split_disable_regions(source)
        assert len(segments) == 3
        assert segments[0] == ("a := 1;", True)
        assert segments[1] == ("(*STweep.Disable*)\nb := 2;\n(*STweep.Enable*)", False)
        assert segments[2] == ("c := 3;", True)

    def test_mixed_pragma_comment(self):
        """Disable with pragma, enable with comment (intermixed)."""
        source = "a := 1;\n{STweep.Disable}\nb := 2;\n(*STweep.Enable*)\nc := 3;"
        segments = split_disable_regions(source)
        assert len(segments) == 3
        assert segments[0][1] is True
        assert segments[1][1] is False
        assert segments[2][1] is True

    def test_case_insensitive(self):
        """All casing variants should work."""
        for marker in ["{stweep.disable}", "{STWEEP.DISABLE}", "{Stweep.Disable}",
                       "{stweep.DISABLE}", "{ STweep.Disable }"]:
            source = f"a := 1;\n{marker}\nb := 2;"
            segments = split_disable_regions(source)
            assert len(segments) == 2, f"Failed for marker: {marker}"
            assert segments[1][1] is False

    def test_multiple_disable_enable_blocks(self):
        source = (
            "a := 1;\n"
            "{STweep.Disable}\n"
            "b := 2;\n"
            "{STweep.Enable}\n"
            "c := 3;\n"
            "(*STweep.Disable*)\n"
            "d := 4;\n"
            "(*STweep.Enable*)\n"
            "e := 5;"
        )
        segments = split_disable_regions(source)
        assert len(segments) == 5
        assert segments[0][1] is True   # a := 1;
        assert segments[1][1] is False  # disable...enable
        assert segments[2][1] is True   # c := 3;
        assert segments[3][1] is False  # disable...enable
        assert segments[4][1] is True   # e := 5;

    def test_empty_disabled_region(self):
        source = "{STweep.Disable}\n{STweep.Enable}"
        segments = split_disable_regions(source)
        # Disable+Enable with nothing after: one disabled segment, nothing follows
        assert len(segments) == 1
        assert segments[0] == ("{STweep.Disable}\n{STweep.Enable}", False)

    def test_empty_disabled_region_with_trailing_code(self):
        source = "{STweep.Disable}\n{STweep.Enable}\nx := 1;"
        segments = split_disable_regions(source)
        assert len(segments) == 2
        assert segments[0] == ("{STweep.Disable}\n{STweep.Enable}", False)
        assert segments[1] == ("x := 1;", True)

    def test_disable_only_at_line_start(self):
        """Markers must be the full stripped line content."""
        source = "x := 1; {STweep.Disable}\ny := 2;"
        segments = split_disable_regions(source)
        # Not a standalone disable marker -> treated as normal code
        assert len(segments) == 1
        assert segments[0][1] is True


# ---------------------------------------------------------------------------
# Integration: formatting respects disabled regions
# ---------------------------------------------------------------------------


class TestDisableRegionsFormatting:
    """Test that the formatter pipeline respects disabled regions."""

    @pytest.fixture
    def config(self):
        return FormatterConfig()

    def test_disabled_region_not_formatted(self, config):
        source = (
            "x:=1;\n"
            "{STweep.Disable}\n"
            "y:=2;\n"
            "z:=     3;\n"
            "{STweep.Enable}\n"
            "w:=4;"
        )
        result = _format_st_pipeline(source, config)
        lines = result.split("\n")

        # Region outside disable: keywords uppercased, but no := normalization
        # (format_st_code only does uppercase+blank lines+trailing ws)
        # Disabled region: EXACTLY as-is
        assert "y:=2;" in result
        assert "z:=     3;" in result

    def test_disabled_region_preserves_weird_formatting(self, config):
        """Completely bonkers formatting preserved in disabled region."""
        weird_code = "    iF   x=1  THEN\n        y:=2;end_if;"
        source = (
            "normal := TRUE;\n"
            "(*STweep.Disable*)\n"
            f"{weird_code}\n"
            "(*STweep.Enable*)\n"
            "also_normal := FALSE;"
        )
        result = _format_st_pipeline(source, config)
        assert weird_code in result

    def test_disable_until_end_of_file(self, config):
        """Disable without re-enable: rest of file untouched."""
        source = (
            "x := 1;\n"
            "{STweep.Disable}\n"
            "auto_generated := code;\n"
            "   weird   spacing   ;\n"
            "NO_KEYWORDS_CHANGED := true;"
        )
        result = _format_st_pipeline(source, config)
        assert "   weird   spacing   ;" in result
        assert "NO_KEYWORDS_CHANGED := true;" in result

    def test_formatted_regions_still_formatted(self, config):
        """Code outside disabled regions is still properly formatted."""
        source = (
            "my_var:=true;\n"
            "{STweep.Disable}\n"
            "skip_this:=1;\n"
            "{STweep.Enable}\n"
            "another_var:=false;"
        )
        result = _format_st_pipeline(source, config)
        # Keywords in enabled regions should be uppercased
        assert "TRUE" in result.split("{STweep.Disable}")[0]
        assert "FALSE" in result.split("{STweep.Enable}")[1]
        # Disabled region stays exactly
        assert "skip_this:=1;" in result

    def test_no_markers_full_format(self, config):
        """Without any markers, everything is formatted normally."""
        source = "x:=true;\ny:=false;"
        result = _format_st_pipeline(source, config)
        assert "TRUE" in result
        assert "FALSE" in result

    def test_idempotent_with_disable_regions(self, config):
        """Formatting twice produces same result."""
        source = (
            "x := 1;\n"
            "{STweep.Disable}\n"
            "y:=2;\n"
            "{STweep.Enable}\n"
            "z := 3;"
        )
        result1 = _format_st_pipeline(source, config)
        result2 = _format_st_pipeline(result1, config)
        assert result1 == result2
