import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from server import (
    _clean_path,
    _resolve_directory,
    _resolve_path,
    _resolve_plcproj_path,
    _scan_plcproj_in_dir,
    twincat_check_syntax,
    twincat_open,
)
from formatter.file_processor import discover_files, discover_project_files
from automation_interface.stweep_ops import StweepOpsMixin
from plcproj.twincat_plcproj_ops import resolve_plcproj_path as ops_resolve_plcproj_path


class TestPathCleaningAndSanitization(unittest.TestCase):
    def test_clean_path_strips_quotes_and_whitespace(self):
        self.assertEqual(_clean_path('  "C:\\Path\\To\\File.sln"  '), "C:\\Path\\To\\File.sln")
        self.assertEqual(_clean_path("  'C:\\Path\\To\\File.sln'  "), "C:\\Path\\To\\File.sln")
        self.assertEqual(_clean_path(""), "")
        self.assertEqual(_clean_path(None), "")


class TestMultiProjectSlnOpening(unittest.TestCase):
    def test_multi_project_sln_auto_selects_primary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sln_file = os.path.join(tmpdir, "MyLib.sln")
            with open(sln_file, "w") as f:
                f.write("Microsoft Visual Studio Solution File")

            fake_resolved = {
                "success": False,
                "error": "multiple_plc_projects",
                "available_projects": [
                    {"name": "MyLib_Sample", "plcproj_path": os.path.join(tmpdir, "Sample", "MyLib_Sample.plcproj")},
                    {"name": "MyLib", "plcproj_path": os.path.join(tmpdir, "MyLib", "MyLib.plcproj")},
                ],
            }

            fake_bridge = MagicMock()
            fake_bridge.open_solution.return_value = {"success": True, "opened": True}

            with patch("server._get_bridge", return_value=fake_bridge):
                with patch("server._resolve_path", return_value=fake_resolved):
                    with patch("server._read_proj_name", return_value="MyLib"):
                        res_str = twincat_open(path=sln_file)
                        self.assertIn('"success": true', res_str.lower())
                        fake_bridge.open_solution.assert_called_once()
                        call_kwargs = fake_bridge.open_solution.call_args.kwargs
                        self.assertEqual(os.path.normcase(call_kwargs["plcproj_path"]), os.path.normcase(os.path.join(tmpdir, "MyLib", "MyLib.plcproj")))


class TestSingleFileSyntaxUpwardSearch(unittest.TestCase):
    def test_deeply_nested_file_finds_top_plcproj(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proj_dir = os.path.join(tmpdir, "MyPlc")
            os.makedirs(proj_dir, exist_ok=True)
            plcproj = os.path.join(proj_dir, "MyPlc.plcproj")
            with open(plcproj, "w") as f:
                f.write("<Project></Project>")

            deep_dir = os.path.join(proj_dir, "POUs", "Level1", "Level2", "Level3")
            os.makedirs(deep_dir, exist_ok=True)
            pou_file = os.path.join(deep_dir, "FB_Motor.TcPOU")
            with open(pou_file, "w") as f:
                f.write("""<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Motor" Id="{12345678-1234-1234-1234-1234567890ab}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Motor
VAR
    bEnable : BOOL;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>""")

            res_str = twincat_check_syntax(path=f'"{pou_file}"')
            self.assertIn('"success": true', res_str.lower())


class TestPlcprojOpsRecursiveDiscovery(unittest.TestCase):
    def test_recursive_discovery_in_project_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sub = os.path.join(tmpdir, "SubDir", "Deep")
            os.makedirs(sub, exist_ok=True)
            plc = os.path.join(sub, "Target.plcproj")
            with open(plc, "w") as f:
                f.write("<Project></Project>")

            resolved = ops_resolve_plcproj_path(project_root=tmpdir)
            self.assertEqual(resolved, Path(plc).resolve())


class TestExcludeFilteringInWalks(unittest.TestCase):
    def test_formatter_and_stweep_ignore_git_and_versions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = os.path.join(tmpdir, "POUs")
            git_dir = os.path.join(tmpdir, ".git", "POUs")
            ver_dir = os.path.join(tmpdir, "Versions", "1.0.0", "POUs")
            os.makedirs(src_dir, exist_ok=True)
            os.makedirs(git_dir, exist_ok=True)
            os.makedirs(ver_dir, exist_ok=True)

            valid_pou = os.path.join(src_dir, "FB_Main.TcPOU")
            git_pou = os.path.join(git_dir, "FB_Git.TcPOU")
            ver_pou = os.path.join(ver_dir, "FB_Ver.TcPOU")

            for f in (valid_pou, git_pou, ver_pou):
                with open(f, "w") as fp:
                    fp.write("<TcPlcObject></TcPlcObject>")

            found = discover_files([tmpdir])
            self.assertEqual(len(found), 1)
            self.assertEqual(Path(found[0]).resolve(), Path(valid_pou).resolve())

            stweep_found = StweepOpsMixin._collect_formattable_files(tmpdir, recursive=True)
            self.assertEqual(len(stweep_found), 1)
            self.assertEqual(Path(stweep_found[0]).resolve(), Path(valid_pou).resolve())


if __name__ == "__main__":
    unittest.main()
