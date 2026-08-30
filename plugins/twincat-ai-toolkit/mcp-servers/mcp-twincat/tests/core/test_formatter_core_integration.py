"""Tests verifying twincat_core integration with the Formatter and strict idempotence."""
import tempfile
from pathlib import Path
import pytest

from formatter.config import FormatterConfig
from formatter.file_processor import process_file
from twincat_core.xml.reader import read_tc_xml
from twincat_core.xml.surgical_patcher import patch_by_filter


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "formatter" / "fixtures" / "raw"


class TestFormatterCoreIntegration:
    """Verify that formatting is 100% idempotent and utilizes twincat_core cleanly."""

    def test_idempotency_format_format_equals_format(self):
        """Verify format(format(source)) == format(source) on raw ST samples."""
        config = FormatterConfig()

        test_files = list(FIXTURES_DIR.glob("**/*.Tc*"))
        assert len(test_files) > 10, f"No fixtures found under {FIXTURES_DIR}"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            for src_file in test_files[:25]:  # Test sample across various file types
                work_file = tmp_path / src_file.name
                work_file.write_bytes(src_file.read_bytes())

                # Pass 1: Initial format
                res1 = process_file(str(work_file), config, dry_run=False)
                assert res1.success is True, f"Format Pass 1 failed on {src_file.name}: {res1.errors}"
                pass1_content = work_file.read_text(encoding="utf-8")

                # Pass 2: Re-format already formatted file
                res2 = process_file(str(work_file), config, dry_run=False)
                assert res2.success is True, f"Format Pass 2 failed on {src_file.name}: {res2.errors}"
                pass2_content = work_file.read_text(encoding="utf-8")

                # Pass 3: Idempotence check
                res3 = process_file(str(work_file), config, dry_run=False)
                assert res3.changed is False, f"File {src_file.name} was modified in Pass 3 (not idempotent)"
                pass3_content = work_file.read_text(encoding="utf-8")

                assert pass1_content == pass2_content == pass3_content, f"Idempotency violated on {src_file.name}"

    def test_surgical_patching_in_formatter_preserves_xml_structure(self):
        """Verify that formatting without XML restructuring leaves non-CDATA XML bytes untouched."""
        config = FormatterConfig()

        raw_xml = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">
  <POU Name="FB_Custom" Id="{12345678-1234-1234-1234-123456789abc}" SpecialFunc="None">
    <!-- Preserved custom XML comment -->
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Custom
VAR
bFlag:BOOL:=TRUE;
nVal:INT:=10;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[
IF bFlag THEN
nVal:=nVal+1;
END_IF;
]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_file = Path(tmpdir) / "FB_Custom.TcPOU"
            tmp_file.write_text(raw_xml, encoding="utf-8")

            # Format with format_xml=False (pure ST surgical patching)
            res = process_file(str(tmp_file), config, format_xml=False, dry_run=False)
            assert res.success is True
            formatted = tmp_file.read_text(encoding="utf-8")

            # Verify that custom XML comment was preserved byte-for-byte
            assert "<!-- Preserved custom XML comment -->" in formatted
            assert 'ProductVersion="3.1.4024.12"' in formatted
            assert 'SpecialFunc="None"' in formatted

            # Verify ST inside CDATA was formatted (aligned colons and assignments)
            assert "bFlag : BOOL := TRUE;" in formatted
            assert "nVal  : INT  := 10;" in formatted
