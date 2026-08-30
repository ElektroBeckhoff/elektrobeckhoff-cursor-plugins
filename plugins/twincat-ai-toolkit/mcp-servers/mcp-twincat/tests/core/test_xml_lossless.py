"""Lossless reading and surgical patching tests for twincat_core.xml."""
from __future__ import annotations

import codecs
from pathlib import Path

import pytest
from twincat_core.xml import (
    CdataKind,
    CdataSpan,
    TcXmlDocument,
    XmlEncodingInfo,
    detect_encoding_info,
    encode_document,
    extract_all_guids,
    find_duplicate_guids,
    generate_guid,
    is_fake_ai_guid,
    is_valid_guid,
    normalize_guid,
    patch_action,
    patch_by_filter,
    patch_cdata_span,
    patch_cdata_spans,
    patch_declaration,
    patch_implementation,
    patch_method,
    read_file_lossless,
    read_tc_xml,
    read_tc_xml_file,
    save_document_lossless,
    scan_cdata_spans,
    write_file_safe,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "formatter" / "fixtures" / "golden"


def _get_golden_fixture_files() -> list[Path]:
    """Collect all golden fixture files."""
    if not FIXTURES_DIR.exists():
        return []
    return sorted(
        [p for p in FIXTURES_DIR.rglob("*") if p.suffix.lower() in (".tcpou", ".tcdut", ".tcgvl", ".tcio")],
        key=lambda p: str(p),
    )


# ===========================================================================
# 1. Byte-for-Byte Golden Fixtures Roundtrip Test
# ===========================================================================

class TestLosslessGoldenRoundtrip:
    """Verifies that reading any fixture and re-encoding without changes produces 100% byte match."""

    @pytest.mark.parametrize("fixture_path", _get_golden_fixture_files(), ids=lambda p: p.name)
    def test_fixture_byte_exact_roundtrip(self, fixture_path: Path):
        orig_bytes = fixture_path.read_bytes()
        doc = read_tc_xml_file(fixture_path)

        assert doc.raw_text, f"Failed to read raw text from {fixture_path.name}"
        assert doc.root_object_name, f"Missing root object name in {fixture_path.name}"

        encoded = encode_document(doc.raw_text, doc.encoding_info)
        assert encoded == orig_bytes, f"Byte mismatch on roundtrip for {fixture_path.name}"


# ===========================================================================
# 2. CDATA Span Discovery & Classification Tests
# ===========================================================================

class TestCdataSpanDiscovery:
    """Tests proper detection and typing of CDATA spans in various TwinCAT structures."""

    def test_pou_with_methods_and_properties(self):
        xml_sample = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="FB_Test" Id="{11111111-2222-3333-4444-555555555555}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test
VAR
    _nCounter : INT;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[_nCounter := _nCounter + 1;]]></ST>
    </Implementation>
    <Method Name="M_Init" Id="{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}">
      <Declaration><![CDATA[METHOD M_Init : BOOL]]></Declaration>
      <Implementation>
        <ST><![CDATA[M_Init := TRUE;]]></ST>
      </Implementation>
    </Method>
    <Property Name="P_Val" Id="{ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee}">
      <Declaration><![CDATA[PROPERTY P_Val : INT]]></Declaration>
      <Get Name="Get" Id="{00000000-bbbb-cccc-dddd-eeeeeeeeeeee}">
        <Declaration><![CDATA[VAR END_VAR]]></Declaration>
        <Implementation>
          <ST><![CDATA[P_Val := _nCounter;]]></ST>
        </Implementation>
      </Get>
    </Property>
    <Action Name="A_Reset" Id="{12345678-bbbb-cccc-dddd-eeeeeeeeeeee}">
      <Implementation>
        <ST><![CDATA[_nCounter := 0;]]></ST>
      </Implementation>
    </Action>
  </POU>
