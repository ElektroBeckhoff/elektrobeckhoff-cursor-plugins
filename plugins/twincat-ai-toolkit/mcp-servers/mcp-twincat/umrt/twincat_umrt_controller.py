"""
TwinCAT 3 Usermode Runtime (TC170x) process controller.

Manages ProgramData instances created from UmRT_Template. Each MCP server
session gets its own default instance name (workspace-stable or PID-based)
so multiple Cursor windows can run parallel Usermode Runtimes.

Start via Start.bat; stop by terminating matching TcSystemServiceUm.exe (-n).

Reference: InfoSys TC170x | TwinCAT 3 Usermode Runtime
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

log = logging.getLogger("twincat-mcp")

# Prefix for session-scoped instance folders under ProgramData\...\Runtimes\
MCP_INSTANCE_PREFIX = "UmRT_CursorMCP"
# Backward-compatible alias (resolved at call time via resolve_session_instance_name)
MCP_INSTANCE_NAME = MCP_INSTANCE_PREFIX
_EXE_NAME = "TcSystemServiceUm.exe"
_ENV_INSTANCE = "TWINCAT_UMRT_INSTANCE"

_FALLBACK_TC_ROOTS = (
    r"C:\Program Files (x86)\Beckhoff\TwinCAT\3.1",
    r"C:\TwinCAT\3.1",
)


@dataclass
class UmrtInstanceInfo:
    name: str
    path: str = ""
    start_bat: str = ""
    config_dir: str = ""
    running: bool = False
    pid: Optional[int] = None
    ams_net_id: str = ""
    is_mcp_instance: bool = False


@dataclass
class UmrtStatusResult:
    success: bool
    installed: bool = False
    twincat_root: str = ""
    bin_path: str = ""
    template_path: str = ""
    instances_root: str = ""
    mcp_instance: str = ""
    mcp_instance_source: str = ""  # env | workspace | pid
    mcp_running: bool = False
    mcp_ams_net_id: str = ""
    instances: list = field(default_factory=list)
    message: str = ""


@dataclass
class UmrtOpResult:
    success: bool
    instance: str = ""
    pid: Optional[int] = None
    ams_net_id: str = ""
    created_instance: bool = False
    window_mode: str = ""  # minimized | hidden
    message: str = ""


def _sanitize_instance_token(raw: str, max_len: int = 24) -> str:
    """Keep Windows-folder-safe chars for UmRT instance names."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", (raw or "").strip())
    cleaned = cleaned.strip("_-")
    if not cleaned:
        return ""
    return cleaned[:max_len]


def _workspace_fingerprint() -> tuple[str, str]:
    """Return (stable_key, source_label) for the current workspace.

    Prefers Cursor/VS Code style env vars, then process cwd.
    """
    for env_name in (
        "CURSOR_PROJECT_DIR",
        "CURSOR_WORKSPACE",
        "WORKSPACE_FOLDER",
        "VSCODE_WORKSPACE_FOLDER",
        "PWD",
    ):
        val = (os.environ.get(env_name) or "").strip().strip('"')
        if val:
            try:
                key = os.path.normcase(os.path.realpath(val))
            except (OSError, ValueError):
                key = os.path.normcase(os.path.abspath(val))
            return key, f"env:{env_name}"

    try:
        cwd = os.path.normcase(os.path.realpath(os.getcwd()))
    except (OSError, ValueError):
        cwd = os.path.normcase(os.path.abspath(os.getcwd()))
    return cwd, "cwd"


