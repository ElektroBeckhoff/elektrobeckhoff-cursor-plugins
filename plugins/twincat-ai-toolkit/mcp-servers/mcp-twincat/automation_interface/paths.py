"""Path helpers for TwinCAT Automation Interface."""
import os


def _canonical_path(p: str) -> str:
    """Canonical, case-folded absolute path (resolves symlinks, junctions, subst, and 8.3 short names)."""
    if not p:
        return ""
    try:
        resolved = os.path.realpath(p)
    except (OSError, ValueError):
        resolved = os.path.abspath(p)

    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(512)
            res = ctypes.windll.kernel32.GetLongPathNameW(resolved, buf, len(buf))
            if 0 < res < len(buf):
                resolved = buf.value
            elif res >= len(buf):
                buf = ctypes.create_unicode_buffer(res + 1)
                res2 = ctypes.windll.kernel32.GetLongPathNameW(resolved, buf, len(buf))
                if res2 > 0:
                    resolved = buf.value
        except Exception:
            pass

    return os.path.normcase(resolved)