</TcPlcObject>"""
        doc = read_tc_xml(xml_sample)

        assert doc.root_object_type == "POU"
        assert doc.root_object_name == "FB_Test"
        assert doc.root_object_id == "{11111111-2222-3333-4444-555555555555}"
        assert doc.product_version == "3.1.4024.16"

        # Check CDATA spans
        spans = doc.cdata_spans
        assert len(spans) == 8

        decl_span = doc.get_declaration_span()
        assert decl_span is not None
        assert decl_span.kind == CdataKind.POU_DECLARATION
        assert "FUNCTION_BLOCK FB_Test" in decl_span.content

        impl_span = doc.get_implementation_span()
        assert impl_span is not None
        assert impl_span.kind == CdataKind.POU_IMPLEMENTATION
        assert "_nCounter := _nCounter + 1;" in impl_span.content

        m_spans = doc.get_method_spans("M_Init")
        assert len(m_spans) == 2
        assert any(s.kind == CdataKind.METHOD_DECLARATION for s in m_spans)
        assert any(s.kind == CdataKind.METHOD_IMPLEMENTATION for s in m_spans)

        prop_spans = doc.get_property_spans("P_Val")
        assert len(prop_spans) == 3
        assert any(s.kind == CdataKind.PROPERTY_DECLARATION for s in prop_spans)
        assert any(s.kind == CdataKind.PROPERTY_GET_DECLARATION for s in prop_spans)
        assert any(s.kind == CdataKind.PROPERTY_GET_IMPLEMENTATION for s in prop_spans)

        act_spans = doc.get_action_spans("A_Reset")
        assert len(act_spans) == 1
        assert act_spans[0].kind == CdataKind.ACTION_IMPLEMENTATION
        assert "_nCounter := 0;" in act_spans[0].content

    def test_dut_and_gvl_classification(self):
        dut_xml = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <DUT Name="ST_Sample" Id="{12345678-1234-1234-1234-123456789abc}">
    <Declaration><![CDATA[TYPE ST_Sample :
STRUCT
    nVal : INT;
END_STRUCT
END_TYPE]]></Declaration>
  </DUT>
</TcPlcObject>"""
        dut_doc = read_tc_xml(dut_xml)
        assert dut_doc.root_object_type == "DUT"
        assert dut_doc.root_object_name == "ST_Sample"
        span = dut_doc.get_declaration_span()
        assert span is not None
        assert span.kind == CdataKind.DUT_DECLARATION
        assert "TYPE ST_Sample :" in span.content


# ===========================================================================
# 3. Surgical Patching Tests
# ===========================================================================

