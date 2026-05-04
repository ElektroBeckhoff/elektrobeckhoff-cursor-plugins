"""
Comprehensive pytest suite for twincat_plcproj_ops.py

Uses synthetic .plcproj XML + temporary file trees -- no external projects.
Run with:  pytest test_plcproj_ops_pytest.py -v
"""
import os
import re
import textwrap
import uuid
from pathlib import Path

import pytest

import twincat_plcproj_ops as P


# ===================================================================
# Synthetic plcproj XML
# ===================================================================

MINIMAL_PLCPROJ = (
    '<?xml version="1.0" encoding="utf-8"?>\r\n'
    '<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">\r\n'
    '  <PropertyGroup>\r\n'
    '    <Name>TestLib</Name>\r\n'
    '    <ProjectVersion>1.0.0.0</ProjectVersion>\r\n'
    '  </PropertyGroup>\r\n'
    '  <ItemGroup>\r\n'
    '    <Compile Include="DUTs\\ST_Data.TcDUT">\r\n'
    '      <SubType>Code</SubType>\r\n'
    '    </Compile>\r\n'
    '    <Compile Include="POUs\\FB_Main.TcPOU">\r\n'
    '      <SubType>Code</SubType>\r\n'
    '    </Compile>\r\n'
    '  </ItemGroup>\r\n'
    '  <ItemGroup>\r\n'
    '    <Folder Include="DUTs" />\r\n'
    '    <Folder Include="POUs" />\r\n'
    '  </ItemGroup>\r\n'
    '</Project>\r\n'
)

MINIMAL_TCPOU = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <TcPlcObject Version="1.1.0.1">
      <POU Name="FB_Main" Id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}">
        <Declaration><![CDATA[FUNCTION_BLOCK FB_Main]]></Declaration>
        <Implementation>
          <ST><![CDATA[;]]></ST>
        </Implementation>
      </POU>
    </TcPlcObject>