def resolve_session_instance_name(
    explicit: Optional[str] = None,
) -> tuple[str, str]:
    """Resolve this MCP session's default UmRT instance name.

    Priority:
      1. explicit argument
      2. env TWINCAT_UMRT_INSTANCE
      3. UmRT_CursorMCP_<8-char workspace hash>  (stable per workspace)
      4. UmRT_CursorMCP_p<pid>                   (last resort)

    Returns (instance_name, source) where source is env|workspace|pid|explicit.
    """
    if explicit and str(explicit).strip():
        name = _sanitize_instance_token(str(explicit).strip(), max_len=48)
        if name:
            return name, "explicit"

    env_name = (os.environ.get(_ENV_INSTANCE) or "").strip()
    if env_name:
        name = _sanitize_instance_token(env_name, max_len=48)
        if name:
            return name, "env"

    # Optional: force per-MCP-process isolation (orphans possible after restart)
    mode = (os.environ.get("TWINCAT_UMRT_SESSION_MODE") or "workspace").strip().lower()
    if mode == "pid":
        name = f"{MCP_INSTANCE_PREFIX}_p{os.getpid()}"
        return name[:40], "pid"

    ws_key, ws_src = _workspace_fingerprint()
    if not ws_key:
        name = f"{MCP_INSTANCE_PREFIX}_p{os.getpid()}"
        return name[:40], "pid"

    digest = hashlib.sha1(ws_key.encode("utf-8", errors="replace")).hexdigest()[:8]
    base = os.path.basename(ws_key.rstrip("\\/")) or "ws"
    hint = _sanitize_instance_token(base, max_len=12)
    if hint:
        name = f"{MCP_INSTANCE_PREFIX}_{hint}_{digest}"
    else:
        name = f"{MCP_INSTANCE_PREFIX}_{digest}"
    name = name[:40].rstrip("_")
    log.info(
        "UmRT session instance=%s (workspace fingerprint from %s)",
        name, ws_src,
    )
    return name, "workspace"


def resolve_twincat_root() -> Optional[str]:
    """Resolve TwinCAT 3.1 install root (ends without trailing slash preference)."""
    env = (os.environ.get("TWINCAT3DIR") or "").strip().strip('"')
    if env:
        root = os.path.normpath(env.rstrip("\\/"))
        if os.path.isdir(root):
            return root

    reg_root = _read_twincat_root_from_registry()
    if reg_root and os.path.isdir(reg_root):
        return reg_root

    for candidate in _FALLBACK_TC_ROOTS:
        if os.path.isdir(candidate):
            return candidate
    return None


def _read_twincat_root_from_registry() -> Optional[str]:
    try:
        import winreg
    except ImportError:
        return None

    keys = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Beckhoff\TwinCAT3\System"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Beckhoff\TwinCAT3\System"),
    )
    value_names = (
        "TwinCatDir", "TwinCATDir", "InstallDir", "InstallPath", "TcDir",
    )
    for hive, sub in keys:
        try:
            with winreg.OpenKey(hive, sub) as key:
                for name in value_names:
                    try:
                        val, _ = winreg.QueryValueEx(key, name)
                        if val and isinstance(val, str):
                            root = os.path.normpath(val.rstrip("\\/"))
                            # ConnectionProvider often points into System\ — trim
                            if root.lower().endswith("\\system"):
                                root = os.path.dirname(root)
                            if os.path.isdir(root):
                                return root
                    except OSError:
                        continue
                # Derive from ConnectionProvider path
                try:
                    val, _ = winreg.QueryValueEx(key, "ConnectionProvider")
                    if isinstance(val, str) and "TwinCAT" in val:
                        # ...\TwinCAT\3.1\System\foo.dll -> ...\TwinCAT\3.1
                        parts = os.path.normpath(val).split(os.sep)
                        for i, p in enumerate(parts):
                            if p.lower() == "3.1" and i > 0:
                                candidate = os.sep.join(parts[: i + 1])
                                if os.path.isdir(candidate):
                                    return candidate
                except OSError:
                    pass
        except OSError:
            continue
    return None


def resolve_umrt_bin(tc_root: Optional[str] = None) -> Optional[str]:
    root = tc_root or resolve_twincat_root()
    if not root:
        return None
    path = os.path.join(root, "Runtimes", "bin", _EXE_NAME)
    return path if os.path.isfile(path) else None


def resolve_template_path(tc_root: Optional[str] = None) -> Optional[str]:
    root = tc_root or resolve_twincat_root()
    if not root:
        return None
    path = os.path.join(root, "Runtimes", "UmRT_Template")
    return path if os.path.isdir(path) else None


def resolve_instances_root() -> str:
    return os.path.join(
        os.environ.get("ProgramData", r"C:\ProgramData"),
        "Beckhoff", "TwinCAT", "3.1", "Runtimes",
    )


