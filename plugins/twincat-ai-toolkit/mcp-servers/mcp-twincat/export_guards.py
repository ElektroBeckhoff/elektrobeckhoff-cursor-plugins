"""Guards for twincat_export_library (version / library / ambiguous plcproj)."""
from __future__ import annotations

import os
from typing import Any, Optional

from mcp_errors import error_result


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path)) if path else ""


def validate_export_target(
    *,
    plcproj_path: str,
    info: dict[str, Any],
    output_dir: str,
    plcproj_from_bridge: str = "",
    plcproj_explicit: bool = False,
    force: bool = False,
) -> Optional[dict[str, Any]]:
    """Return an error dict if export must be refused, else None.

    Always-safe echo fields are included on refusal.
    """
    title = info.get("title") or info.get("name") or "Unknown"
    version = (info.get("version") or "0.0.0.0").strip() or "0.0.0.0"
    echo = {
        "resolved_plcproj_path": plcproj_path,
        "project_title": title,
        "project_version": version,
        "output_dir": output_dir,
        "is_library_project": bool(info.get("is_library_project")),
        "project_category": info.get("project_category") or "",
    }

    bridge = _norm(plcproj_from_bridge)
    resolved = _norm(plcproj_path)

    # Ambiguous: open sample/session plcproj is 0.0.0.0 and caller did not pin path
    if (
        not plcproj_explicit
        and bridge
        and resolved == bridge
        and version == "0.0.0.0"
        and not force
    ):
        return error_result(
            "plcproj_ambiguous",
            (
                "Export refused: open session .plcproj has ProjectVersion 0.0.0.0 "
                "(likely a sample/app). Pass plcproj_path to the library project "
                "explicitly, or force=true to override."
            ),
            extra={
                **echo,
                "example_next_call": {
                    "tool": "twincat_export_library",
                    "plcproj_path": "<path-to-library.plcproj>",
                    "force": False,
                },
            },
        )

    if version == "0.0.0.0" and not force:
        return error_result(
            "export_invalid_project",
            (
                "Export refused: ProjectVersion is 0.0.0.0 (sample/app placeholder). "
                "Pass the library .plcproj via plcproj_path, or force=true."
            ),
            extra=echo,
        )

    is_lib = info.get("is_library_project")
    if is_lib is False and not force:
        return error_result(
            "export_invalid_project",
            (
                "Export refused: project does not look like a TwinCAT PLC library "
                f"(category={echo['project_category']!r}). "
                "Pass a library .plcproj or force=true."
            ),
            extra=echo,
        )

    return None


def export_echo_fields(
    *,
    plcproj_path: str,
    info: dict[str, Any],
    output_dir: str,
) -> dict[str, Any]:
    return {
        "resolved_plcproj_path": plcproj_path,
        "project_title": info.get("title") or info.get("name") or "Unknown",
        "project_version": (info.get("version") or "0.0.0.0").strip() or "0.0.0.0",
        "output_dir": output_dir,
        "is_library_project": bool(info.get("is_library_project")),
        "project_category": info.get("project_category") or "",
    }
