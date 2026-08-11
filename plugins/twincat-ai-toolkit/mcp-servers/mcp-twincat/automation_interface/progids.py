"""TcXaeShell ProgID discovery and version mapping."""
from typing import Optional
import sys


_PROG_ID_PREFIX = "TcXaeShell.DTE."
_DEFAULT_PROG_ID = f"{_PROG_ID_PREFIX}17.0"
PROG_ID = _DEFAULT_PROG_ID

_XAE_VERSION_ALIASES = {
    "4026": f"{_PROG_ID_PREFIX}17.0",
    "4024": f"{_PROG_ID_PREFIX}15.0",
    "17.0": f"{_PROG_ID_PREFIX}17.0",
    "15.0": f"{_PROG_ID_PREFIX}15.0",
    "17": f"{_PROG_ID_PREFIX}17.0",
    "15": f"{_PROG_ID_PREFIX}15.0",
}

_PROG_ID_TO_TC_VERSION = {
    f"{_PROG_ID_PREFIX}17.0": "4026",
    f"{_PROG_ID_PREFIX}15.0": "4024",
}


def _tai():
    """Late-bound facade module (keeps unittest patches working)."""
    return sys.modules["twincat_automation_interface"]


def _prog_id_version_key(prog_id: str) -> tuple[int, ...]:
    suffix = prog_id[len(_PROG_ID_PREFIX):] if prog_id.startswith(_PROG_ID_PREFIX) else prog_id
    parts: list[int] = []
    for piece in suffix.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(-1)
    return tuple(parts)


def _discover_registered_prog_ids() -> list[str]:
    """Return registered TcXaeShell DTE ProgIDs, newest VS version first."""
    import winreg

    found: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "") as root:
            idx = 0
            while True:
                try:
                    name = winreg.EnumKey(root, idx)
                    idx += 1
                except OSError:
                    break
                if not name.startswith(_PROG_ID_PREFIX):
                    continue
                try:
                    winreg.OpenKey(
                        winreg.HKEY_CLASSES_ROOT, f"{name}\\CLSID"
                    ).Close()
                    found.append(name)
                except OSError:
                    continue
    except OSError:
        pass

    found.sort(key=_prog_id_version_key, reverse=True)
    return found


def _normalize_xae_version(version: Optional[str]) -> Optional[str]:
    """Map a user-facing XAE version string to a registered ProgID."""
    if version is None:
        return None
    raw = str(version).strip()
    if not raw:
        return None

    registered = _tai()._discover_registered_prog_ids()
    lower = raw.lower()

    if lower in {p.lower() for p in registered}:
        for p in registered:
            if p.lower() == lower:
                return p

    alias = _XAE_VERSION_ALIASES.get(lower)
    if alias and alias in registered:
        return alias
    if alias:
        return alias

    for p in registered:
        if p.lower().endswith("." + lower) or p[len(_PROG_ID_PREFIX):].lower() == lower:
            return p

    raise ValueError(
        f"Unknown XAE version '{version}'. "
        f"Use 4024, 4026, 15.0, 17.0, or a ProgID. "
        f"Registered: {registered or ['(none)']}"
    )


def _tc_version_label(prog_id: Optional[str]) -> str:
    if not prog_id:
        return ""
    return _PROG_ID_TO_TC_VERSION.get(prog_id, prog_id)


def _resolve_prog_id(preferred: Optional[str] = None) -> str:
    """Pick the best TcXaeShell ProgID for COM access."""
    tai = _tai()
    registered = tai._discover_registered_prog_ids()
    if preferred:
        return preferred

    for prog_id in registered:
        try:
            tai.win32com.client.GetActiveObject(prog_id)
            return prog_id
        except Exception:
            continue

    if registered:
        return registered[0]
    return _DEFAULT_PROG_ID
