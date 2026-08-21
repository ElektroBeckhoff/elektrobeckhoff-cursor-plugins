"""Unit tests for infosys_mshc.search module."""

import pytest
from infosys_mshc.search import (
    fts5_sanitize,
    score_entry,
    search_auto,
    search_symbol,
    search_title,
)


def test_fts5_sanitize():
    assert fts5_sanitize("") == ""
    assert fts5_sanitize("   ") == ""
    assert fts5_sanitize('"input registers"') == '"input registers"'
    assert fts5_sanitize("FB_Json*") == "FB_Json*"
    assert fts5_sanitize("PID, controller; (test)") == "PID controller test"


def test_score_entry():
    raw_entry = {
        "title": "FB_Sample",
        "type": "FUNCTION_BLOCK",
        "component": "sample_lib",
        "path": "sample/1033/1.html",
        "description": "Sample description",
    }
    scored = score_entry(raw_entry, 90)
    assert scored["score"] == 90
    assert scored["title"] == "FB_Sample"
    assert scored["description"] == "Sample description"


def test_search_title():
    entries = [
        {"title": "FB_Test", "type": "FUNCTION_BLOCK", "component": "lib", "path": "1.html"},
        {"title": "FB_Testing", "type": "FUNCTION_BLOCK", "component": "lib", "path": "2.html"},
        {"title": "ST_FB_Test_Param", "type": "STRUCT", "component": "lib", "path": "3.html"},
        {"title": "Other", "type": "article", "component": "lib", "path": "4.html"},
    ]
    res = search_title(entries, "fb_test", limit=10)
    assert len(res) == 3
    assert res[0]["title"] == "FB_Test"
    assert res[0]["score"] == 100
    assert res[1]["title"] == "FB_Testing"
    assert res[1]["score"] == 90
    assert res[2]["title"] == "ST_FB_Test_Param"
    assert res[2]["score"] == 70


def test_search_symbol():
    entries = [
        {"title": "FB_Test", "type": "FUNCTION_BLOCK", "component": "lib", "path": "1.html"},
        {"title": "Overview FB_Test", "type": "article", "component": "lib", "path": "2.html"},
    ]
    res = search_symbol(entries, "fb_test", limit=10)
    assert len(res) == 1
    assert res[0]["title"] == "FB_Test"
    assert res[0]["type"] == "FUNCTION_BLOCK"


def test_search_auto_priorities():
    entries = [
        {"title": "FB_MqttClient", "type": "FUNCTION_BLOCK", "component": "mqtt", "path": "1.html"},
        {"title": "FB_MqttClient_Ext", "type": "FUNCTION_BLOCK", "component": "mqtt", "path": "2.html"},
        {"title": "ST_FB_MqttClient", "type": "STRUCT", "component": "mqtt", "path": "3.html"},
    ]
    title_map = {"fb_mqttclient": entries[0]}
    res = search_auto(entries, title_map, "FB_MqttClient", "fb_mqttclient", limit=10)
    assert len(res) >= 1
    assert res[0]["title"] == "FB_MqttClient"
    assert res[0]["score"] == 100
