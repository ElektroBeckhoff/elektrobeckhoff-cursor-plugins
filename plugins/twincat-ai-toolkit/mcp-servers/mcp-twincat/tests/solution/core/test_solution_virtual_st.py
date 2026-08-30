"""Virtual ST projection and bidirectional source mapping tests on the real Solution."""
from __future__ import annotations

from pathlib import Path
import pytest

from twincat_core.projection.virtual_st import project_to_virtual_st, sync_virtual_st_to_xml, VirtualStDocument
from twincat_core.projection.source_map import SourceMap


class TestSolutionVirtualSt:
    """Verifies Virtual ST projection on real solution files."""

    def test_project_all_solution_pous(self, all_solution_files):
        pou_files = [f for f in all_solution_files if f.suffix.lower() == ".tcpou"]
        assert len(pou_files) >= 20

        for file_path in pou_files:
            raw_text = file_path.read_text(encoding="utf-8")
            virt_doc = project_to_virtual_st(raw_text, file_path=file_path)
            assert isinstance(virt_doc, VirtualStDocument)
            assert len(virt_doc.virtual_st) > 0
            assert isinstance(virt_doc.source_map, SourceMap)
            assert len(virt_doc.source_map.sections) >= 1

    def test_bidirectional_coordinate_mapping(self, solution_paths):
        pou_file = solution_paths["syntax_dir"] / "FB_Syntax_Derived.TcPOU"
        raw_text = pou_file.read_text(encoding="utf-8")
        virt_doc = project_to_virtual_st(raw_text, file_path=pou_file)
        source_map = virt_doc.source_map

        # Pick first section
        sec = source_map.sections[0]
        # Map XML position to Virtual ST position
        virt_pos = source_map.xml_to_virtual_position(sec.xml_content_start_line, 1)
        assert virt_pos is not None
        # Map Virtual ST position back to XML
        xml_pos = source_map.virtual_to_xml_position(virt_pos[0], virt_pos[1])
        assert xml_pos is not None
        assert xml_pos[0] == sec.xml_content_start_line

    def test_apply_virtual_st_changes_roundtrip(self, solution_paths):
        pou_file = solution_paths["syntax_dir"] / "FB_Syntax_Derived.TcPOU"
        raw_text = pou_file.read_text(encoding="utf-8")
        virt_doc = project_to_virtual_st(raw_text, file_path=pou_file)

        # Applying unchanged virtual ST should yield valid XML content
        synced_xml = sync_virtual_st_to_xml(raw_text, virt_doc.virtual_st, file_path=pou_file)
        assert len(synced_xml) > 0
        assert "FB_Syntax_Derived" in synced_xml
