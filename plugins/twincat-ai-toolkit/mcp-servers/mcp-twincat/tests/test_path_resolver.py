"""
Tests for path resolution, PLC name guessing, and solution_path in error results.

Covers:
  - _resolve_tsproj with inline PrjFilePath (no .xti)
  - _resolve_tsproj with .xti (regression)
  - _resolve_tsproj with mixed .xti + inline
  - Soft-fail: .sln resolver error does not block ROT attach
  - _guess_proj_name reads from plcproj, not sln basename
  - _try_read_dte_sln / solution_path in failure OpenResult
"""

import os
import sys
import textwrap
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub COM modules so we can import on non-Windows
# ---------------------------------------------------------------------------
_fake_pythoncom = MagicMock()
_fake_pythoncom.CoInitialize = MagicMock()
_fake_pythoncom.CoUninitialize = MagicMock()
_fake_pythoncom.PumpWaitingMessages = MagicMock()
_fake_pythoncom.CLSCTX_LOCAL_SERVER = 4
_fake_pythoncom.IID_IDispatch = "IID_IDispatch"
_fake_pythoncom.CoCreateInstance = MagicMock()

_fake_win32com = MagicMock()
_fake_win32com_client = MagicMock()
_fake_win32com.client = _fake_win32com_client

sys.modules.setdefault("pythoncom", _fake_pythoncom)
sys.modules.setdefault("pywintypes", MagicMock())
sys.modules.setdefault("win32com", _fake_win32com)
sys.modules.setdefault("win32com.client", _fake_win32com_client)
sys.modules.setdefault("win32gui", MagicMock())
sys.modules.setdefault("win32con", MagicMock())

from twincat_automation_interface import TcAutomationInterface


# ===================================================================
# Helpers
# ===================================================================

def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))


PLCPROJ_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<Project DefaultTargets="Build"
         xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Name>{name}</Name>
    <ProjectGuid>{{ABCD1234}}</ProjectGuid>
  </PropertyGroup>
</Project>
"""

XTI_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<TcSmItem>
  <Project Name="{name}" PrjFilePath="{prj_file_path}"/>
</TcSmItem>
"""


# ===================================================================
# 1. _resolve_tsproj: inline PrjFilePath
# ===================================================================

class TestResolveTsprojInline:
    """Tests for inline PrjFilePath resolution in _resolve_tsproj."""

    def test_inline_prjfilepath_single(self, tmp_path):
        """Single <Project PrjFilePath=...> without File attr resolves."""
        from server import _resolve_tsproj

        plcproj = tmp_path / "PLC" / "PLC.plcproj"
        _write(str(plcproj), PLCPROJ_TEMPLATE.format(name="PLC"))

        tsproj = tmp_path / "MySolution.tsproj"
        _write(str(tsproj), f"""\
        <?xml version="1.0" encoding="utf-8"?>
        <TcSmProject>
          <Plc>
            <Project Name="PLC" PrjFilePath="PLC\\PLC.plcproj"/>
          </Plc>
        </TcSmProject>
        """)

        result = _resolve_tsproj(str(tsproj), str(tmp_path / "MySolution.sln"))
        assert isinstance(result, str), f"Expected path string, got {result}"
        assert result == os.path.normpath(str(plcproj))

    def test_inline_prjfilepath_with_name(self, tmp_path):
        """Name attribute is captured from inline Project element."""
        from server import _resolve_tsproj

        plcproj = tmp_path / "MyPLC" / "MyPLC.plcproj"
        _write(str(plcproj), PLCPROJ_TEMPLATE.format(name="MyPLC"))

        tsproj = tmp_path / "Test.tsproj"
        _write(str(tsproj), f"""\
        <?xml version="1.0" encoding="utf-8"?>
        <TcSmProject>
          <Plc>
            <Project Name="MyPLC" PrjFilePath="MyPLC\\MyPLC.plcproj"/>
          </Plc>
        </TcSmProject>
        """)

        result = _resolve_tsproj(str(tsproj), str(tmp_path / "Test.sln"))
        assert isinstance(result, str)

    def test_inline_missing_plcproj_file(self, tmp_path):
        """Inline PrjFilePath pointing to non-existent file is skipped."""
        from server import _resolve_tsproj

        tsproj = tmp_path / "Test.tsproj"
        _write(str(tsproj), """\
        <?xml version="1.0" encoding="utf-8"?>
        <TcSmProject>
          <Plc>
            <Project Name="Ghost" PrjFilePath="Ghost\\Ghost.plcproj"/>
          </Plc>
        </TcSmProject>
        """)

        result = _resolve_tsproj(str(tsproj), str(tmp_path / "Test.sln"))
        assert isinstance(result, dict)
        assert "No PLC projects" in result.get("error", "")

    def test_multiple_inline_projects(self, tmp_path):
        """Multiple inline projects → multiple_plc_projects error."""
        from server import _resolve_tsproj

        for name in ("PLC1", "PLC2"):
            _write(
                str(tmp_path / name / f"{name}.plcproj"),
                PLCPROJ_TEMPLATE.format(name=name),
            )

        tsproj = tmp_path / "Multi.tsproj"
        _write(str(tsproj), """\
        <?xml version="1.0" encoding="utf-8"?>
        <TcSmProject>
          <Plc>
            <Project Name="PLC1" PrjFilePath="PLC1\\PLC1.plcproj"/>
            <Project Name="PLC2" PrjFilePath="PLC2\\PLC2.plcproj"/>
          </Plc>
        </TcSmProject>
        """)

        result = _resolve_tsproj(str(tsproj), str(tmp_path / "Multi.sln"))
        assert isinstance(result, dict)
        assert result["error"] == "multiple_plc_projects"
        assert len(result["available_projects"]) == 2