def parse_ams_net_id_from_registry_xml(xml_path: str) -> str:
    """Parse AmsNetId BIN hex from TcRegistry.xml -> dotted decimal."""
    if not xml_path or not os.path.isfile(xml_path):
        return ""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        log.debug("TcRegistry parse failed: %s", exc)
        return ""

    for el in tree.iter():
        if el.tag != "Value":
            continue
        if el.attrib.get("Name") != "AmsNetId":
            continue
        if el.attrib.get("Type", "").upper() != "BIN":
            continue
        hex_str = (el.text or "").strip()
        return bin_hex_to_ams_net_id(hex_str)
    return ""


def bin_hex_to_ams_net_id(hex_str: str) -> str:
    """Convert e.g. C7042AFA0101 -> 199.4.42.250.1.1."""
    raw = re.sub(r"[^0-9A-Fa-f]", "", hex_str or "")
    if len(raw) < 12:
        return ""
    raw = raw[:12]
    try:
        parts = [str(int(raw[i : i + 2], 16)) for i in range(0, 12, 2)]
    except ValueError:
        return ""
    return ".".join(parts)


def _list_umrt_processes() -> list[dict[str, Any]]:
    """Return [{pid, name, cmdline}] for TcSystemServiceUm.exe."""
    procs: list[dict[str, Any]] = []
    try:
        import win32com.client  # type: ignore
        wmi = win32com.client.GetObject("winmgmts:")
        for p in wmi.ExecQuery(
            f"SELECT ProcessId, Name, CommandLine FROM Win32_Process "
            f"WHERE Name = '{_EXE_NAME}'"
        ):
            procs.append({
                "pid": int(p.ProcessId),
                "name": str(p.Name or ""),
                "cmdline": str(p.CommandLine or ""),
            })
        return procs
    except Exception as exc:
        log.debug("WMI process query failed: %s", exc)

    # Fallback: tasklist (no cmdline — weaker matching)
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {_EXE_NAME}", "/FO", "CSV", "/NH"],
            text=True,
            errors="ignore",
            timeout=10,
        )
        for line in out.splitlines():
            line = line.strip().strip('"')
            if not line or _EXE_NAME.lower() not in line.lower():
                continue
            # "TcSystemServiceUm.exe","1234","Session Name","Session#","Mem"
            parts = [x.strip().strip('"') for x in line.split('","')]
            if len(parts) >= 2:
                try:
                    procs.append({
                        "pid": int(parts[1]),
                        "name": parts[0],
                        "cmdline": "",
                    })
                except ValueError:
                    continue
    except Exception as exc:
        log.debug("tasklist fallback failed: %s", exc)
    return procs


def _match_instance_pid(instance: str, procs: Optional[list] = None) -> Optional[int]:
    """Find PID whose command line contains -n <instance>."""
    name = (instance or "").strip()
    if not name:
        return None
    procs = procs if procs is not None else _list_umrt_processes()
    needle_patterns = (
        f'-n "{name}"',
        f"-n '{name}'",
        f"-n {name}",
        f'-n"{name}"',
    )
    for p in procs:
        cmd = p.get("cmdline") or ""
        if not cmd:
            continue
        # Prefer exact -n token match
        if any(pat in cmd for pat in needle_patterns):
            return int(p["pid"])
        # Also match if window title form appears
        if f'"{name}"' in cmd and _EXE_NAME.lower() in cmd.lower():
            # avoid matching unrelated quoted paths — require -n nearby
            if re.search(rf'-n\s+"?{re.escape(name)}"?(?:\s|$)', cmd, re.I):
                return int(p["pid"])
    return None


def _terminate_pid(pid: int) -> bool:
    try:
        subprocess.check_call(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return True
    except Exception as exc:
        log.warning("taskkill PID %s failed: %s", pid, exc)
        try:
            import ctypes
            PROCESS_TERMINATE = 0x0001
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 1)
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
        except Exception as exc2:
            log.warning("TerminateProcess PID %s failed: %s", pid, exc2)
    return False


