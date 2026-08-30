"""Tests for AutoDocs syntax safety gate."""
from __future__ import annotations

from pathlib import Path
from autodocs.pipeline import process_folder


class TestAutoDocsSyntaxSafetyGate:
    def test_autodocs_skips_files_with_syntax_errors(self, tmp_path: Path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        # 1. Clean file
        clean_file = src_dir / "FB_Clean.TcPOU"
        clean_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Clean" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Clean
VAR_INPUT
    bEnable : BOOL;
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        # 2. Broken file (missing return type on function -> TC-DECL-001)
        broken_file = src_dir / "F_Broken.TcPOU"
        broken_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="F_Broken" Id="{22222222-2222-2222-2222-222222222222}">
    <Declaration><![CDATA[FUNCTION F_Broken
VAR_INPUT
    nIn : INT;
END_VAR
]]></Declaration>
  </POU>
</TcPlcObject>""", encoding="utf-8")

        report = process_folder(src_dir, out_dir)

        assert report.success is False
        assert report.errors >= 1
        # Verify docs generated for clean file but NOT for broken file
        assert (out_dir / "docs" / "FB_Clean.md").exists()
        assert not (out_dir / "docs" / "F_Broken.md").exists()
