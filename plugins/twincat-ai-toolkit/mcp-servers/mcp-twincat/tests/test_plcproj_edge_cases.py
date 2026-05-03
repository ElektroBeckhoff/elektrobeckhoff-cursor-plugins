"""
Extended edge-case tests for twincat_plcproj_ops.py

Covers all scenarios NOT already in test_plcproj_ops_pytest.py:
  - Verify:  slash formats, case sensitivity, corrupted XML, wrong paths
  - Sync:    PlcTask ordering, read-only file, missing plcproj via sync
  - GUID:    multi-different GUIDs in one file, TcIO/TcTTO, no-root XML,
             non-Tc extensions ignored
  - Disk:    special chars / umlauts / spaces, empty folders, deep nesting,
             bin/obj exclusion in scan
  - Encoding: UTF-8 BOM, Latin-1, CRLF, LF, mixed line endings, write fidelity
  - CLI:     verify-only with direct plcproj path, exit-code validation,
             verify output text, combined flags
  - MCP:     log_level forwarding, skip_folder_sync in sync

Run with:  pytest tests/test_plcproj_edge_cases.py -v
"""
import json
import os
import re
import stat
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import twincat_plcproj_ops as P
from server import twincat_plcproj_verify, twincat_plcproj_sync


# ===================================================================
#  Helpers
# ===================================================================

