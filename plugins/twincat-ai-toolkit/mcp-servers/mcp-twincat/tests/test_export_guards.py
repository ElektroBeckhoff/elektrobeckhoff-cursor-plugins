"""Unit tests for export guards (0.0.0.0 / non-library / echo)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLC = os.path.join(_ROOT, "plcproj")
for p in (_ROOT, _PLC):
    if p not in sys.path:
        sys.path.insert(0, p)

from export_guards import export_echo_fields, validate_export_target
from twincat_plcproj_ops import read_project_info


NS = "http://schemas.microsoft.com/developer/msbuild/2003"


def _write_plcproj(path: str, *, version: str, category: str, title: str) -> None:
    root = ET.Element("Project", xmlns=NS)
    pg = ET.SubElement(root, "PropertyGroup")
    ET.SubElement(pg, "Title").text = title
    ET.SubElement(pg, "Name").text = title
    ET.SubElement(pg, "ProjectVersion").text = version
    ET.SubElement(pg, "ProjectCategory").text = category
    ET.SubElement(pg, "Company").text = "Test"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


class TestExportGuards(unittest.TestCase):
    def test_reject_zero_version(self):
        info = {
            "title": "Sample",
            "version": "0.0.0.0",
            "is_library_project": False,
            "project_category": "TwinCAT PLC Project",
        }
        err = validate_export_target(
            plcproj_path=r"C:\repo\samples\app.plcproj",
            info=info,
            output_dir=r"C:\repo\Versions\0.0.0.0",
            plcproj_from_bridge=r"C:\repo\samples\app.plcproj",
            plcproj_explicit=False,
            force=False,
        )
        self.assertIsNotNone(err)
        self.assertEqual(err["error_code"], "plcproj_ambiguous")
        self.assertEqual(err["project_version"], "0.0.0.0")

    def test_reject_explicit_zero_without_force(self):
        info = {
            "title": "Sample",
            "version": "0.0.0.0",
            "is_library_project": False,
            "project_category": "TwinCAT PLC Project",
        }
        err = validate_export_target(
            plcproj_path=r"C:\repo\lib.plcproj",
            info=info,
            output_dir=r"C:\repo\Versions\0.0.0.0",
            plcproj_explicit=True,
            force=False,
        )
        self.assertIsNotNone(err)
        self.assertEqual(err["error_code"], "export_invalid_project")

    def test_force_allows_zero(self):
        info = {
            "title": "Sample",
            "version": "0.0.0.0",
            "is_library_project": False,
            "project_category": "TwinCAT PLC Project",
        }
        err = validate_export_target(
            plcproj_path=r"C:\repo\lib.plcproj",
            info=info,
            output_dir=r"C:\repo\Versions\0.0.0.0",
            plcproj_explicit=True,
            force=True,
        )
        self.assertIsNone(err)

    def test_reject_non_library(self):
        info = {
            "title": "App",
            "version": "1.2.3.4",
            "is_library_project": False,
            "project_category": "TwinCAT PLC Project",
        }
        err = validate_export_target(
            plcproj_path=r"C:\repo\app.plcproj",
            info=info,
            output_dir=r"C:\repo\Versions\1.2.3.4",
            plcproj_explicit=True,
            force=False,
        )
        self.assertIsNotNone(err)
        self.assertEqual(err["error_code"], "export_invalid_project")

    def test_library_ok(self):
        info = {
            "title": "Tc3_EB_BA",
            "version": "1.6.1.0",
            "is_library_project": True,
            "project_category": "TwinCAT PLC Library Project",
        }
        err = validate_export_target(
            plcproj_path=r"C:\repo\Tc3_EB_BA.plcproj",
            info=info,
            output_dir=r"C:\repo\Versions\1.6.1.0",
            plcproj_explicit=True,
            force=False,
        )
        self.assertIsNone(err)
        echo = export_echo_fields(
            plcproj_path=r"C:\repo\Tc3_EB_BA.plcproj",
            info=info,
            output_dir=r"C:\repo\Versions\1.6.1.0",
        )
        self.assertEqual(echo["project_version"], "1.6.1.0")
        self.assertTrue(echo["is_library_project"])

    def test_read_project_info_library_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "Lib.plcproj")
            _write_plcproj(
                p,
                version="1.0.0.0",
                category="TwinCAT PLC Library Project",
                title="Lib",
            )
            info = read_project_info(p)
            self.assertTrue(info["is_library_project"])
            self.assertEqual(info["version"], "1.0.0.0")


if __name__ == "__main__":
    unittest.main()
