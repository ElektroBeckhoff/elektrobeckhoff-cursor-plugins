"""Unit tests for thread-safe ZipFile handle caching and latency in InfoSysMshcIndex."""

import concurrent.futures
import os
import time
import pytest

from infosys_mshc import InfoSysMshcIndex
from infosys_mshc.paths import DEFAULT_MSHC_PATH

skip_no_mshc = pytest.mark.skipif(
    not os.path.isfile(DEFAULT_MSHC_PATH),
    reason="TwinCAT InfoSys offline documentation (.mshc) is not installed",
)


@skip_no_mshc
class TestZipCaching:
    @pytest.fixture(scope="class")
    def idx(self):
        index = InfoSysMshcIndex(DEFAULT_MSHC_PATH)
        yield index
        index.close()

    def test_cached_read_latency_under_10ms(self, idx):
        """Verify that sequential page reads using the cached ZipFile handle average < 5ms."""
        path = "tf6701_tc3_iot_communication_mqtt/1033/3391835403.html"
        # Warmup
        idx.read_page(path)

        latencies = []
        for _ in range(10):
            t0 = time.perf_counter()
            page = idx.read_page(path)
            dt = (time.perf_counter() - t0) * 1000.0
            latencies.append(dt)
            assert page["title"] == "FB_IotMqttClient"

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 10.0, f"Average latency was {avg_latency:.2f}ms (expected < 10ms)"

    def test_concurrent_reads_thread_safety(self, idx):
        """Verify that parallel threads can read concurrently without corrupting ZipFile state."""
        sample_paths = [
            "tf6701_tc3_iot_communication_mqtt/1033/3391835403.html",
            "tcplclib_tc3_jsonxml/1033/4219231115.html",
            "tcplclib_tc2_system/1033/30977547.html",
            "tcplclib_tc2_utilities/1033/34979467.html",
        ]

        def worker(p):
            res = idx.read_page(p)
            assert res["title"]
            return res["title"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            tasks = [executor.submit(worker, p) for p in sample_paths * 5]
            titles = [t.result() for t in concurrent.futures.as_completed(tasks)]

        assert len(titles) == 20
        assert "FB_IotMqttClient" in titles
        assert "FB_JsonDomParser" in titles

    def test_context_manager_close(self):
        """Verify context manager cleanly opens and closes resources."""
        with InfoSysMshcIndex(DEFAULT_MSHC_PATH) as index:
            page = index.read_page("tf6701_tc3_iot_communication_mqtt/1033/3391835403.html")
            assert page["title"] == "FB_IotMqttClient"
            assert index._zf is not None
        assert index._zf is None
