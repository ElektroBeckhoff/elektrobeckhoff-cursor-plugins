"""XAE modal dialog enumeration and auto-dismiss."""
from __future__ import annotations

import logging
import re
import sys
import threading
import time
from typing import Optional

from results import DismissSafeDialogsResult


log = logging.getLogger("twincat-mcp")

# Caps for explicit idle dismiss (twincat_dismiss_safe_dialogs).
_DISMISS_MAX_COUNT = 20
_DISMISS_MAX_S = 10.0
_DISMISS_BURST_S = 0.15


def _tai():
    return sys.modules["twincat_automation_interface"]


class DialogOpsMixin:
    # --------------- Modal dialog auto-dismiss ---------------

    # Substrings matched against normalized (lower, collapsed whitespace) dialog
    # text. TwinCAT/VS wording differs by version and language — keep broad but
    # still specific to the external-file-change / reload prompt.
    _SAFE_DIALOG_PATTERNS = [
        # EN — VS / TcXaeShell file-change (4024 often says "changed", not "modified")
        "file has been changed outside",
        "file has been modified outside",
        "changed outside the environment",
        "modified outside the environment",
        "modified outside of twincat",
        "outside the environment",  # broad EN anchor for reload prompt
        # DE
        "außerhalb der umgebung geändert",
        "ausserhalb der umgebung geändert",  # ae spelling
        "außerhalb von twincat xae",
        "außerhalb der umgebung",
        "datei neu laden",
    ]

    _POLL_IDLE_S = 0.5
    _POLL_BURST_S = 0.15

    # Child classes that commonly carry MessageBox / XAE dialog body text.
    _DIALOG_TEXT_CLASSES = frozenset({
        "Static",
        "Button",  # sometimes "Yes"/"Ja" only; harmless for our patterns
        "RichEdit20W",
        "RichEdit20A",
        "Edit",
    })

    def _normalize_dialog_text(self, text: str) -> str:
        """Lowercase and collapse whitespace/newlines for stable matching."""
        if not text:
            return ""
        return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip().lower()

    def _read_dialog_text(self, hwnd) -> str:
        """Best-effort body text from a ``#32770`` dialog.

        TwinCAT puts the path and the English/German sentence into one or more
        ``Static`` children (sometimes split). Relying on a single control or
        only the first 200 chars for matching is unsafe — collect all useful
        child text, then normalize.
        """
        tai = _tai()
        parts: list[str] = []

        def enum_children(child_hwnd, _):
            try:
                cls = tai.win32gui.GetClassName(child_hwnd) or ""
                # Prefer known text hosts; also accept any non-empty child text
                # (covers uncommon wrappers) except the dialog chrome we skip.
                text = tai.win32gui.GetWindowText(child_hwnd) or ""
                if not text.strip():
                    return True
                if cls in self._DIALOG_TEXT_CLASSES or cls.startswith("Static"):
                    parts.append(text)
                elif cls not in ("#32770", "ScrollBar"):
                    # Fallback: unknown class with text (e.g. custom label)
                    parts.append(text)
            except Exception:
                pass
            return True

        try:
            tai.win32gui.EnumChildWindows(hwnd, enum_children, None)
        except Exception as exc:
            log.debug("EnumChildWindows for dialog %s failed: %s", hwnd, exc)

        if not parts:
            # Last resort: dialog window text (usually just "TcXaeShell")
            try:
                top = tai.win32gui.GetWindowText(hwnd) or ""
                if top:
                    parts.append(top)
            except Exception:
                pass

        return self._normalize_dialog_text(" ".join(parts))

    def _match_safe_dialog_pattern(self, full_text: str) -> str:
        """Return first matching safe pattern, or empty string."""
        if not full_text:
            return ""
        for pattern in self._SAFE_DIALOG_PATTERNS:
            if pattern in full_text:
                return pattern
        return ""

    def _enumerate_xae_dialogs(self) -> list[dict]:
        """Return visible TcXaeShell ``#32770`` dialogs (read-only).

        Each entry: ``hwnd``, ``title``, ``text``, ``auto_dismissable``,
        ``matched_pattern``. Used by ``twincat_status`` and the dismiss
        worker. Does not click any buttons.
        """
        if not _tai().HAS_WIN32GUI:
            return []

        found: list[dict] = []

        def enum_cb(hwnd, _):
            try:
                if not _tai().win32gui.IsWindowVisible(hwnd):
                    return True
                title = _tai().win32gui.GetWindowText(hwnd)
                if title != "TcXaeShell":
                    return True
                if _tai().win32gui.GetClassName(hwnd) != "#32770":
                    return True

                full_text = self._read_dialog_text(hwnd)
                matched = self._match_safe_dialog_pattern(full_text)
                found.append({
                    "hwnd": int(hwnd),
                    "title": title,
                    "text": full_text[:240],
                    "auto_dismissable": bool(matched),
                    "matched_pattern": matched,
                })
            except Exception:
                pass
            return True

        try:
            _tai().win32gui.EnumWindows(enum_cb, None)
        except Exception as exc:
            log.debug("EnumWindows for XAE dialogs failed: %s", exc)
        return found

    def _dialog_dismiss_worker(self, stop_event: threading.Event):
        """Background worker that auto-dismisses known XAE modal dialogs.

        Runs for the duration of each ``_call_sta`` COM call (not while MCP is
        idle). Prevents the STA thread from sticking on a modal dialog
        (e.g. "file has been changed outside the environment — reload?").
        Only dismisses dialogs whose text matches a known safe pattern.

        When multiple files are modified, XAE shows one dialog per file
        in sequence.  After a successful dismiss the worker switches to
        a fast burst-poll so that the whole queue is cleared quickly.
        """
        if not _tai().HAS_WIN32GUI:
            return

        IDYES = 6  # MessageBox button ID for "Yes"/"Ja" (reload)

        while not stop_event.is_set():
            dismissed_any = False
            try:
                for dlg in self._enumerate_xae_dialogs():
                    if not dlg.get("auto_dismissable"):
                        continue
                    hwnd = dlg["hwnd"]
                    pattern = dlg.get("matched_pattern", "")
                    text = dlg.get("text", "")[:120]
                    _tai().win32gui.PostMessage(
                        hwnd, _tai().win32con.WM_COMMAND, IDYES, 0,
                    )
                    log.warning(
                        "Auto-dismissed TcXaeShell dialog (hwnd=%s, "
                        "pattern='%s', text='%s')", hwnd, pattern, text,
                    )
                    self._dismissed_dialogs.append(
                        f"[{pattern}] {text}"
                    )
                    dismissed_any = True
            except Exception as exc:
                log.debug("Dialog watcher error: %s", exc)

            delay = self._POLL_BURST_S if dismissed_any else self._POLL_IDLE_S
            stop_event.wait(delay)

    def dismiss_safe_dialogs(self) -> DismissSafeDialogsResult:
        """Dismiss idle reload prompts (Yes/Ja) — fills the STA-worker gap.

        Call when ``twincat_status.blocking_dialogs`` shows
        ``auto_dismissable=true``. Does not require an active ``_call_sta``.
        """
        if not _tai().HAS_WIN32GUI:
            return DismissSafeDialogsResult(
                success=False,
                message="win32gui not available — cannot dismiss dialogs",
            )

        IDYES = 6
        dismissed: list[str] = []
        deadline = time.time() + _DISMISS_MAX_S
        while (
            len(dismissed) < _DISMISS_MAX_COUNT
            and time.time() < deadline
        ):
            found_any = False
            for dlg in self._enumerate_xae_dialogs():
                if not dlg.get("auto_dismissable"):
                    continue
                hwnd = dlg["hwnd"]
                pattern = dlg.get("matched_pattern", "")
                text = dlg.get("text", "")[:120]
                try:
                    _tai().win32gui.PostMessage(
                        hwnd, _tai().win32con.WM_COMMAND, IDYES, 0,
                    )
                except Exception as exc:
                    log.debug("PostMessage dismiss hwnd=%s: %s", hwnd, exc)
                    continue
                entry = f"[{pattern}] {text}"
                dismissed.append(entry)
                if not hasattr(self, "_dismissed_dialogs"):
                    self._dismissed_dialogs = []
                self._dismissed_dialogs.append(entry)
                found_any = True
                log.warning(
                    "dismiss_safe_dialogs: hwnd=%s pattern='%s' text='%s'",
                    hwnd, pattern, text,
                )
                if len(dismissed) >= _DISMISS_MAX_COUNT:
                    break
            if not found_any:
                break
            time.sleep(_DISMISS_BURST_S)

        remaining = [
            d for d in self._enumerate_xae_dialogs()
            if not d.get("auto_dismissable")
        ]
        still_auto = [
            d for d in self._enumerate_xae_dialogs()
            if d.get("auto_dismissable")
        ]
        remaining_blocking = remaining + still_auto
        if dismissed and not remaining_blocking:
            msg = (
                f"Dismissed {len(dismissed)} safe reload dialog(s). "
                "Retry the original MCP call once."
            )
        elif dismissed and remaining_blocking:
            msg = (
                f"Dismissed {len(dismissed)} dialog(s); "
                f"{len(remaining_blocking)} still blocking — "
                "if auto_dismissable=false, tell the user; else call again."
            )
        elif remaining_blocking:
            msg = (
                f"{len(remaining_blocking)} blocking dialog(s) remain "
                "(none auto-dismissable). Tell the user the dialog text."
            )
        else:
            msg = "No TcXaeShell reload dialogs found"
        return DismissSafeDialogsResult(
            success=True,
            dismissed_count=len(dismissed),
            dismissed=dismissed,
            remaining_blocking=remaining_blocking,
            message=msg,
        )
