"""Unit tests for infosys_mshc.cli module."""

import json
import os
import pytest
from infosys_mshc.cli import main
from infosys_mshc.paths import DEFAULT_MSHC_PATH

MSHC_AVAILABLE = os.path.isfile(DEFAULT_MSHC_PATH)
skip_no_mshc = pytest.mark.skipif(
    not MSHC_AVAILABLE,
    reason=f"MSHC not installed at {DEFAULT_MSHC_PATH}",
)


def test_cli_no_args_returns_one(capsys):
    rc = main([])
    assert rc == 1
    captured = capsys.readouterr()
    assert "usage:" in captured.err.lower() or "infosys_mshc" in captured.err.lower()


@skip_no_mshc
def test_cli_search_json(capsys):
    rc = main(["--search", "FB_IotMqttClient", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["count"] >= 1
    assert data["results"][0]["title"] == "FB_IotMqttClient"


@skip_no_mshc
def test_cli_search_formatted(capsys):
    rc = main(["--search", "FB_IotMqttClient", "--limit", "3"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "FB_IotMqttClient" in captured.out
    assert "Found" in captured.out


@skip_no_mshc
def test_cli_read_json(capsys):
    rc = main([
        "--read",
        "tf6701_tc3_iot_communication_mqtt/1033/3391835403.html",
        "--json",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["title"] == "FB_IotMqttClient"
    assert "syntax" in data


def test_cli_missing_file_json(capsys):
    rc = main(["--search", "test", "--file", r"C:\nonexistent_file.mshc", "--json"])
    assert rc == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data.get("success") is False
    assert "not found" in data.get("error", "").lower()