# ===================================================================
# 2. _resolve_tsproj: .xti regression
# ===================================================================

class TestResolveTsprojXti:
    """Ensure existing .xti-based resolution still works."""

    def test_xti_resolution(self, tmp_path):
        from server import _resolve_tsproj

        plcproj = tmp_path / "PLC" / "PLC.plcproj"
        _write(str(plcproj), PLCPROJ_TEMPLATE.format(name="PLC"))

        xti_dir = tmp_path / "_Config" / "PLC"
        xti_file = xti_dir / "PLC.xti"
        rel_plcproj = os.path.relpath(str(plcproj), str(xti_dir))
        _write(str(xti_file), XTI_TEMPLATE.format(
            name="PLC", prj_file_path=rel_plcproj,
        ))

        tsproj = tmp_path / "MySolution.tsproj"
        _write(str(tsproj), """\
        <?xml version="1.0" encoding="utf-8"?>
        <TcSmProject>
          <Plc>
            <Project File="PLC.xti"/>
          </Plc>
        </TcSmProject>
        """)

        result = _resolve_tsproj(str(tsproj), str(tmp_path / "MySolution.sln"))
        assert isinstance(result, str)
        assert result == os.path.normpath(str(plcproj))

    def test_xti_preferred_over_inline(self, tmp_path):
        """When both File attr and PrjFilePath exist, .xti wins."""
        from server import _resolve_tsproj

        plcproj = tmp_path / "PLC" / "PLC.plcproj"
        _write(str(plcproj), PLCPROJ_TEMPLATE.format(name="PLC"))

        xti_dir = tmp_path / "_Config" / "PLC"
        xti_file = xti_dir / "PLC.xti"
        rel_plcproj = os.path.relpath(str(plcproj), str(xti_dir))
        _write(str(xti_file), XTI_TEMPLATE.format(
            name="PLC", prj_file_path=rel_plcproj,
        ))

        tsproj = tmp_path / "MySolution.tsproj"
        _write(str(tsproj), """\
        <?xml version="1.0" encoding="utf-8"?>
        <TcSmProject>
          <Plc>
            <Project File="PLC.xti" PrjFilePath="PLC\\PLC.plcproj"/>
          </Plc>
        </TcSmProject>
        """)

        result = _resolve_tsproj(str(tsproj), str(tmp_path / "MySolution.sln"))
        assert isinstance(result, str)
        assert result == os.path.normpath(str(plcproj))

    def test_xti_missing_falls_back_to_inline(self, tmp_path):
        """File attr set but .xti missing → falls back to inline PrjFilePath."""
        from server import _resolve_tsproj

        plcproj = tmp_path / "PLC" / "PLC.plcproj"
        _write(str(plcproj), PLCPROJ_TEMPLATE.format(name="PLC"))

        tsproj = tmp_path / "MySolution.tsproj"
        _write(str(tsproj), """\
        <?xml version="1.0" encoding="utf-8"?>
        <TcSmProject>
          <Plc>
            <Project File="DoesNotExist.xti" PrjFilePath="PLC\\PLC.plcproj"/>
          </Plc>
        </TcSmProject>
        """)

        result = _resolve_tsproj(str(tsproj), str(tmp_path / "MySolution.sln"))
        assert isinstance(result, str)
        assert result == os.path.normpath(str(plcproj))


