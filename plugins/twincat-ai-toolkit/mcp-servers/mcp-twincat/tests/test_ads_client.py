"""Unit tests for ADS client helpers (mocked pyads)."""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import twincat_ads_client as ads_mod
from twincat_ads_client import (
    AdsClient,
    coerce_write_value,
    parse_symbol_list,
    parse_symbol_value_map,
)


class TestCoerceWriteValue(unittest.TestCase):
    def test_bool_strings(self):
        v, t = coerce_write_value("true", "BOOL")
        self.assertTrue(v)
        self.assertEqual(t, "BOOL")
        v, t = coerce_write_value("0")
        self.assertFalse(v)

    def test_numbers(self):
        v, t = coerce_write_value("42", "DINT")
        self.assertEqual(v, 42)
        self.assertEqual(t, "DINT")
        v, t = coerce_write_value("3.14", "LREAL")
        self.assertAlmostEqual(v, 3.14)
        self.assertEqual(t, "LREAL")

    def test_string(self):
        v, t = coerce_write_value("hello", "STRING")
        self.assertEqual(v, "hello")
        self.assertEqual(t, "STRING")


class TestAdsClientMocked(unittest.TestCase):
    @patch.object(ads_mod, "HAS_PYADS", True)
    @patch.object(ads_mod, "pyads")
    def test_read_state_and_set_mode(self, mock_pyads):
        mock_pyads.ADSState.ADSSTATE_RUN = 5
        mock_pyads.ADSState.ADSSTATE_CONFIG = 16
        mock_pyads.ADSState.ADSSTATE_STOP = 6
        conn = MagicMock()
        conn.read_state.return_value = (5, 0)
        mock_pyads.Connection.return_value = conn

        client = AdsClient("127.0.0.1.1.1", port=10000)
        client._conn = conn
        state = client.read_state()
        self.assertTrue(state["success"])
        self.assertEqual(state["device_state"], 0)

        result = client.set_ads_state("config")
        conn.write_control.assert_called()
        self.assertEqual(result["requested_mode"], "config")

    @patch.object(ads_mod, "HAS_PYADS", True)
    @patch.object(ads_mod, "pyads")
    def test_read_write_by_name(self, mock_pyads):
        mock_pyads.PLCTYPE_BOOL = object()
        conn = MagicMock()
        conn.read_by_name.return_value = True
        mock_pyads.Connection.return_value = conn

        client = AdsClient("127.0.0.1.1.1", port=851)
        client._conn = conn
        r = client.read_by_name("MAIN.bEnable")
        self.assertTrue(r["success"])
        self.assertEqual(r["value"], True)

        w = client.write_by_name("MAIN.bEnable", "false", plc_type="BOOL")
        self.assertTrue(w["success"])
        conn.write_by_name.assert_called()

    @patch.object(ads_mod, "HAS_PYADS", True)
    @patch.object(ads_mod, "pyads")
    def test_read_list_by_name(self, mock_pyads):
        conn = MagicMock()
        conn.read_list_by_name.return_value = {
            "MAIN.bEnable": True,
            "P_Sample.fbController._bGateOpen": False,
        }
        mock_pyads.Connection.return_value = conn
        client = AdsClient("127.0.0.1.1.1", port=851)
        client._conn = conn
        r = client.read_list_by_name([
            "MAIN.bEnable", "P_Sample.fbController._bGateOpen",
        ])
        self.assertTrue(r["success"])
        self.assertEqual(r["count"], 2)
        self.assertTrue(r["values"]["MAIN.bEnable"])
        conn.read_list_by_name.assert_called_once()

    def test_parse_symbol_list(self):
        self.assertEqual(
            parse_symbol_list('["A", "B"]'),
            ["A", "B"],
        )
        self.assertEqual(parse_symbol_list("A\nB,C"), ["A", "B", "C"])
        self.assertEqual(
            parse_symbol_value_map('{"A": true, "B": 1}'),
            {"A": True, "B": 1},
        )

    @patch.object(ads_mod, "HAS_PYADS", True)
    @patch.object(ads_mod, "pyads")
    def test_list_symbols_filters(self, mock_pyads):
        class Sym:
            def __init__(self, name, symbol_type="", comment=""):
                self.name = name
                self.symbol_type = symbol_type
                self.comment = comment

        conn = MagicMock()
        conn.get_all_symbols.return_value = [
            Sym("P_Sample.stLightControl1", "ST_Lib_Control_Light"),
            Sym("P_Sample.fbController", "FB_Lib_Controller"),
            Sym("MAIN.bEnable", "BOOL"),
        ]
        mock_pyads.Connection.return_value = conn
        client = AdsClient("127.0.0.1.1.1", port=851)
        client._conn = conn
        r = client.list_symbols(prefix="P_Sample.", max_symbols=10)
        self.assertTrue(r["success"])
        self.assertEqual(r["returned"], 2)
        self.assertEqual(r["symbols"][0]["name"], "P_Sample.stLightControl1")
        r2 = client.list_symbols(name_contains="fbController", type_contains="FB_Lib")
        self.assertEqual(r2["returned"], 1)


class TestAdsMcpConfirm(unittest.TestCase):
    """Confirm guards on server tools (import server helpers)."""

    def test_set_runtime_mode_confirm(self):
        import server as srv

        out = json.loads(srv.twincat_set_runtime_mode(mode="config", confirm=False))
        self.assertFalse(out["success"])
        self.assertEqual(out["error_code"], "confirm_required")
        self.assertIn("confirm", out["error"].lower())

    def test_ads_write_confirm(self):
        import server as srv

        out = json.loads(
            srv.twincat_ads_write(symbol="MAIN.x", value="1", confirm=False)
        )
        self.assertFalse(out["success"])
        self.assertEqual(out["error_code"], "confirm_required")
        self.assertIn("confirm", out["error"].lower())

    def test_plc_stop_confirm(self):
        import server as srv

        out = json.loads(srv.twincat_plc_stop(confirm=False))
        self.assertFalse(out["success"])
        self.assertEqual(out["error_code"], "confirm_required")


if __name__ == "__main__":
    unittest.main()
