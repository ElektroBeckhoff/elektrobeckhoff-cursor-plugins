"""sys.path configuration for formatter tests."""
import sys
from pathlib import Path

import pytest

_mcp_twincat_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_mcp_twincat_root))
sys.path.insert(0, str(_mcp_twincat_root / "tests" / "formatter"))
sys.path.insert(0, str(_mcp_twincat_root / "tests" / "formatter" / "scripts"))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "fast: quick subset (failures-only byte match)")

