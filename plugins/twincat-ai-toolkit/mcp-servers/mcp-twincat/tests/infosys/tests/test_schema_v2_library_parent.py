"""Unit tests for Schema v2: library, parent symbol, qualified_name, and disambiguation."""

import os
import pytest

from infosys_mshc import InfoSysMshcIndex, extract_library_and_parent
from infosys_mshc.paths import DEFAULT_MSHC_PATH

skip_no_mshc = pytest.mark.skipif(
    not os.path.isfile(DEFAULT_MSHC_PATH),
    reason="TwinCAT InfoSys offline documentation (.mshc) is not installed",
)


def test_extract_library_and_parent_from_metadata():
    """Verify helper extraction logic for various titles and metadata formats."""
    lib, parent, qname = extract_library_and_parent(
        title="FB_JsonDomParser.AddJsonMember",
        display_version="Tc3_JsonXml (v3.1.4024.0)",
        component="tcplclib_tc3_jsonxml",
    )
    assert lib == "Tc3_JsonXml"
    assert parent == "FB_JsonDomParser"
    assert qname == "Tc3_JsonXml.FB_JsonDomParser.AddJsonMember"


def test_extract_library_from_requirements():
    """Verify library extraction from requirements dictionary."""
    lib, parent, qname = extract_library_and_parent(
        title="FB_IotMqttClient",
        display_version="",
        component="tf6701_tc3_iot_communication_mqtt",
        requirements={"library": "Tc3_IotBase"},
    )
    assert lib == "Tc3_IotBase"
    assert parent == ""
    assert qname == "Tc3_IotBase.FB_IotMqttClient"


@skip_no_mshc
class TestSchemaV2Search:
    @pytest.fixture(scope="class")
    def idx(self):
        index = InfoSysMshcIndex(DEFAULT_MSHC_PATH)
        yield index
        index.close()

    def test_search_results_contain_library_and_parent(self, idx):
        """Verify search results expose library, parent, and qualified_name."""
        r = idx.search("FB_JsonDomParser", limit=5)
        assert r["count"] > 0
        top = r["results"][0]
        assert top["title"] == "FB_JsonDomParser"
        assert "library" in top
        assert "qualified_name" in top

    def test_search_filtered_by_library(self, idx):
        """Verify search can be filtered to a specific library."""
        r_all = idx.search("AddJsonMember", limit=10)
        assert r_all["count"] > 0

        r_lib = idx.search("AddJsonMember", limit=5, library="Tc3_JsonXml")
        assert r_lib["count"] > 0
        for item in r_lib["results"]:
            assert "tc3_jsonxml" in item.get("library", "").lower() or "tc3_jsonxml" in item.get("component", "").lower()

    def test_search_filtered_by_parent_mock(self):
        """Verify search disambiguation via parent symbol filtering on entry collections."""
        from infosys_mshc.search import search_auto
        mock_entries = [
            {
                "title": "Reset",
                "type": "METHOD",
                "component": "tcplclib_tc3_jsonxml",
                "path": "p1.html",
                "library": "Tc3_JsonXml",
                "parent": "FB_JsonDomParser",
                "qualified_name": "Tc3_JsonXml.FB_JsonDomParser.Reset",
            },
            {
                "title": "Reset",
                "type": "METHOD",
                "component": "tf6701_tc3_iot",
                "path": "p2.html",
                "library": "Tc3_IotBase",
                "parent": "FB_IotMqttClient",
                "qualified_name": "Tc3_IotBase.FB_IotMqttClient.Reset",
            },
        ]
        mock_title_map = {}
        r = search_auto(mock_entries, mock_title_map, "Reset", "reset", limit=5, parent="FB_JsonDomParser")
        assert len(r) == 1
        assert r[0]["parent"] == "FB_JsonDomParser"
        assert r[0]["library"] == "Tc3_JsonXml"