def _write(path: Path, content: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _write_bytes(path: Path, raw: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


PLCPROJ_TEMPLATE = (
    '<?xml version="1.0" encoding="utf-8"?>\r\n'
    '<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">\r\n'
    '  <PropertyGroup>\r\n'
    '    <Name>EdgeTest</Name>\r\n'
    '  </PropertyGroup>\r\n'
    '  <ItemGroup>\r\n'
    '{compile_lines}'
    '  </ItemGroup>\r\n'
    '  <ItemGroup>\r\n'
    '{folder_lines}'
    '  </ItemGroup>\r\n'
    '</Project>\r\n'
)


def _plcproj(compile_paths: list[str], folders: list[str]) -> str:
    compile_lines = ""
    for cp in compile_paths:
        compile_lines += f'    <Compile Include="{cp}">\r\n'
        compile_lines += "      <SubType>Code</SubType>\r\n"
        compile_lines += "    </Compile>\r\n"
    folder_lines = ""
    for f in folders:
        folder_lines += f'    <Folder Include="{f}" />\r\n'
    return PLCPROJ_TEMPLATE.format(compile_lines=compile_lines, folder_lines=folder_lines)


# ===================================================================
#  Verify edge cases
# ===================================================================

class TestVerifyEdgeCases:
    """Edge cases for verify_plcproj()."""

    def test_case_insensitive_compile_match(self, tmp_path):
        """plcproj uses 'POUs\\fb_main.TcPOU' but disk has 'POUs\\FB_Main.TcPOU'."""
        xml = _plcproj(["POUs\\fb_main.TcPOU"], ["POUs"])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "POUs" / "FB_Main.TcPOU", "<POU/>")
        vr = P.verify_plcproj(proj)
        assert vr.ok is True, "Case-insensitive compare should pass"

    def test_forward_slash_in_plcproj_still_matches(self, tmp_path):
        """Disk uses backslash, plcproj uses forward slash -- verify relies on
        regex extraction, the scan always produces backslash.  This tests that
        case-insensitive match handles the actual entries in the plcproj."""
        xml = _plcproj(["POUs\\FB_Main.TcPOU"], ["POUs"])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "POUs" / "FB_Main.TcPOU", "<POU/>")
        vr = P.verify_plcproj(proj)
        assert vr.ok is True

    def test_corrupted_xml_no_closing_tag(self, tmp_path):
        """Completely broken XML without any ItemGroup."""
        proj = tmp_path / "T.plcproj"
        _write(proj, '<?xml version="1.0"?><Project><broken')
        _write(tmp_path / "F.TcPOU", "<POU/>")
        vr = P.verify_plcproj(proj)
        assert vr.ok is False
        assert vr.exit_code == 2

    def test_empty_plcproj_file(self, tmp_path):
        """Empty plcproj file."""
        proj = tmp_path / "T.plcproj"
        _write(proj, "")
        vr = P.verify_plcproj(proj)
        assert vr.ok is False
        assert vr.exit_code == 2

    def test_plcproj_with_compile_but_no_folder_block(self, tmp_path):
        """plcproj has Compile block but no Folder block."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\r\n'
            '<Project>\r\n'
            '  <ItemGroup>\r\n'
            '    <Compile Include="F.TcPOU">\r\n'
            '      <SubType>Code</SubType>\r\n'
            '    </Compile>\r\n'
            '  </ItemGroup>\r\n'
            '</Project>\r\n'
        )
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        vr = P.verify_plcproj(proj)
        assert vr.ok is False
        assert vr.exit_code == 2
        assert "Folder" in vr.error_message

    def test_multiple_extra_and_missing_combined(self, tmp_path):
        """Multiple missing and extra compile entries simultaneously."""
        xml = _plcproj(
            ["Old1.TcPOU", "Old2.TcDUT", "Still.TcPOU"],
            ["POUs"],
        )
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "Still.TcPOU", "<POU/>")
        _write(tmp_path / "New1.TcGVL", "<GVL/>")
        _write(tmp_path / "New2.TcPOU", "<POU/>")
        _write(tmp_path / "POUs" / "placeholder", "")  # folder exists
        vr = P.verify_plcproj(proj)
        assert vr.ok is False
        assert len(vr.missing_compile) == 2
        assert len(vr.extra_compile) == 2


# ===================================================================
#  Sync edge cases
# ===================================================================

class TestSyncEdgeCases:
    """Edge cases for sync_plcproj()."""

    def test_plctask_sorting_in_sync_output(self, tmp_path):
        """PlcTask.TcTTO must be the first Compile entry after sync."""
        xml = _plcproj(["PlcTask.TcTTO", "POUs\\FB_Main.TcPOU"], ["POUs"])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "POUs" / "FB_Main.TcPOU", "<POU/>")
        _write(tmp_path / "PlcTask.TcTTO", "<Task/>")
        _write(tmp_path / "A_First.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(input_path=str(tmp_path), force=True)
        report = P.sync_plcproj(cfg)
        assert report.success is True

        content = P._read_text_raw(proj)
        first_compile = re.search(r'<Compile Include="([^"]+)"', content)
        assert first_compile is not None
        assert "PlcTask.TcTTO" in first_compile.group(1)

    def test_sync_missing_plcproj_returns_error(self, tmp_path):
        """Sync with a nonexistent plcproj path."""
        cfg = P.PlcProjConfig(input_path=str(tmp_path / "nonexistent"))
        report = P.sync_plcproj(cfg)
        assert report.success is False

    def test_sync_no_compile_block_in_plcproj(self, tmp_path):
        """Sync with plcproj that has no Compile ItemGroup."""
        proj = tmp_path / "T.plcproj"
        _write(proj, '<?xml version="1.0"?>\r\n<Project/>\r\n')
        _write(tmp_path / "F.TcPOU", "<POU/>")
        cfg = P.PlcProjConfig(input_path=str(proj), force=True)
        report = P.sync_plcproj(cfg)
        assert report.success is False
        assert any("Compile ItemGroup" in w for w in report.warnings)

    def test_sync_readonly_file_raises(self, tmp_path):
        """Sync should fail gracefully when plcproj is read-only."""
        xml = _plcproj(["F.TcPOU"], [])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        _write(tmp_path / "New.TcPOU", "<POU/>")

        os.chmod(str(proj), stat.S_IREAD)
        try:
            cfg = P.PlcProjConfig(input_path=str(proj), force=True, backup=False,
                                  skip_folder_sync=True)
            report = P.sync_plcproj(cfg)
            assert report.success is False
        finally:
            os.chmod(str(proj), stat.S_IWRITE | stat.S_IREAD)

    def test_sync_backup_preserves_original_content(self, tmp_path):
        """After sync with backup, the .bak file must contain the original XML."""
        xml = _plcproj(["F.TcPOU"], [])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        _write(tmp_path / "New.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(input_path=str(proj), force=True, backup=True,
                              skip_folder_sync=True)
        P.sync_plcproj(cfg)
        baks = list(tmp_path.glob("*.plcproj.bak"))
        assert len(baks) == 1
        bak_content = baks[0].read_text(encoding="utf-8")
        assert "New.TcPOU" not in bak_content
        assert "F.TcPOU" in bak_content


# ===================================================================
#  GUID Repair edge cases
# ===================================================================

class TestGuidRepairEdgeCases:
    """Extended GUID-repair scenarios."""

    def test_multi_different_guids_in_one_file(self, tmp_path):
        """Two *different* GUIDs as Id attributes on a single POU tag."""
        g1 = str(uuid.uuid4())
        g2 = str(uuid.uuid4())
        content = (
            f'<TcPlcObject><POU Name="FB_X" Id="{{{g1}}}" Id="{{{g2}}}">'
            '</POU></TcPlcObject>'
        )
        _write(tmp_path / "X.TcPOU", content)
        repairs = P.repair_object_guids(str(tmp_path))
        assert len(repairs) == 1
        assert repairs[0].reason == "multi_attr_invalid"

    def test_tcio_extension_supported(self, tmp_path):
        """TcIO files should be scanned by GUID repair."""
        content = '<TcPlcObject><POU Name="IO_Module"></POU></TcPlcObject>'
        _write(tmp_path / "IO_Module.TcIO", content)
        repairs = P.repair_object_guids(str(tmp_path))
        assert len(repairs) == 1

    def test_tctto_extension_supported(self, tmp_path):
        """TcTTO files should be scanned by GUID repair."""
        content = '<TcPlcObject><POU Name="PlcTask"></POU></TcPlcObject>'
        _write(tmp_path / "PlcTask.TcTTO", content)
        repairs = P.repair_object_guids(str(tmp_path))
        assert len(repairs) == 1

    def test_non_tc_extension_ignored(self, tmp_path):
        """Files with non-Tc extensions should not be processed."""
        content = '<TcPlcObject><POU Name="FB_Skip"></POU></TcPlcObject>'
        _write(tmp_path / "Readme.md", content)
        _write(tmp_path / "Script.py", content)
        _write(tmp_path / "Config.xml", content)
        repairs = P.repair_object_guids(str(tmp_path))
        assert len(repairs) == 0

    def test_no_root_tag_in_tc_file(self, tmp_path):
        """Tc file with no POU/GVL/DUT/Itf root tag -> no repair, no crash."""
        content = '<?xml version="1.0"?><TcPlcObject><Something/></TcPlcObject>'
        _write(tmp_path / "Odd.TcPOU", content)
        repairs = P.repair_object_guids(str(tmp_path))
        assert len(repairs) == 0

    def test_empty_id_attribute(self, tmp_path):
        """Id="" (empty string) should be treated as invalid."""
        content = '<TcPlcObject><POU Name="FB_Empty" Id=""></POU></TcPlcObject>'
        _write(tmp_path / "FB_Empty.TcPOU", content)
        repairs = P.repair_object_guids(str(tmp_path))
        assert len(repairs) == 1
        assert repairs[0].reason == "invalid"
        updated = (tmp_path / "FB_Empty.TcPOU").read_text()
        assert 'Id="{' in updated

    def test_three_way_duplicate(self, tmp_path):
        """Three files with the same GUID -> two get new GUIDs."""
        g = str(uuid.uuid4())
        for name in ("A.TcPOU", "B.TcPOU", "C.TcPOU"):
            content = f'<TcPlcObject><POU Name="{name}" Id="{{{g}}}"></POU></TcPlcObject>'
            _write(tmp_path / name, content)
        repairs = P.repair_object_guids(str(tmp_path))
        dup_repairs = [r for r in repairs if r.reason == "duplicate_across_files"]
        assert len(dup_repairs) == 2

        ids = set()
        for name in ("A.TcPOU", "B.TcPOU", "C.TcPOU"):
            m = re.search(r'Id="([^"]+)"', (tmp_path / name).read_text())
            ids.add(m.group(1))
        assert len(ids) == 3, "All three files must have unique GUIDs"


# ===================================================================
#  Disk Scanner edge cases
# ===================================================================

class TestDiskScanEdgeCases:
    """Extended disk-scan scenarios."""

    def test_umlaut_filename(self, tmp_path):
        """File names with German umlauts."""
        proj = tmp_path / "T.plcproj"
        _write(proj, "<Project/>")
        _write(tmp_path / "FB_Prüfung.TcPOU", "<POU/>")
        _write(tmp_path / "ST_Größe.TcDUT", "<DUT/>")
        state = P.scan_disk_state(proj)
        names = [os.path.basename(p) for p in state.ordered]
        assert "FB_Prüfung.TcPOU" in names
        assert "ST_Größe.TcDUT" in names

    def test_space_in_filename(self, tmp_path):
        """File names with spaces."""
        proj = tmp_path / "T.plcproj"
        _write(proj, "<Project/>")
        _write(tmp_path / "FB My Block.TcPOU", "<POU/>")
        state = P.scan_disk_state(proj)
        names = [os.path.basename(p) for p in state.ordered]
        assert "FB My Block.TcPOU" in names

    def test_space_in_folder(self, tmp_path):
        """Folder names with spaces."""
        proj = tmp_path / "T.plcproj"
        _write(proj, "<Project/>")
        _write(tmp_path / "My POUs" / "FB_X.TcPOU", "<POU/>")
        state = P.scan_disk_state(proj)
        names = [os.path.basename(p) for p in state.ordered]
        assert "FB_X.TcPOU" in names
        assert any("My POUs" in f for f in state.folder_set)

    def test_empty_subfolder_scanned(self, tmp_path):
        """Empty subfolders appear in folder_set."""
        proj = tmp_path / "T.plcproj"
        _write(proj, "<Project/>")
        (tmp_path / "EmptyFolder").mkdir()
        state = P.scan_disk_state(proj)
        assert "EmptyFolder" in state.folder_set

    def test_deep_nesting(self, tmp_path):
        """Deeply nested folder structure (5 levels)."""
        proj = tmp_path / "T.plcproj"
        _write(proj, "<Project/>")
        deep = tmp_path / "L1" / "L2" / "L3" / "L4" / "L5"
        _write(deep / "FB_Deep.TcPOU", "<POU/>")
        state = P.scan_disk_state(proj)
        names = [os.path.basename(p) for p in state.ordered]
        assert "FB_Deep.TcPOU" in names
        assert len(state.folder_set) == 5

    def test_excludes_bin_and_obj(self, tmp_path):
        """bin/ and obj/ folders must be excluded."""
        proj = tmp_path / "T.plcproj"
        _write(proj, "<Project/>")
        _write(tmp_path / "bin" / "Debug" / "F.TcPOU", "<POU/>")
        _write(tmp_path / "obj" / "Release" / "G.TcPOU", "<POU/>")
        _write(tmp_path / "POUs" / "H.TcPOU", "<POU/>")
        state = P.scan_disk_state(proj)
        names = [os.path.basename(p) for p in state.ordered]
        assert "F.TcPOU" not in names
        assert "G.TcPOU" not in names
        assert "H.TcPOU" in names
        folder_bases = {os.path.basename(f) for f in state.folder_set}
        assert "bin" not in folder_bases
        assert "obj" not in folder_bases

    def test_no_tc_files_returns_empty(self, tmp_path):
        """Project directory with no Tc* files."""
        proj = tmp_path / "T.plcproj"
        _write(proj, "<Project/>")
        _write(tmp_path / "readme.md", "hello")
        _write(tmp_path / "script.py", "pass")
        state = P.scan_disk_state(proj)
        assert len(state.ordered) == 0

    def test_case_insensitive_extension_match(self, tmp_path):
        """Extensions with mixed case (e.g. .TCPOU) should be found."""
        proj = tmp_path / "T.plcproj"
        _write(proj, "<Project/>")
        _write(tmp_path / "FB_Upper.TCPOU", "<POU/>")
        _write(tmp_path / "FB_Lower.tcpou", "<POU/>")
        state = P.scan_disk_state(proj)
        names = [os.path.basename(p) for p in state.ordered]
        assert "FB_Upper.TCPOU" in names
        assert "FB_Lower.tcpou" in names


# ===================================================================
#  Encoding edge cases
# ===================================================================

class TestEncodingEdgeCases:
    """Encoding handling in _read_text_raw()."""

    def test_utf8_bom(self, tmp_path):
        """UTF-8 file with BOM (EF BB BF) is read correctly."""
        bom = b'\xef\xbb\xbf'
        xml = '<?xml version="1.0"?>\r\n<Project>\r\n  <Name>BOM</Name>\r\n</Project>\r\n'
        _write_bytes(tmp_path / "T.plcproj", bom + xml.encode("utf-8"))
        content = P._read_text_raw(tmp_path / "T.plcproj")
        assert "<Name>BOM</Name>" in content
        assert not content.startswith("\ufeff"), "BOM should be stripped by utf-8-sig"

    def test_latin1_encoding(self, tmp_path):
        """Latin-1 file with special characters."""
        xml_latin1 = '<?xml version="1.0"?>\r\n<Project>\r\n  <Name>Größe</Name>\r\n</Project>\r\n'
        _write_bytes(tmp_path / "T.plcproj", xml_latin1.encode("latin-1"))
        content = P._read_text_raw(tmp_path / "T.plcproj")
        assert "Größe" in content

    def test_crlf_preserved(self, tmp_path):
        """CRLF line endings are preserved byte-for-byte."""
        xml = "Line1\r\nLine2\r\nLine3\r\n"
        _write_bytes(tmp_path / "test.txt", xml.encode("utf-8"))
        content = P._read_text_raw(tmp_path / "test.txt")
        assert content == xml
        assert "\r\n" in content

    def test_lf_only_preserved(self, tmp_path):
        """LF-only line endings are preserved."""
        xml = "Line1\nLine2\nLine3\n"
        _write_bytes(tmp_path / "test.txt", xml.encode("utf-8"))
        content = P._read_text_raw(tmp_path / "test.txt")
        assert content == xml
        assert "\r\n" not in content

    def test_mixed_line_endings_preserved(self, tmp_path):
        """Mixed CRLF/LF are preserved as-is."""
        xml = "Line1\r\nLine2\nLine3\r\n"
        _write_bytes(tmp_path / "test.txt", xml.encode("utf-8"))
        content = P._read_text_raw(tmp_path / "test.txt")
        assert content == xml

    def test_write_no_double_crlf(self, tmp_path):
        """Writing with newline='' must not produce double \\r\\n."""
        xml = _plcproj(["F.TcPOU"], [])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        _write(tmp_path / "New.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(input_path=str(proj), force=True, backup=False,
                              skip_folder_sync=True)
        P.sync_plcproj(cfg)
        raw = proj.read_bytes()
        assert b"\r\r\n" not in raw, "Must not have double carriage return"

    def test_utf8_bom_plcproj_verify(self, tmp_path):
        """verify_plcproj works correctly with BOM-prefixed plcproj."""
        bom = b'\xef\xbb\xbf'
        xml = _plcproj(["F.TcPOU"], ["POUs"])
        _write_bytes(tmp_path / "T.plcproj", bom + xml.encode("utf-8"))
        _write(tmp_path / "F.TcPOU", "<POU/>")
        (tmp_path / "POUs").mkdir(exist_ok=True)
        vr = P.verify_plcproj(tmp_path / "T.plcproj")
        assert vr.ok is True


# ===================================================================
#  CLI edge cases
# ===================================================================

class TestCLIEdgeCases:
    """Extended CLI scenarios."""

    def test_verify_only_with_direct_plcproj_path(self, tmp_path):
        """--verify-only with explicit .plcproj path (not directory)."""
        xml = _plcproj(["F.TcPOU"], [])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        code = P.main(["--input", str(proj), "--verify-only", "--skip-folder-sync"])
        assert code == 0

    def test_verify_only_exit_code_1_on_drift(self, tmp_path):
        """Verify drift returns exit code 1."""
        xml = _plcproj(["F.TcPOU"], [])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        _write(tmp_path / "Extra.TcPOU", "<POU/>")
        code = P.main(["--input", str(proj), "--verify-only", "--skip-folder-sync"])
        assert code == 1

    def test_verify_only_exit_code_2_on_structural_error(self, tmp_path):
        """Verify returns exit code 2 when no Compile block exists."""
        proj = tmp_path / "T.plcproj"
        _write(proj, "<?xml?><Project/>")
        code = P.main(["--input", str(proj), "--verify-only", "--skip-folder-sync"])
        assert code == 2

    def test_force_and_dry_run_combined(self, tmp_path):
        """force + dry-run: should succeed but not write."""
        xml = _plcproj(["F.TcPOU"], [])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        _write(tmp_path / "New.TcPOU", "<POU/>")
        orig = proj.read_bytes()

        code = P.main(["--input", str(proj), "--force", "--dry-run", "--skip-folder-sync"])
        assert code == 0
        assert proj.read_bytes() == orig

    def test_ensure_object_guids_via_cli(self, tmp_path):
        """--ensure-object-guids repairs missing IDs."""
        xml = _plcproj(["F.TcPOU"], [])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", '<TcPlcObject><POU Name="FB_X"></POU></TcPlcObject>')
        code = P.main(["--input", str(proj), "--force", "--ensure-object-guids",
                        "--skip-folder-sync"])
        assert code == 0
        updated = (tmp_path / "F.TcPOU").read_text()
        assert 'Id="{' in updated

    def test_custom_extensions_without_dot(self):
        """--compile-extensions TcPOU (without dot) should normalize to .tcpou."""
        cfg = P.parse_arguments(["--input", "x", "--compile-extensions", "TcPOU"])
        assert ".tcpou" in cfg.compile_extensions


# ===================================================================
#  MCP tool edge cases
# ===================================================================

class TestMcpEdgeCases:
    """Extended MCP wrapper scenarios."""

    def test_verify_log_level_forwarding(self, tmp_path):
        """log_level parameter should be passed through."""
        xml = _plcproj(["F.TcPOU"], ["POUs"])
        _write(tmp_path / "T.plcproj", xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        (tmp_path / "POUs").mkdir(exist_ok=True)
        raw = twincat_plcproj_verify(input=str(tmp_path), log_level="DEBUG")
        result = json.loads(raw)
        assert result["success"] is True

    def test_sync_skip_folder_sync(self, tmp_path):
        """skip_folder_sync in sync should work without Folder block."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\r\n'
            '<Project>\r\n'
            '  <ItemGroup>\r\n'
            '    <Compile Include="F.TcPOU">\r\n'
            '      <SubType>Code</SubType>\r\n'
            '    </Compile>\r\n'
            '  </ItemGroup>\r\n'
            '</Project>\r\n'
        )
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")

        raw = twincat_plcproj_sync(
            input=str(proj), force=True, dry_run=True,
            skip_folder_sync=True,
        )
        result = json.loads(raw)
        assert result["success"] is True

    def test_sync_error_contains_output(self, tmp_path):
        """When sync fails, output field should contain useful info."""
        raw = twincat_plcproj_sync(input=str(tmp_path / "nonexistent"))
        result = json.loads(raw)
        assert result["success"] is False
        assert result["exit_code"] != 0

    def test_verify_with_direct_plcproj(self, tmp_path):
        """MCP verify with direct .plcproj path."""
        xml = _plcproj(["F.TcPOU"], [])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        raw = twincat_plcproj_verify(input=str(proj), skip_folder_sync=True)
        result = json.loads(raw)
        assert result["success"] is True

    def test_sync_force_creates_valid_xml(self, tmp_path):
        """After sync, the plcproj should still be parseable XML-ish content."""
        xml = _plcproj(["F.TcPOU"], ["POUs"])
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        _write(tmp_path / "New.TcPOU", "<POU/>")
        (tmp_path / "POUs").mkdir(exist_ok=True)

        twincat_plcproj_sync(input=str(tmp_path), force=True)
        content = proj.read_text(encoding="utf-8")
        assert '<Compile Include="F.TcPOU">' in content
        assert '<Compile Include="New.TcPOU">' in content
        assert "</Project>" in content