def inspect_instance_licenses(instance_path: str) -> dict[str, Any]:
    """Inspect license directory of an UmRT instance for .tclsp / .tclse / .xml files."""
    if not instance_path or not os.path.isdir(instance_path):
        return {
            "success": False,
            "licenses_ok": False,
            "missing_trial_license": True,
            "found_files": [],
            "message": f"Instance path not found: {instance_path}",
        }

    search_dirs = [
        os.path.join(instance_path, "3.1", "Target", "License"),
        os.path.join(instance_path, "Target", "License"),
        os.path.join(instance_path, "3.1", "Boot", "License"),
        os.path.join(instance_path, "Boot", "License"),
    ]

    found_files: list[str] = []
    for d in search_dirs:
        if os.path.isdir(d):
            try:
                for f in os.listdir(d):
                    if f.lower().endswith((".tclsp", ".tclse", ".xml")):
                        found_files.append(os.path.join(d, f))
            except Exception:
                pass

    if not found_files:
        return {
            "success": False,
            "licenses_ok": False,
            "missing_trial_license": True,
            "found_files": [],
            "message": "No active license files (.tclsp/.tclse) found in UmRT License directory",
        }

    detected_licenses: list[str] = []
    for fpath in found_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                matches = re.findall(r"(TC\d+|TF\d+)", content)
                for m in matches:
                    if m not in detected_licenses:
                        detected_licenses.append(m)
        except Exception:
            pass

    return {
        "success": True,
        "licenses_ok": True,
        "missing_trial_license": False,
        "found_files": [os.path.basename(f) for f in found_files],
        "detected_licenses": detected_licenses,
        "message": f"Found {len(found_files)} license file(s) with {len(detected_licenses)} license item(s)",
    }