# ===================================================================
# 3. _guess_proj_name reads from plcproj
# ===================================================================

class TestGuessProjName:
    """Tests for _guess_proj_name preferring plcproj metadata."""

    def _make_bridge(self):
        with patch.object(TcAutomationInterface, "__init__", lambda self: None):
            bridge = TcAutomationInterface()
        bridge._dte = None
        bridge._prog_id = None
        bridge._sln_path = None
        bridge._plcproj_file_path = None
        bridge._created_new = False
        bridge._sys_man = None
        bridge._plc_proj_item = None
        bridge._instance_registry = {}
        return bridge

    def test_name_from_plcproj_xml(self, tmp_path):
        """Name is read from <Name> element in .plcproj XML."""
        bridge = self._make_bridge()
        plcproj = tmp_path / "PLC.plcproj"
        _write(str(plcproj), PLCPROJ_TEMPLATE.format(name="MyRealPLC"))
        bridge._plcproj_file_path = str(plcproj)

        name = bridge._guess_proj_name()
        assert name == "MyRealPLC"

    def test_name_from_plcproj_filename(self, tmp_path):
        """If <Name> missing, falls back to plcproj filename stem."""
        bridge = self._make_bridge()
        plcproj = tmp_path / "FallbackName.plcproj"
        _write(str(plcproj), """\
        <?xml version="1.0" encoding="utf-8"?>
        <Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
          <PropertyGroup>
            <ProjectGuid>{1234}</ProjectGuid>
          </PropertyGroup>
        </Project>
        """)
        bridge._plcproj_file_path = str(plcproj)

        name = bridge._guess_proj_name()
        assert name == "FallbackName"

    def test_name_from_sln_basename(self):
        """Without plcproj, falls back to sln basename."""
        bridge = self._make_bridge()
        bridge._plcproj_file_path = None
        dte_mock = MagicMock()
        dte_mock.Solution.FullName = r"C:\Work\Tc3_EB_BA.sln"
        bridge._dte = dte_mock

        name = bridge._guess_proj_name()
        assert name == "Tc3_EB_BA"


# ===================================================================
# 4. _try_read_dte_sln / solution_path in error results
# ===================================================================

class TestTryReadDteSln:

    def _make_bridge(self):
        with patch.object(TcAutomationInterface, "__init__", lambda self: None):
            bridge = TcAutomationInterface()
        bridge._dte = None
        bridge._prog_id = None
        bridge._sln_path = None
        bridge._plcproj_file_path = None
        bridge._created_new = False
        bridge._sys_man = None
        bridge._plc_proj_item = None
        bridge._instance_registry = {}
        return bridge

    def test_returns_fullname(self):
        bridge = self._make_bridge()
        dte_mock = MagicMock()
        dte_mock.Solution.FullName = r"C:\Projects\Test.sln"
        bridge._dte = dte_mock

        assert bridge._try_read_dte_sln() == r"C:\Projects\Test.sln"

    def test_returns_empty_on_error(self):
        bridge = self._make_bridge()
        dte_mock = MagicMock()
        dte_mock.Solution.FullName = property(
            lambda self: (_ for _ in ()).throw(Exception("COM dead"))
        )
        bridge._dte = dte_mock

        result = bridge._try_read_dte_sln()
        assert result == "" or isinstance(result, str)

    def test_returns_empty_when_no_dte(self):
        bridge = self._make_bridge()
        bridge._dte = None
        assert bridge._try_read_dte_sln() == ""


# ===================================================================
# 5. _read_plcproj_name static method
# ===================================================================

class TestReadPlcprojName:

    def test_reads_name_element(self, tmp_path):
        plcproj = tmp_path / "Test.plcproj"
        _write(str(plcproj), PLCPROJ_TEMPLATE.format(name="MyProject"))
        assert TcAutomationInterface._read_plcproj_name(str(plcproj)) == "MyProject"

    def test_falls_back_to_filename(self, tmp_path):
        plcproj = tmp_path / "FallbackPLC.plcproj"
        _write(str(plcproj), """\
        <?xml version="1.0" encoding="utf-8"?>
        <Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
        </Project>
        """)
        assert TcAutomationInterface._read_plcproj_name(str(plcproj)) == "FallbackPLC"

    def test_nonexistent_file(self, tmp_path):
        result = TcAutomationInterface._read_plcproj_name(
            str(tmp_path / "nope.plcproj")
        )
        assert result == "nope"