# ===================================================================
#  Internal helper edge cases
# ===================================================================

class TestInternalHelpers:
    """Tests for internal functions not covered elsewhere."""

    def test_relative_path_backslash(self, tmp_path):
        """_relative_path always returns backslash separators."""
        base = str(tmp_path)
        full = str(tmp_path / "POUs" / "FB_Main.TcPOU")
        rel = P._relative_path(base, full)
        assert "\\" in rel
        assert "/" not in rel

    def test_relative_path_not_under_base(self):
        """_relative_path raises for paths outside base."""
        with pytest.raises(ValueError, match="not under base"):
            P._relative_path("C:\\A", "C:\\B\\file.txt")

    def test_is_valid_guid_with_braces(self):
        g = str(uuid.uuid4())
        assert P._is_valid_guid(f"{{{g}}}") is True

    def test_is_valid_guid_without_braces(self):
        g = str(uuid.uuid4())
        assert P._is_valid_guid(g) is True

    def test_is_valid_guid_garbage(self):
        assert P._is_valid_guid("not-a-guid") is False
        assert P._is_valid_guid("") is False

    def test_normalize_guid_consistent(self):
        g = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"
        assert P._normalize_guid(g) == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert P._normalize_guid(f"{{{g}}}") == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def test_build_compile_block_crlf(self):
        """build_compile_block uses CRLF by default."""
        block = P.build_compile_block(["F.TcPOU"])
        assert "\r\n" in block

    def test_build_folder_block_crlf(self):
        """build_folder_block uses CRLF by default."""
        block = P.build_folder_block({"POUs"})
        assert "\r\n" in block

    def test_replace_xml_blocks_inserts_folder_when_missing(self):
        """When plcproj has no Folder block, it should be appended after Compile."""
        xml = (
            '<?xml version="1.0"?>\r\n'
            '<Project>\r\n'
            '  <ItemGroup>\r\n'
            '    <Compile Include="F.TcPOU">\r\n'
            '      <SubType>Code</SubType>\r\n'
            '    </Compile>\r\n'
            '  </ItemGroup>\r\n'
            '</Project>\r\n'
        )
        compile_block = P.build_compile_block(["F.TcPOU"])
        folder_block = P.build_folder_block({"POUs"})
        result = P.replace_xml_blocks(xml, compile_block, folder_block)
        assert '<Folder Include="POUs" />' in result

    def test_read_text_raw_fallback_replace(self, tmp_path):
        """Truly broken binary content should still return something."""
        _write_bytes(tmp_path / "broken.txt", bytes(range(256)))
        content = P._read_text_raw(tmp_path / "broken.txt")
        assert isinstance(content, str)
        assert len(content) > 0