class UmrtController:
    """High-level Usermode Runtime lifecycle helper."""

    def __init__(self, mcp_instance: Optional[str] = None):
        if mcp_instance and str(mcp_instance).strip():
            self.mcp_instance, self.mcp_instance_source = resolve_session_instance_name(
                mcp_instance
            )
        else:
            self.mcp_instance, self.mcp_instance_source = resolve_session_instance_name()

    def ensure_instance(self, name: Optional[str] = None) -> UmrtOpResult:
        """Create ProgramData instance from UmRT_Template if missing."""
        instance = (name or self.mcp_instance).strip()
        if not instance or any(c in instance for c in '\\/:*?"<>|'):
            return UmrtOpResult(
                success=False,
                instance=instance,
                message="Invalid instance name",
            )

        inst_root = resolve_instances_root()
        dest = os.path.join(inst_root, instance)
        start_bat = os.path.join(dest, "Start.bat")
        if os.path.isfile(start_bat):
            return UmrtOpResult(
                success=True,
                instance=instance,
                ams_net_id=parse_ams_net_id_from_registry_xml(
                    os.path.join(dest, "3.1", "TcRegistry.xml")
                ),
                created_instance=False,
                message=f"Instance already exists: {dest}",
            )

        template = resolve_template_path()
        bin_path = resolve_umrt_bin()
        if not template:
            return UmrtOpResult(
                success=False,
                instance=instance,
                message=(
                    "UmRT_Template not found. Install TC170x | TwinCAT 3 "
                    "Usermode Runtime (TwinCAT 4026+)."
                ),
            )
        if not bin_path:
            return UmrtOpResult(
                success=False,
                instance=instance,
                message=f"{_EXE_NAME} not found under TwinCAT Runtimes\\bin",
            )

        os.makedirs(inst_root, exist_ok=True)
        try:
            shutil.copytree(template, dest)
        except Exception as exc:
            return UmrtOpResult(
                success=False,
                instance=instance,
                message=f"Failed to copy template: {exc}",
            )

        if not os.path.isfile(start_bat):
            return UmrtOpResult(
                success=False,
                instance=instance,
                message=f"Template copy missing Start.bat: {dest}",
            )

        return UmrtOpResult(
            success=True,
            instance=instance,
            ams_net_id=parse_ams_net_id_from_registry_xml(
                os.path.join(dest, "3.1", "TcRegistry.xml")
            ),
            created_instance=True,
            message=f"Created instance from UmRT_Template: {dest}",
        )

    def list_instances(self) -> list[UmrtInstanceInfo]:
        root = resolve_instances_root()
        procs = _list_umrt_processes()
        result: list[UmrtInstanceInfo] = []
        if not os.path.isdir(root):
            return result

        for entry in sorted(os.listdir(root)):
            path = os.path.join(root, entry)
            if not os.path.isdir(path):
                continue
            start_bat = os.path.join(path, "Start.bat")
            if not os.path.isfile(start_bat):
                continue
            pid = _match_instance_pid(entry, procs)
            # Fallback when cmdline unavailable: any UmRT process counts only
            # for single-process ambiguity — skip weak match if multiple procs
            config_dir = os.path.join(path, "3.1")
            net_id = parse_ams_net_id_from_registry_xml(
                os.path.join(config_dir, "TcRegistry.xml")
            )
            result.append(UmrtInstanceInfo(
                name=entry,
                path=path,
                start_bat=start_bat,
                config_dir=config_dir if os.path.isdir(config_dir) else "",
                running=pid is not None,
                pid=pid,
                ams_net_id=net_id,
                is_mcp_instance=(entry == self.mcp_instance),
            ))
        return result

    def status(self) -> UmrtStatusResult:
        tc_root = resolve_twincat_root() or ""
        bin_path = resolve_umrt_bin(tc_root) or ""
        template = resolve_template_path(tc_root) or ""
        inst_root = resolve_instances_root()
        instances = self.list_instances()
        mcp = next(
            (i for i in instances if i.name == self.mcp_instance), None,
        )
        installed = bool(bin_path and template)
        msg_parts = []
        if installed:
            msg_parts.append("Usermode Runtime installed")
        else:
            msg_parts.append("Usermode Runtime not installed or incomplete")
        msg_parts.append(f"{len(instances)} instance(s)")
        if mcp and mcp.running:
            msg_parts.append(f"MCP instance running (pid={mcp.pid})")
        elif mcp:
            msg_parts.append("MCP instance present but stopped")
        else:
            msg_parts.append("MCP instance not created yet")

        return UmrtStatusResult(
            success=True,
            installed=installed,
            twincat_root=tc_root,
            bin_path=bin_path,
            template_path=template,
            instances_root=inst_root,
            mcp_instance=self.mcp_instance,
            mcp_instance_source=self.mcp_instance_source,
            mcp_running=bool(mcp and mcp.running),
            mcp_ams_net_id=(mcp.ams_net_id if mcp else ""),
            instances=[asdict(i) for i in instances],
            message=" | ".join(msg_parts),
        )

    def get_mcp_ams_net_id_if_running(self) -> str:
        """Return AmsNetId of running MCP instance, or empty string."""
        for inst in self.list_instances():
            if inst.name == self.mcp_instance and inst.running and inst.ams_net_id:
                return inst.ams_net_id
        return ""

    def check_licenses(self, instance: Optional[str] = None) -> dict[str, Any]:
        """Check if the given or default MCP UmRT instance has active license files."""
        inst_name = (instance or self.mcp_instance).strip()
        inst_root = resolve_instances_root()
        dest = os.path.join(inst_root, inst_name)
        return inspect_instance_licenses(dest)

    def start(
        self,
        instance: Optional[str] = None,
        confirm: bool = False,
        window_mode: str = "minimized",
    ) -> UmrtOpResult:
        """Start UmRT.

        window_mode:
          - ``minimized`` (default): Start.bat → console via ``start /min``
          - ``hidden``: launch TcSystemServiceUm.exe with CREATE_NO_WINDOW
            (no console UI; use COM twincat_start for Run — no interactive
            ``r``/``c`` keys)
        """
        if not confirm:
            return UmrtOpResult(
                success=False,
                instance=instance or self.mcp_instance,
                message=(
                    "Refused: set confirm=true to run twincat_umrt_start"
                ),
            )

        mode = (window_mode or "minimized").strip().lower()
        if mode not in ("minimized", "hidden"):
            return UmrtOpResult(
                success=False,
                instance=instance or self.mcp_instance,
                message="window_mode must be 'minimized' or 'hidden'",
            )

        instance = (instance or self.mcp_instance).strip()
        ensured = self.ensure_instance(instance)
        if not ensured.success:
            return ensured

        # Already running?
        pid = _match_instance_pid(instance)
        if pid:
            return UmrtOpResult(
                success=True,
                instance=instance,
                pid=pid,
                ams_net_id=ensured.ams_net_id,
                created_instance=ensured.created_instance,
                window_mode=mode,
                message=f"Already running (pid={pid})",
            )

        inst_dir = os.path.join(resolve_instances_root(), instance)
        start_bat = os.path.join(inst_dir, "Start.bat")
        if not os.path.isfile(start_bat):
            return UmrtOpResult(
                success=False,
                instance=instance,
                message=f"Start.bat not found: {start_bat}",
            )

        tc_root = resolve_twincat_root()
        env = os.environ.copy()
        if tc_root:
            # Start.bat expects TWINCAT3DIR with trailing backslash
            env["TWINCAT3DIR"] = tc_root.rstrip("\\/") + "\\"

        try:
            if mode == "hidden":
                exe = resolve_umrt_bin(tc_root)
                if not exe:
                    return UmrtOpResult(
                        success=False,
                        instance=instance,
                        created_instance=ensured.created_instance,
                        window_mode=mode,
                        message=f"{_EXE_NAME} not found — cannot use window_mode=hidden",
                    )
                # No console window; AmsNetId from instance registry (-i path)
                flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
                flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                subprocess.Popen(
                    [exe, "-t", "bin", "-i", "path", "-n", instance, "-c", r".\3.1"],
                    cwd=inst_dir,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )
            else:
                # Start.bat → `start ... /min` console (Beckhoff default)
                subprocess.Popen(
                    ["cmd.exe", "/c", "Start.bat"],
                    cwd=inst_dir,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        except Exception as exc:
            return UmrtOpResult(
                success=False,
                instance=instance,
                created_instance=ensured.created_instance,
                window_mode=mode,
                message=f"Failed to launch Usermode Runtime: {exc}",
            )

        # Wait for process to appear
        pid = None
        for _ in range(40):
            time.sleep(0.25)
            pid = _match_instance_pid(instance)
            if pid:
                break

        net_id = parse_ams_net_id_from_registry_xml(
            os.path.join(inst_dir, "3.1", "TcRegistry.xml")
        )
        if not pid:
            return UmrtOpResult(
                success=False,
                instance=instance,
                ams_net_id=net_id,
                created_instance=ensured.created_instance,
                window_mode=mode,
                message=(
                    "Launch succeeded but TcSystemServiceUm process "
                    f"for '{instance}' not detected within timeout"
                ),
            )

        extra = ""
        if mode == "hidden":
            extra = " (no console window — use twincat_start for Run)"
        return UmrtOpResult(
            success=True,
            instance=instance,
            pid=pid,
            ams_net_id=net_id,
            created_instance=ensured.created_instance,
            window_mode=mode,
            message=(
                f"Started {instance} (pid={pid}, net_id={net_id or '?'}, "
                f"window={mode}){extra}"
            ),
        )

    def stop(
        self,
        instance: Optional[str] = None,
        confirm: bool = False,
    ) -> UmrtOpResult:
        if not confirm:
            return UmrtOpResult(
                success=False,
                instance=instance or self.mcp_instance,
                message=(
                    "Refused: set confirm=true to run twincat_umrt_stop"
                ),
            )

        instance = (instance or self.mcp_instance).strip()
        pid = _match_instance_pid(instance)
        if not pid:
            return UmrtOpResult(
                success=True,
                instance=instance,
                message=f"Instance '{instance}' is not running",
            )

        if not _terminate_pid(pid):
            return UmrtOpResult(
                success=False,
                instance=instance,
                pid=pid,
                message=f"Failed to terminate pid={pid}",
            )

        # Confirm gone
        for _ in range(20):
            time.sleep(0.15)
            if _match_instance_pid(instance) is None:
                break

        return UmrtOpResult(
            success=True,
            instance=instance,
            pid=pid,
            message=f"Stopped {instance} (was pid={pid})",
        )


def status_to_dict(result: UmrtStatusResult) -> dict:
    return asdict(result)


def op_to_dict(result: UmrtOpResult) -> dict:
    return asdict(result)
