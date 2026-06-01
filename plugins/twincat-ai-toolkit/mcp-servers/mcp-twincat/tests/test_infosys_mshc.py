"""Smoke tests for twincat_infosys_mshc_search / twincat_infosys_mshc_read."""

import json
import os
import pytest

from twincat_infosys_mshc import InfoSysMshcIndex, DEFAULT_MSHC_PATH

MSHC_AVAILABLE = os.path.isfile(DEFAULT_MSHC_PATH)
skip_no_mshc = pytest.mark.skipif(
    not MSHC_AVAILABLE,
    reason=f"MSHC not installed at {DEFAULT_MSHC_PATH}",
)


@skip_no_mshc
class TestInfoSysMshcSearch:
    @pytest.fixture(scope="class")
    def idx(self):
        return InfoSysMshcIndex()

    def test_search_exact_fb(self, idx):
        r = idx.search("FB_IotMqttClient")
        assert r["count"] >= 1
        top = r["results"][0]
        assert top["title"] == "FB_IotMqttClient"
        assert top["type"] == "FUNCTION_BLOCK"
        assert top["score"] == 100
        assert "tf6701" in top["component"]

    def test_search_enum(self, idx):
        r = idx.search("E_ALY_BandMode", mode="symbol")
        assert r["count"] >= 1
        assert r["results"][0]["type"] == "ENUM"

    def test_search_struct(self, idx):
        r = idx.search("ST_IotMqttWill")
        assert r["count"] >= 1
        assert r["results"][0]["type"] == "STRUCT"

    def test_search_title_mode(self, idx):
        r = idx.search("FB_JsonDomParser", mode="title")
        assert r["count"] >= 1
        assert r["results"][0]["title"] == "FB_JsonDomParser"

    def test_search_limit(self, idx):
        r = idx.search("FB_", limit=5)
        assert len(r["results"]) <= 5

    def test_search_empty_query(self, idx):
        r = idx.search("")
        assert r["count"] == 0

    def test_search_nonexistent(self, idx):
        r = idx.search("XYZZY_NONEXISTENT_SYMBOL_12345")
        assert r["count"] == 0


@skip_no_mshc
class TestInfoSysMshcRead:
    @pytest.fixture(scope="class")
    def idx(self):
        return InfoSysMshcIndex()

    def test_read_fb_page(self, idx):
        page = idx.read_page(
            "tf6701_tc3_iot_communication_mqtt/1033/3391835403.html"
        )
        assert page["title"] == "FB_IotMqttClient"
        assert page["type"] == "FUNCTION_BLOCK"
        assert "FUNCTION_BLOCK" in page["syntax"]
        assert "VAR_INPUT" in page["syntax"]
        assert len(page["inputs"]) > 0
        assert len(page["outputs"]) > 0
        assert page["full_text"]

    def test_read_nonexistent(self, idx):
        with pytest.raises(FileNotFoundError):
            idx.read_page("nonexistent/path.html")

    def test_read_has_requirements(self, idx):
        page = idx.read_page(
            "tf6701_tc3_iot_communication_mqtt/1033/3391835403.html"
        )
        assert "requirements" in page
        assert page["requirements"].get("library")


class TestInfoSysMshcMissing:
    def test_missing_mshc_file(self):
        idx = InfoSysMshcIndex(r"C:\nonexistent\path.mshc")
        with pytest.raises(FileNotFoundError, match="MSHC file not found"):
            idx.search("test")


@skip_no_mshc
class TestMcpToolWrappers:
    def test_search_tool(self):
        from server import twincat_infosys_mshc_search
        raw = twincat_infosys_mshc_search(query="FB_IotMqttClient")
        data = json.loads(raw)
        assert data["count"] >= 1
        assert data["results"][0]["title"] == "FB_IotMqttClient"

    def test_read_tool(self):
        from server import twincat_infosys_mshc_read
        raw = twincat_infosys_mshc_read(
            path="tf6701_tc3_iot_communication_mqtt/1033/3391835403.html"
        )
        data = json.loads(raw)
        assert data["title"] == "FB_IotMqttClient"
        assert "FUNCTION_BLOCK" in data["syntax"]

    def test_search_missing_file(self):
        from server import twincat_infosys_mshc_search
        raw = twincat_infosys_mshc_search(
            query="test", file_path=r"C:\nonexistent.mshc"
        )
        data = json.loads(raw)
        assert data.get("success") is False
        assert "not found" in data.get("error", "").lower()