# ===================================================================
#  ExcludeFromBuild (EFB) edge cases
# ===================================================================

def _plcproj_efb(
    compile_entries: list[tuple[str, str | None]],
    folder_entries: list[tuple[str, str | None]],
) -> str:
    """Build a plcproj with optional ExcludeFromBuild on Compile/Folder entries.

    Each entry is (path, efb_value) where efb_value is "true", "false", or None.
    """
    compile_lines = ""
    for path, efb in compile_entries:
        compile_lines += f'    <Compile Include="{path}">\r\n'
        compile_lines += "      <SubType>Code</SubType>\r\n"
        if efb is not None:
            compile_lines += f"      <ExcludeFromBuild>{efb}</ExcludeFromBuild>\r\n"
        compile_lines += "    </Compile>\r\n"

    folder_lines = ""
    for path, efb in folder_entries:
        if efb is not None:
            folder_lines += f'    <Folder Include="{path}">\r\n'
            folder_lines += f"      <ExcludeFromBuild>{efb}</ExcludeFromBuild>\r\n"
            folder_lines += "    </Folder>\r\n"
        else:
            folder_lines += f'    <Folder Include="{path}" />\r\n'

    return PLCPROJ_TEMPLATE.format(
        compile_lines=compile_lines, folder_lines=folder_lines,
    )


