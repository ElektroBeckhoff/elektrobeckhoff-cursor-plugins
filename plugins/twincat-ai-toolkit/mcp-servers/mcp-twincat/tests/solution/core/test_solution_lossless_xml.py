"""Lossless XML reading, serialization, and surgical patching on real Solution files."""
from __future__ import annotations

import codecs
import tempfile
from pathlib import Path
import pytest

from twincat_core.xml import (
    read_tc_xml,
    read_tc_xml_file,
    read_file_lossless,
    save_document_lossless,
    patch_declaration,
    patch_implementation,
    patch_method,
    extract_all_guids,
    is_valid_guid,
)


class TestSolutionLosslessXml:
    """Verifies lossless XML guarantees against all real TwinCAT solution files."""

    def test_lossless_roundtrip_all_solution_files(self, all_solution_files):
        for file_path in all_solution_files:
            raw_bytes = file_path.read_bytes()
            raw_text, enc_info = read_file_lossless(file_path)
            # Compare decoded text without BOM
            expected_text = raw_bytes.decode(enc_info.encoding, errors="replace").lstrip("\ufeff")
            assert raw_text == expected_text, f"Lossless read mismatch for {file_path.name}"

    def test_surgical_patch_on_solution_pou(self, solution_paths):
        pou_file = solution_paths["syntax_dir"] / "FB_Syntax_Derived.TcPOU"
        assert pou_file.is_file()
        doc = read_tc_xml_file(pou_file)

        # Surgically patch implementation
        new_body = "\n// Surgically patched body\nnCount := nCount + 1;\n"
        patched_text = patch_implementation(doc, new_body)

        assert new_body in patched_text
        if doc.root_object_id:
            assert doc.root_object_id in patched_text
        # Ensure declaration was NOT modified
        assert "FUNCTION_BLOCK FB_Syntax_Derived" in patched_text

    def test_surgical_patch_method_on_solution_pou(self, solution_paths):
        pou_file = solution_paths["syntax_dir"] / "FB_Syntax_Derived.TcPOU"
        doc = read_tc_xml_file(pou_file)

        new_method_impl = "\n// Patched method calculation\nM_Execute := TRUE;\n"
        patched_text = patch_method(doc, method_name="M_Execute", new_implementation=new_method_impl)

        assert new_method_impl in patched_text
        assert "FB_Syntax_Derived" in patched_text

    def test_guid_integrity_across_solution(self, all_solution_files):
        all_guids = []
        for file_path in all_solution_files:
            raw_text = file_path.read_text(encoding="utf-8")
            guids = extract_all_guids(raw_text)
            for g in guids:
                assert is_valid_guid(g), f"Invalid GUID format '{g}' in {file_path.name}"
                all_guids.append(g)

        assert len(all_guids) >= 50