""")


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


def _write(path: Path, content: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _make_project(tmp_dir: Path, plcproj_xml: str = MINIMAL_PLCPROJ) -> Path:
    """Create a minimal project directory matching the default MINIMAL_PLCPROJ."""
    proj = tmp_dir / "TestLib.plcproj"
    _write(proj, plcproj_xml)
    _write(tmp_dir / "POUs" / "FB_Main.TcPOU", MINIMAL_TCPOU)
    _write(tmp_dir / "DUTs" / "ST_Data.TcDUT", "<TcPlcObject/>")
    return proj


# ===================================================================
# TestResolve
# ===================================================================

class TestResolve:
    def test_explicit_path(self, tmp_dir):
        proj = tmp_dir / "My.plcproj"
        _write(proj, "<Project/>")
        result = P.resolve_plcproj_path(plcproj_path=str(proj))
        assert result == proj.resolve()

    def test_project_root_single(self, tmp_dir):
        proj = tmp_dir / "Lib.plcproj"
        _write(proj, "<Project/>")
        result = P.resolve_plcproj_path(project_root=str(tmp_dir))
        assert result == proj.resolve()

    def test_project_root_multiple_raises(self, tmp_dir):
        _write(tmp_dir / "A.plcproj", "<Project/>")
        _write(tmp_dir / "B.plcproj", "<Project/>")
        with pytest.raises(ValueError, match="Multiple"):
            P.resolve_plcproj_path(project_root=str(tmp_dir))

    def test_project_root_none_raises(self, tmp_dir):
        with pytest.raises(FileNotFoundError, match="No .plcproj"):
            P.resolve_plcproj_path(project_root=str(tmp_dir))

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            P.resolve_plcproj_path(plcproj_path="nonexistent.plcproj")

    def test_no_args_raises(self):
        with pytest.raises(ValueError, match="Specify"):
            P.resolve_plcproj_path()


# ===================================================================
# TestDiskScan
# ===================================================================

class TestDiskScan:
    def test_finds_tc_files(self, tmp_dir):
        proj = _make_project(tmp_dir)
        state = P.scan_disk_state(proj)
        names = [os.path.basename(p) for p in state.ordered]
        assert "FB_Main.TcPOU" in names
        assert "ST_Data.TcDUT" in names

    def test_excludes_compileinfo(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "_CompileInfo" / "hidden.TcPOU", "<POU/>")
        state = P.scan_disk_state(proj)
        all_names = [os.path.basename(p) for p in state.ordered]
        assert "hidden.TcPOU" not in all_names

    def test_excludes_libraries(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "_Libraries" / "lib.TcPOU", "<POU/>")
        state = P.scan_disk_state(proj)
        all_names = [os.path.basename(p) for p in state.ordered]
        assert "lib.TcPOU" not in all_names

    def test_excludes_git(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / ".git" / "obj.TcPOU", "<POU/>")
        state = P.scan_disk_state(proj)
        all_names = [os.path.basename(p) for p in state.ordered]
        assert "obj.TcPOU" not in all_names

    def test_plctask_sorted_first(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "PlcTask.TcTTO", "<Task/>")
        state = P.scan_disk_state(proj)
        assert state.ordered[0].endswith("PlcTask.TcTTO")

    def test_folder_set(self, tmp_dir):
        proj = _make_project(tmp_dir)
        state = P.scan_disk_state(proj, skip_folder_sync=False)
        folder_names = {os.path.basename(f) for f in state.folder_set}
        assert "POUs" in folder_names
        assert "DUTs" in folder_names

    def test_skip_folder_sync(self, tmp_dir):
        proj = _make_project(tmp_dir)
        state = P.scan_disk_state(proj, skip_folder_sync=True)
        assert len(state.folder_set) == 0

    def test_custom_extensions(self, tmp_dir):
        proj = tmp_dir / "T.plcproj"
        _write(proj, MINIMAL_PLCPROJ)
        _write(tmp_dir / "F.TcPOU", "<POU/>")
        _write(tmp_dir / "G.TcGVL", "<GVL/>")
        state = P.scan_disk_state(proj, extensions={".tcpou"})
        names = [os.path.basename(p) for p in state.ordered]
        assert "F.TcPOU" in names
        assert "G.TcGVL" not in names


# ===================================================================
# TestCompileBlock
# ===================================================================

class TestCompileBlock:
    def test_basic_output(self):
        block = P.build_compile_block(["POUs\\FB_Main.TcPOU"])
        assert '<Compile Include="POUs\\FB_Main.TcPOU">' in block
        assert "<SubType>Code</SubType>" in block
        assert block.startswith("  <ItemGroup>")
        assert block.endswith("  </ItemGroup>")

    def test_multiple_entries(self):
        block = P.build_compile_block(["A.TcPOU", "B.TcDUT", "C.TcGVL"])
        assert block.count("<Compile Include=") == 3

    def test_empty_list(self):
        block = P.build_compile_block([])
        assert "<Compile" not in block
        assert "<ItemGroup>" in block


# ===================================================================
# TestFolderBlock
# ===================================================================

class TestFolderBlock:
    def test_basic_output(self):
        block = P.build_folder_block({"POUs", "DUTs"})
        assert '<Folder Include="DUTs" />' in block
        assert '<Folder Include="POUs" />' in block

    def test_sorted_output(self):
        block = P.build_folder_block({"Zebra", "Alpha", "Middle"})
        alpha_pos = block.index("Alpha")
        middle_pos = block.index("Middle")
        zebra_pos = block.index("Zebra")
        assert alpha_pos < middle_pos < zebra_pos

    def test_empty_set(self):
        block = P.build_folder_block(set())
        assert "<Folder" not in block


# ===================================================================
# TestVerify
# ===================================================================

class TestVerify:
    def test_matching_project(self, tmp_dir):
        proj = _make_project(tmp_dir)
        vr = P.verify_plcproj(proj)
        assert vr.ok is True
        assert vr.exit_code == 0

    def test_missing_compile(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")
        vr = P.verify_plcproj(proj)
        assert vr.ok is False
        names = [os.path.basename(p) for p in vr.missing_compile]
        assert "FB_New.TcPOU" in names

    def test_extra_compile(self, tmp_dir):
        proj = _make_project(tmp_dir)
        (tmp_dir / "DUTs" / "ST_Data.TcDUT").unlink()
        vr = P.verify_plcproj(proj)
        assert vr.ok is False
        names = [os.path.basename(p) for p in vr.extra_compile]
        assert "ST_Data.TcDUT" in names

    def test_missing_folder(self, tmp_dir):
        proj = _make_project(tmp_dir)
        (tmp_dir / "GVLs").mkdir()
        vr = P.verify_plcproj(proj)
        assert vr.ok is False
        folder_names = [os.path.basename(p) for p in vr.folder_missing]
        assert "GVLs" in folder_names

    def test_extra_folder(self, tmp_dir):
        proj = _make_project(tmp_dir)
        plcproj_with_extra = MINIMAL_PLCPROJ.replace(
            '    <Folder Include="DUTs" />',
            '    <Folder Include="DUTs" />\r\n    <Folder Include="OldFolder" />',
        )
        proj.write_text(plcproj_with_extra, encoding="utf-8")
        vr = P.verify_plcproj(proj)
        assert vr.ok is False
        folder_names = [os.path.basename(p) for p in vr.folder_extra]
        assert "OldFolder" in folder_names

    def test_no_compile_block_returns_error(self, tmp_dir):
        proj = tmp_dir / "T.plcproj"
        _write(proj, '<?xml version="1.0"?>\n<Project/>')
        _write(tmp_dir / "F.TcPOU", "<POU/>")
        vr = P.verify_plcproj(proj)
        assert vr.ok is False
        assert vr.exit_code == 2
        assert "Compile ItemGroup" in vr.error_message

    def test_skip_folder_sync_ignores_folders(self, tmp_dir):
        proj = _make_project(tmp_dir)
        (tmp_dir / "NewDir").mkdir()
        vr = P.verify_plcproj(proj, skip_folder_sync=True)
        assert vr.ok is True


# ===================================================================
# TestXmlReplace
# ===================================================================

class TestXmlReplace:
    def test_compile_replaced(self):
        new_block = P.build_compile_block(["X.TcPOU"])
        result = P.replace_xml_blocks(MINIMAL_PLCPROJ, new_block, "", skip_folder_sync=True)
        assert '<Compile Include="X.TcPOU">' in result
        assert '<Compile Include="POUs\\\\FB_Main.TcPOU">' not in result

    def test_folder_replaced(self):
        compile_block = P.build_compile_block(["POUs\\FB_Main.TcPOU", "DUTs\\ST_Data.TcDUT"])
        folder_block = P.build_folder_block({"POUs", "DUTs", "NewFolder"})
        result = P.replace_xml_blocks(MINIMAL_PLCPROJ, compile_block, folder_block)
        assert '<Folder Include="NewFolder" />' in result


# ===================================================================
# TestSync
# ===================================================================

class TestSync:
    def test_sync_force_writes(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(input_path=str(tmp_dir), force=True)
        report = P.sync_plcproj(cfg)
        assert report.success is True
        assert report.plcproj_written is True

        content = proj.read_text(encoding="utf-8")
        assert "FB_New.TcPOU" in content

    def test_sync_no_force_drift_fails(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(input_path=str(tmp_dir))
        report = P.sync_plcproj(cfg)
        assert report.success is False

    def test_sync_no_force_matching_ok(self, tmp_dir):
        proj = _make_project(tmp_dir)
        cfg = P.PlcProjConfig(input_path=str(tmp_dir))
        report = P.sync_plcproj(cfg)
        assert report.success is True

    def test_sync_dry_run_no_write(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")
        orig = proj.read_text(encoding="utf-8")

        cfg = P.PlcProjConfig(input_path=str(tmp_dir), force=True, dry_run=True)
        report = P.sync_plcproj(cfg)
        assert report.success is True
        assert report.plcproj_written is False
        assert proj.read_text(encoding="utf-8") == orig

    def test_sync_unchanged_skips_write(self, tmp_dir):
        proj = _make_project(tmp_dir)
        cfg = P.PlcProjConfig(input_path=str(tmp_dir), force=True)
        report = P.sync_plcproj(cfg)
        assert report.success is True
        assert report.plcproj_unchanged is True
        assert report.plcproj_written is False

    def test_sync_backup_created(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(input_path=str(tmp_dir), force=True, backup=True)
        P.sync_plcproj(cfg)
        baks = list(tmp_dir.glob("*.plcproj.bak"))
        assert len(baks) == 1

    def test_sync_no_backup(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(input_path=str(tmp_dir), force=True, backup=False)
        P.sync_plcproj(cfg)
        baks = list(tmp_dir.glob("*.plcproj.bak"))
        assert len(baks) == 0

    def test_sync_with_plcproj_path(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")

        cfg = P.PlcProjConfig(input_path=str(proj), force=True)
        report = P.sync_plcproj(cfg)
        assert report.success is True
        assert report.plcproj_written is True

    def test_sync_counts(self, tmp_dir):
        proj = _make_project(tmp_dir)
        cfg = P.PlcProjConfig(input_path=str(tmp_dir), force=True)
        report = P.sync_plcproj(cfg)
        assert report.compile_count == 2
        assert report.folder_count == 2

    def test_sync_ensure_guids(self, tmp_dir):
        proj = _make_project(tmp_dir)
        no_id = textwrap.dedent("""\
            <?xml version="1.0" encoding="utf-8"?>
            <TcPlcObject Version="1.1.0.1">
              <POU Name="FB_NoId">
                <Declaration><![CDATA[FUNCTION_BLOCK FB_NoId]]></Declaration>
              </POU>
            </TcPlcObject>
        """)
        _write(tmp_dir / "POUs" / "FB_Main.TcPOU", no_id)

        cfg = P.PlcProjConfig(input_path=str(tmp_dir), force=True, ensure_object_guids=True)
        report = P.sync_plcproj(cfg)
        assert report.success is True
        assert len(report.guids_repaired) >= 1
        repaired_names = [r.file_name for r in report.guids_repaired]
        assert "FB_Main.TcPOU" in repaired_names


# ===================================================================
# TestGuidRepair
# ===================================================================

class TestGuidRepair:
    def test_missing_guid_added(self, tmp_dir):
        content = '<TcPlcObject><POU Name="FB_Test"></POU></TcPlcObject>'
        _write(tmp_dir / "FB_Test.TcPOU", content)
        repairs = P.repair_object_guids(str(tmp_dir))
        assert len(repairs) == 1
        assert repairs[0].reason == "missing"
        updated = (tmp_dir / "FB_Test.TcPOU").read_text()
        assert 'Id="{' in updated

    def test_valid_guid_untouched(self, tmp_dir):
        g = str(uuid.uuid4())
        content = f'<TcPlcObject><POU Name="FB_Ok" Id="{{{g}}}"></POU></TcPlcObject>'
        _write(tmp_dir / "FB_Ok.TcPOU", content)
        repairs = P.repair_object_guids(str(tmp_dir))
        assert len(repairs) == 0

    def test_invalid_guid_replaced(self, tmp_dir):
        content = '<TcPlcObject><POU Name="FB_Bad" Id="not-a-guid"></POU></TcPlcObject>'
        _write(tmp_dir / "FB_Bad.TcPOU", content)
        repairs = P.repair_object_guids(str(tmp_dir))
        assert len(repairs) == 1
        assert repairs[0].reason == "invalid"

    def test_duplicate_guid_fixed(self, tmp_dir):
        g = str(uuid.uuid4())
        for name in ("A.TcPOU", "B.TcPOU"):
            content = f'<TcPlcObject><POU Name="{name}" Id="{{{g}}}"></POU></TcPlcObject>'
            _write(tmp_dir / name, content)
        repairs = P.repair_object_guids(str(tmp_dir))
        assert any(r.reason == "duplicate_across_files" for r in repairs)

        id_a = re.search(r'Id="([^"]+)"', (tmp_dir / "A.TcPOU").read_text()).group(1)
        id_b = re.search(r'Id="([^"]+)"', (tmp_dir / "B.TcPOU").read_text()).group(1)
        assert id_a != id_b

    def test_multi_id_attrs(self, tmp_dir):
        g = str(uuid.uuid4())
        content = f'<TcPlcObject><POU Name="FB_Multi" Id="{{{g}}}" Id="{{{g}}}"></POU></TcPlcObject>'
        _write(tmp_dir / "FB_Multi.TcPOU", content)
        repairs = P.repair_object_guids(str(tmp_dir))
        assert len(repairs) == 1
        assert repairs[0].reason == "multi_attr"

    def test_dry_run_no_write(self, tmp_dir):
        content = '<TcPlcObject><POU Name="FB_Dry"></POU></TcPlcObject>'
        _write(tmp_dir / "FB_Dry.TcPOU", content)
        orig = (tmp_dir / "FB_Dry.TcPOU").read_text()
        repairs = P.repair_object_guids(str(tmp_dir), dry_run=True)
        assert len(repairs) == 1
        assert (tmp_dir / "FB_Dry.TcPOU").read_text() == orig

    def test_gvl_supported(self, tmp_dir):
        content = '<TcPlcObject><GVL Name="GVL_Test"></GVL></TcPlcObject>'
        _write(tmp_dir / "GVL_Test.TcGVL", content)
        repairs = P.repair_object_guids(str(tmp_dir))
        assert len(repairs) == 1

    def test_dut_supported(self, tmp_dir):
        content = '<TcPlcObject><DUT Name="DUT_Test"></DUT></TcPlcObject>'
        _write(tmp_dir / "DUT_Test.TcDUT", content)
        repairs = P.repair_object_guids(str(tmp_dir))
        assert len(repairs) == 1

    def test_itf_supported(self, tmp_dir):
        content = '<TcPlcObject><Itf Name="I_Test"></Itf></TcPlcObject>'
        _write(tmp_dir / "I_Test.TcPOU", content)
        repairs = P.repair_object_guids(str(tmp_dir))
        assert len(repairs) == 1

    def test_excludes_compileinfo(self, tmp_dir):
        content = '<TcPlcObject><POU Name="FB_Hidden"></POU></TcPlcObject>'
        _write(tmp_dir / "_CompileInfo" / "FB_Hidden.TcPOU", content)
        repairs = P.repair_object_guids(str(tmp_dir))
        assert len(repairs) == 0


# ===================================================================
# TestCLI
# ===================================================================

class TestCLI:
    def test_minimal_args(self):
        cfg = P.parse_arguments(["--input", "test.plcproj"])
        assert cfg.input_path == "test.plcproj"
        assert cfg.force is False
        assert cfg.dry_run is False
        assert cfg.backup is True
        assert cfg.verify_only is False

    def test_verify_only(self):
        cfg = P.parse_arguments(["--input", "x", "--verify-only"])
        assert cfg.verify_only is True

    def test_force(self):
        cfg = P.parse_arguments(["--input", "x", "--force"])
        assert cfg.force is True

    def test_dry_run(self):
        cfg = P.parse_arguments(["--input", "x", "--dry-run"])
        assert cfg.dry_run is True

    def test_no_backup(self):
        cfg = P.parse_arguments(["--input", "x", "--no-backup"])
        assert cfg.backup is False

    def test_skip_folder_sync(self):
        cfg = P.parse_arguments(["--input", "x", "--skip-folder-sync"])
        assert cfg.skip_folder_sync is True

    def test_ensure_object_guids(self):
        cfg = P.parse_arguments(["--input", "x", "--ensure-object-guids"])
        assert cfg.ensure_object_guids is True

    def test_custom_extensions(self):
        cfg = P.parse_arguments(["--input", "x", "--compile-extensions", ".TcPOU", ".TcDUT"])
        assert ".tcpou" in cfg.compile_extensions
        assert ".tcdut" in cfg.compile_extensions
        assert ".tcgvl" not in cfg.compile_extensions

    def test_log_level(self):
        cfg = P.parse_arguments(["--input", "x", "--log-level", "DEBUG"])
        assert cfg.log_level == "DEBUG"


# ===================================================================
# TestMain
# ===================================================================

class TestMain:
    def test_main_verify_ok(self, tmp_dir):
        proj = _make_project(tmp_dir)
        code = P.main(["--input", str(tmp_dir), "--verify-only"])
        assert code == 0

    def test_main_verify_drift(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")
        code = P.main(["--input", str(tmp_dir), "--verify-only"])
        assert code != 0

    def test_main_sync_force(self, tmp_dir):
        proj = _make_project(tmp_dir)
        _write(tmp_dir / "POUs" / "FB_New.TcPOU", "<POU/>")
        code = P.main(["--input", str(tmp_dir), "--force"])
        assert code == 0

    def test_main_sync_dry_run(self, tmp_dir):
        proj = _make_project(tmp_dir)
        code = P.main(["--input", str(tmp_dir), "--dry-run", "--force"])
        assert code == 0

    def test_main_nonexistent_fails(self):
        code = P.main(["--input", "nonexistent_path_xyz"])
        assert code != 0


# ===================================================================
# TestIsExcludedDir
# ===================================================================

class TestIsExcludedDir:
    def test_compileinfo(self):
        assert P._is_excluded_dir("_CompileInfo") is True
        assert P._is_excluded_dir("_CompileInfo\\sub") is True

    def test_libraries(self):
        assert P._is_excluded_dir("_Libraries") is True

    def test_git(self):
        assert P._is_excluded_dir(".git") is True

    def test_bin(self):
        assert P._is_excluded_dir("bin") is True

    def test_obj(self):
        assert P._is_excluded_dir("obj") is True

    def test_normal_dir(self):
        assert P._is_excluded_dir("POUs") is False
        assert P._is_excluded_dir("DUTs") is False
        assert P._is_excluded_dir("GVLs") is False

    def test_empty(self):
        assert P._is_excluded_dir("") is False

    def test_nested_normal(self):
        assert P._is_excluded_dir("POUs\\SubDir") is False