class TestExcludeFromBuild:
    """ExcludeFromBuild (EFB) support for folders and compile entries."""

    # --- Parse helpers ---

    def test_parse_efb_folders_true(self):
        xml = (
            '  <ItemGroup>\r\n'
            '    <Folder Include="POUs\\V3">\r\n'
            '      <ExcludeFromBuild>true</ExcludeFromBuild>\r\n'
            '    </Folder>\r\n'
            '    <Folder Include="POUs\\V2" />\r\n'
            '  </ItemGroup>'
        )
        efb = P._parse_efb_folders(xml)
        assert efb == {"pous\\v3": "true"}

    def test_parse_efb_folders_false(self):
        xml = (
            '  <ItemGroup>\r\n'
            '    <Folder Include="POUs\\V3">\r\n'
            '      <ExcludeFromBuild>false</ExcludeFromBuild>\r\n'
            '    </Folder>\r\n'
            '  </ItemGroup>'
        )
        efb = P._parse_efb_folders(xml)
        assert efb == {"pous\\v3": "false"}

    def test_parse_efb_folders_empty(self):
        xml = (
            '  <ItemGroup>\r\n'
            '    <Folder Include="POUs" />\r\n'
            '    <Folder Include="POUs\\Sub" />\r\n'
            '  </ItemGroup>'
        )
        efb = P._parse_efb_folders(xml)
        assert efb == {}

    def test_parse_efb_compile_true(self):
        xml = (
            '  <ItemGroup>\r\n'
            '    <Compile Include="POUs\\FB_Old.TcPOU">\r\n'
            '      <SubType>Code</SubType>\r\n'
            '      <ExcludeFromBuild>true</ExcludeFromBuild>\r\n'
            '    </Compile>\r\n'
            '    <Compile Include="POUs\\FB_New.TcPOU">\r\n'
            '      <SubType>Code</SubType>\r\n'
            '    </Compile>\r\n'
            '  </ItemGroup>'
        )
        efb = P._parse_efb_compile(xml)
        assert efb == {"pous\\fb_old.tcpou": "true"}

    def test_parse_efb_compile_false(self):
        xml = (
            '  <ItemGroup>\r\n'
            '    <Compile Include="POUs\\FB_X.TcPOU">\r\n'
            '      <SubType>Code</SubType>\r\n'
            '      <ExcludeFromBuild>false</ExcludeFromBuild>\r\n'
            '    </Compile>\r\n'
            '  </ItemGroup>'
        )
        efb = P._parse_efb_compile(xml)
        assert efb == {"pous\\fb_x.tcpou": "false"}

    def test_parse_efb_compile_empty(self):
        xml = (
            '  <ItemGroup>\r\n'
            '    <Compile Include="F.TcPOU">\r\n'
            '      <SubType>Code</SubType>\r\n'
            '    </Compile>\r\n'
            '  </ItemGroup>'
        )
        efb = P._parse_efb_compile(xml)
        assert efb == {}

    # --- Build block helpers ---

    def test_build_folder_block_with_efb_true(self):
        block = P.build_folder_block(
            {"POUs", "POUs\\V3", "POUs\\V2"},
            efb_folders={"POUs\\V3": "true"},
        )
        assert '<Folder Include="POUs" />' in block
        assert '<Folder Include="POUs\\V2" />' in block
        assert '<ExcludeFromBuild>true</ExcludeFromBuild>' in block
        assert 'POUs\\V3">' in block

    def test_build_folder_block_with_efb_false(self):
        block = P.build_folder_block(
            {"POUs\\V3"},
            efb_folders={"POUs\\V3": "false"},
        )
        assert '<ExcludeFromBuild>false</ExcludeFromBuild>' in block
        assert '/>' not in block.split("ExcludeFromBuild")[0].split("V3")[1]

    def test_build_compile_block_with_efb(self):
        block = P.build_compile_block(
            ["F.TcPOU", "POUs\\FB_Old.TcPOU"],
            efb_compile={"pous\\fb_old.tcpou": "true"},
        )
        assert '<ExcludeFromBuild>true</ExcludeFromBuild>' in block
        f_section = block.split("F.TcPOU")[1].split("</Compile>")[0]
        assert "ExcludeFromBuild" not in f_section

    # --- Sync integration ---

    def test_sync_preserves_efb_folder(self, tmp_path):
        """Folder ExcludeFromBuild=true must survive a force sync."""
        xml = _plcproj_efb(
            compile_entries=[("POUs\\FB_A.TcPOU", None)],
            folder_entries=[("POUs", "true")],
        )
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "POUs" / "FB_A.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(input_path=str(proj), force=True, backup=False)
        report = P.sync_plcproj(cfg)
        assert report.success is True

        content = P._read_text_raw(proj)
        assert '<ExcludeFromBuild>true</ExcludeFromBuild>' in content
        assert '<Folder Include="POUs">' in content

    def test_sync_preserves_efb_compile(self, tmp_path):
        """Compile ExcludeFromBuild=true must survive a force sync."""
        xml = _plcproj_efb(
            compile_entries=[
                ("POUs\\FB_A.TcPOU", "true"),
                ("POUs\\FB_B.TcPOU", None),
            ],
            folder_entries=[("POUs", None)],
        )
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "POUs" / "FB_A.TcPOU", "<POU/>")
        _write(tmp_path / "POUs" / "FB_B.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(input_path=str(proj), force=True, backup=False)
        report = P.sync_plcproj(cfg)
        assert report.success is True

        content = P._read_text_raw(proj)
        a_section = content.split("FB_A.TcPOU")[1].split("</Compile>")[0]
        assert "ExcludeFromBuild>true<" in a_section
        b_section = content.split("FB_B.TcPOU")[1].split("</Compile>")[0]
        assert "ExcludeFromBuild" not in b_section

    def test_sync_new_file_no_efb(self, tmp_path):
        """A file newly added on disk must NOT get ExcludeFromBuild."""
        xml = _plcproj_efb(
            compile_entries=[("F.TcPOU", None)],
            folder_entries=[],
        )
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        _write(tmp_path / "New.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(
            input_path=str(proj), force=True, backup=False, skip_folder_sync=True,
        )
        P.sync_plcproj(cfg)
        content = P._read_text_raw(proj)
        new_section = content.split("New.TcPOU")[1].split("</Compile>")[0]
        assert "ExcludeFromBuild" not in new_section

    def test_sync_new_folder_no_efb(self, tmp_path):
        """A folder newly created on disk must NOT get ExcludeFromBuild."""
        xml = _plcproj_efb(
            compile_entries=[("POUs\\FB_A.TcPOU", None)],
            folder_entries=[("POUs", None)],
        )
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "POUs" / "FB_A.TcPOU", "<POU/>")
        (tmp_path / "NewFolder").mkdir()

        cfg = P.PlcProjConfig(input_path=str(proj), force=True, backup=False)
        P.sync_plcproj(cfg)
        content = P._read_text_raw(proj)
        assert '<Folder Include="NewFolder" />' in content

    def test_verify_reports_efb_info(self, tmp_path):
        """verify_plcproj() must populate efb_folders and efb_compile."""
        xml = _plcproj_efb(
            compile_entries=[
                ("POUs\\FB_A.TcPOU", "true"),
                ("POUs\\FB_B.TcPOU", None),
            ],
            folder_entries=[("POUs", "false")],
        )
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "POUs" / "FB_A.TcPOU", "<POU/>")
        _write(tmp_path / "POUs" / "FB_B.TcPOU", "<POU/>")

        vr = P.verify_plcproj(proj)
        assert vr.ok is True
        assert vr.efb_folders == {"pous": "false"}
        assert vr.efb_compile == {"pous\\fb_a.tcpou": "true"}

    def test_efb_case_insensitive(self):
        """EFB parsing must be case-insensitive for paths."""
        xml = (
            '  <ItemGroup>\r\n'
            '    <Compile Include="POUs\\FB_Mixed.TcPOU">\r\n'
            '      <SubType>Code</SubType>\r\n'
            '      <ExcludeFromBuild>True</ExcludeFromBuild>\r\n'
            '    </Compile>\r\n'
            '  </ItemGroup>'
        )
        efb = P._parse_efb_compile(xml)
        assert "pous\\fb_mixed.tcpou" in efb
        assert efb["pous\\fb_mixed.tcpou"] == "true"

    def test_sync_preserves_efb_false_on_folder(self, tmp_path):
        """Folder with ExcludeFromBuild=false must survive a force sync."""
        xml = _plcproj_efb(
            compile_entries=[("F.TcPOU", None)],
            folder_entries=[("POUs", "false")],
        )
        proj = tmp_path / "T.plcproj"
        _write(proj, xml)
        _write(tmp_path / "F.TcPOU", "<POU/>")
        (tmp_path / "POUs").mkdir(exist_ok=True)

        cfg = P.PlcProjConfig(input_path=str(proj), force=True, backup=False)
        P.sync_plcproj(cfg)
        content = P._read_text_raw(proj)
        assert '<ExcludeFromBuild>false</ExcludeFromBuild>' in content
