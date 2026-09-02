"""
TwinCAT MCP Server for Cursor IDE.

Exposes TcXaeShell build automation, runtime control (TE1000 + ADS),
Usermode Runtime (TC170x), FBD/FUP-to-ST and CFC-to-ST migration as MCP tools:
status/open/check/build/export/close, target/activate/start/tasks,
UmRT start/stop, ADS mode + PLC + variable R/W, ST formatting,
migrators, plcproj, InfoSys.

Transport: stdio  (Cursor starts this process as a child)
COM:       TcXaeShell via STA thread (twincat_automation_interface / TE1000)
ADS:       pyads client (ads/twincat_ads_client) for runtime & symbols
UmRT:      TC170x Usermode Runtime controller (umrt/twincat_umrt_controller)
"""

from __future__ import annotations

import logging
import os
import sys
import threading

_server_dir = os.path.dirname(os.path.abspath(__file__))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)
for _subdir in (
    "migrator",
    "automation_interface",
    "plcproj",
    "ads",
    "umrt",
):
    _p = os.path.join(_server_dir, _subdir)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from migrator._bootstrap import setup_migrator_paths  # noqa: E402

setup_migrator_paths()

# stdout is the MCP JSON-RPC wire -- all logging goes to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("twincat-mcp")

from mcp.server.fastmcp import FastMCP
from twincat_automation_interface import TcAutomationInterface, HAS_WIN32
import extension_ops

# Automatically check & update VS Code extension in background on MCP startup
threading.Thread(target=extension_ops.auto_update_if_needed, daemon=True).start()

# FastMCP application instance
mcp = FastMCP("TwinCAT")

# Import all domain tools & helpers for registration and re-export
from tools.common import (  # noqa: E402, F401
    _as_dict,
    _clean_path,
    _find_repo_root,
    _json,
    _parse_xti,
    _read_plcproj_meta,
    _read_proj_name,
    _resolve_directory,
    _resolve_path,
    _resolve_plcproj_path,
    _resolve_sln,
    _resolve_tsproj,
    _scan_plcproj_in_dir,
    _auto_detect_plcproj,
    _EXCLUDES_LOWER,
    _SLN_PROJECT_RE,
)

from tools.core_syntax import (  # noqa: E402, F401
    twincat_plcproj_info,
    twincat_workspace_symbols,
    twincat_symbol_lookup,
    twincat_check_syntax,
)

from tools.solution import (  # noqa: E402, F401
    _bridge,
    _get_bridge,
    twincat_status,
    twincat_open,
    twincat_reload,
    twincat_check_all_objects,
    twincat_build,
    twincat_get_output_log,
    twincat_stweep_status,
    twincat_stweep_format_progress,
    twincat_stweep_format_cancel,
    twincat_stweep_format,
    twincat_dismiss_safe_dialogs,
    twincat_export_progress,
    twincat_export_library,
    twincat_export_check_artifacts,
    twincat_close,
)

from tools.extension import (  # noqa: E402, F401
    twincat_extension_status,
    twincat_extension_install,
    twincat_extension_build,
)

from tools.target_io import (  # noqa: E402, F401
    twincat_get_target,
    twincat_set_target,
    twincat_activate,
    twincat_start,
    twincat_task_list,
    twincat_task_info,
    twincat_io_list,
    twincat_io_set_disabled,
)

from tools.umrt import (  # noqa: E402, F401
    _umrt_controller,
    _get_umrt,
    _umrt_instance_arg,
    _target_context,
    _target_is_mcp_umrt,
    _attach_target_safety,
    _enrich_umrt_runtime_result,
    _resolve_ads_net_id,
    twincat_umrt_status,
    twincat_umrt_start,
    twincat_umrt_stop,
    twincat_runtime_state,
    twincat_set_runtime_mode,
    twincat_plc_start,
    twincat_plc_stop,
    twincat_runtime_messages,
    twincat_verify_library_on_target,
    twincat_umrt_e2e,
)

from tools.ads import (  # noqa: E402, F401
    twincat_ads_symbols,
    twincat_ads_read,
    twincat_ads_read_list,
    twincat_ads_write,
    twincat_ads_write_list,
)

from tools.migrator import (  # noqa: E402, F401
    _detect_member_filter,
    _file_has_auto_generated,
    _collect_format_targets,
    _format_after_migrate,
    _AUTO_GEN_MARKER,
    _TC_EXTENSIONS,
    twincat_fup_migrate,
    twincat_cfc_migrate,
    twincat_migrate,
)

from tools.autodocs import (  # noqa: E402, F401
    twincat_autodocs,
)

from tools.plcproj import (  # noqa: E402, F401
    twincat_plcproj_verify,
    twincat_plcproj_sync,
)

from tools.infosys import (  # noqa: E402, F401
    _infosys_mshc_cache,
    _get_infosys_mshc,
    twincat_infosys_mshc_search,
    twincat_infosys_mshc_read,
)

from tools.formatter import (  # noqa: E402, F401
    _format_lock,
    _format_progress,
    twincat_format,
    twincat_format_progress,
    twincat_format_validate,
    twincat_format_config,
)

from tools import register_all_tools  # noqa: E402

# Register all MCP tools with FastMCP
register_all_tools(mcp)


if __name__ == "__main__":
    mcp.run()