class TestSurgicalPatching:
    """Tests point-in-time substring replacements without XML re-serialization."""

    def test_patch_single_declaration(self):
        xml_orig = """<?xml version="1.0" encoding="utf-8"?>
<!-- Important comment that must not disappear -->
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="FB_Motor" Id="{abcdef01-1234-5678-90ab-cdef01234567}" SpecialFunc="None">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Motor
VAR
    bOld : BOOL;
END_VAR]]></Declaration>
    <Implementation>
      <ST><![CDATA[bOld := TRUE;]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>"""
        doc = read_tc_xml(xml_orig)
        new_decl = """FUNCTION_BLOCK FB_Motor
VAR
    bNew : BOOL;
    nSpeed : INT;
END_VAR"""
        patched = patch_declaration(doc, new_decl)

        # XML Comments, header, GUID must remain untouched
        assert "<!-- Important comment that must not disappear -->" in patched
        assert 'Id="{abcdef01-1234-5678-90ab-cdef01234567}"' in patched
        assert 'bNew : BOOL;' in patched
        assert 'nSpeed : INT;' in patched
        assert 'bOld : BOOL;' not in patched
        assert '<ST><![CDATA[bOld := TRUE;]]></ST>' in patched

    def test_patch_method_implementation_only(self):
        xml_orig = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">
  <POU Name="FB_Service" Id="{11111111-1111-1111-1111-111111111111}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Service]]></Declaration>
    <Implementation>
      <ST><![CDATA[;]]></ST>
    </Implementation>
    <Method Name="M_DoWork" Id="{22222222-2222-2222-2222-222222222222}">
      <Declaration><![CDATA[METHOD M_DoWork : BOOL]]></Declaration>
      <Implementation>
        <ST><![CDATA[// Old implementation
M_DoWork := FALSE;]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>"""
        doc = read_tc_xml(xml_orig)
        new_impl = "// New implementation\nM_DoWork := TRUE;"
        patched = patch_method(doc, "M_DoWork", new_implementation=new_impl)

        assert "// New implementation" in patched
        assert "M_DoWork := TRUE;" in patched
        assert "// Old implementation" not in patched
        assert 'Id="{22222222-2222-2222-2222-222222222222}"' in patched

    def test_multi_span_patch_reverse_offset_order(self):
        xml_orig = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Multi" Id="{00000000-0000-0000-0000-000000000000}">
    <Declaration><![CDATA[DECL_ORIG]]></Declaration>
    <Implementation>
      <ST><![CDATA[IMPL_ORIG]]></ST>
    </Implementation>
    <Method Name="M1" Id="{11111111-1111-1111-1111-111111111111}">
      <Declaration><![CDATA[M1_DECL_ORIG]]></Declaration>
      <Implementation>
        <ST><![CDATA[M1_IMPL_ORIG]]></ST>
      </Implementation>
    </Method>
  </POU>
</TcPlcObject>"""
        doc = read_tc_xml(xml_orig)

        # Replace each section with a specific new content of different length
        def _replacer(span: CdataSpan) -> str | None:
            if span.kind == CdataKind.POU_DECLARATION:
                return "DECL_EXPANDED_MUCH_LONGER_CONTENT"
            if span.kind == CdataKind.POU_IMPLEMENTATION:
                return "IMPL_SHORT"
            if span.kind == CdataKind.METHOD_DECLARATION:
                return "M1_NEW_DECL"
            if span.kind == CdataKind.METHOD_IMPLEMENTATION:
                return "M1_NEW_IMPL_CODE"
            return None

        patched_text, count = patch_by_filter(doc, _replacer)
        assert count == 4
        assert "DECL_EXPANDED_MUCH_LONGER_CONTENT" in patched_text
        assert "IMPL_SHORT" in patched_text
        assert "M1_NEW_DECL" in patched_text
        assert "M1_NEW_IMPL_CODE" in patched_text

    def test_noop_patch_returns_identical_string(self):
        xml_orig = """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Same" Id="{00000000-0000-0000-0000-000000000000}">
    <Declaration><![CDATA[ST_SAME]]></Declaration>
  </POU>
</TcPlcObject>"""
        doc = read_tc_xml(xml_orig)
        res = patch_cdata_span(doc, doc.cdata_spans[0], "ST_SAME")
        assert res is doc.raw_text


# ===========================================================================
# 4. Encoding, BOM and CRLF Preservation Tests
# ===========================================================================

class TestEncodingAndBomPreservation:
    """Tests preservation of UTF-8 BOM, encoding, and CRLF line endings."""

    def test_utf8_bom_detection_and_encoding(self):
        text_with_crlf = '<?xml version="1.0" encoding="utf-8"?>\r\n<TcPlcObject Version="1.1.0.1">\r\n</TcPlcObject>\r\n'
        raw_bytes_with_bom = codecs.BOM_UTF8 + text_with_crlf.encode("utf-8")

        decoded, enc_info = detect_encoding_info(raw_bytes_with_bom)
        assert enc_info.has_bom is True
        assert enc_info.encoding == "utf-8"
        assert enc_info.line_ending == "\r\n"

        re_encoded = encode_document(decoded, enc_info)
        assert re_encoded == raw_bytes_with_bom

    def test_crlf_standardization_on_encode(self):
        mixed_text = "line1\nline2\r\nline3\rline4"
        info = XmlEncodingInfo(encoding="utf-8", line_ending="\r\n", has_bom=False)
        encoded = encode_document(mixed_text, info)
        assert b"line1\r\nline2\r\nline3\r\nline4" == encoded


# ===========================================================================
# 5. GUID Validation and Preservation Tests
# ===========================================================================

class TestGuidManagement:
    """Tests GUID validation and fake AI detection."""

    def test_valid_and_invalid_guids(self):
        assert is_valid_guid("{d8471e9a-4c28-4033-bb92-e421a1f0a1c8}")
        assert is_valid_guid("d8471e9a-4c28-4033-bb92-e421a1f0a1c8")
        assert not is_valid_guid("not-a-guid")
        assert not is_valid_guid("{123-invalid}")

    def test_fake_ai_guid_heuristics(self):
        # Known fake prefixes
        assert is_fake_ai_guid("{12345678-1234-1234-1234-123456789abc}")
        assert is_fake_ai_guid("{abcdef01-1234-5678-90ab-cdef01234567}")
        # Repeated digits
        assert is_fake_ai_guid("{aaaaa111-2222-3333-4444-555555555555}")
        # Valid random uuid4
        assert not is_fake_ai_guid("{82848a68-ef61-408e-ac30-65608590b957}")
        assert not is_fake_ai_guid("{c1891f57-0da9-4e5c-b324-15acd7b61c68}")

    def test_guid_normalization_and_extraction(self):
        xml_text = """<POU Id="{D8471E9A-4C28-4033-BB92-E421A1F0A1C8}">
  <Method Id="d8471e9a-4c28-4033-bb92-e421a1f0a1c8" />
  <Action Id="{11111111-2222-3333-4444-555555555555}" />
</POU>"""
        guids = extract_all_guids(xml_text)
        assert len(guids) == 3
        dups = find_duplicate_guids(xml_text)
        assert len(dups) == 1
        assert dups[0] == "{d8471e9a-4c28-4033-bb92-e421a1f0a1c8}"


# ===========================================================================
# 6. Safe Atomic File I/O Tests
# ===========================================================================

class TestSafeIo:
    """Tests atomic write, backup creation, and rollback."""

    def test_atomic_write_and_no_change_detection(self, tmp_path: Path):
        test_file = tmp_path / "test.TcPOU"
        test_content = b'<?xml version="1.0" encoding="utf-8"?>\r\n<POU Name="Test"/>'

        res1 = write_file_safe(test_file, test_content)
        assert res1.written is True
        assert test_file.read_bytes() == test_content

        # Writing identical content -> written=False
        res2 = write_file_safe(test_file, test_content)
        assert res2.written is False

    def test_save_document_lossless(self, tmp_path: Path):
        test_file = tmp_path / "FB_Test.TcPOU"
        xml_content = '<?xml version="1.0" encoding="utf-8"?>\r\n<POU Name="FB_Test"><Declaration><![CDATA[VAR END_VAR]]></Declaration></POU>\r\n'
        test_file.write_bytes(xml_content.encode("utf-8"))

        doc = read_tc_xml_file(test_file)
        new_decl = "VAR\n    bFlag : BOOL;\nEND_VAR"
        new_xml = patch_declaration(doc, new_decl)
        doc.raw_text = new_xml

        save_res = save_document_lossless(doc)
        assert save_res.written is True
        assert "bFlag : BOOL;" in test_file.read_text(encoding="utf-8")
