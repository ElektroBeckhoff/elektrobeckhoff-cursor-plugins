"""XAE modal dialog enumeration and auto-dismiss."""
from __future__ import annotations

import glob
import logging
import os
import re
import sys
import time
from dataclasses import asdict
from typing import Optional



log = logging.getLogger("twincat-mcp")


def _tai():
    return sys.modules["twincat_automation_interface"]


class DialogOpsMixin:
    # --------------- Modal dialog auto-dismiss ---------------

    _SAFE_DIALOG_PATTERNS = [
        "modified outside the environment",  # EN: XAE file-change dialog
        "file has been modified outside",    # EN: alternate wording
        "modified outside of twincat",       # EN: TwinCAT-specific variant
        "außerhalb der umgebung geändert",   # DE: XAE file-change dialog
        "außerhalb von twincat xae",         # DE: TwinCAT-specific variant
        "datei neu laden",                   # DE: "Datei neu laden?" prompt
    ]

    _POLL_IDLE_S = 0.5
    _POLL_BURST_S = 0.15

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

                dialog_texts = []

                def enum_children(child_hwnd, _):
                    if _tai().win32gui.GetClassName(child_hwnd) == "Static":
                        text = _tai().win32gui.GetWindowText(child_hwnd)
                        if text:
                            dialog_texts.append(text.lower())
                    return True

                try:
                    _tai().win32gui.EnumChildWindows(hwnd, enum_children, None)
                except Exception:
                    return True

                full_text = " ".join(dialog_texts)
                matched = [
                    p for p in self._SAFE_DIALOG_PATTERNS if p in full_text
                ]
                found.append({
                    "hwnd": int(hwnd),
                    "title": title,
                    "text": full_text[:200],
                    "auto_dismissable": bool(matched),
                    "matched_pattern": matched[0] if matched else "",
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

        Runs alongside every COM call to prevent the STA thread from
        getting stuck on a modal dialog (e.g. "project modified outside
        of TwinCAT XAE -- reload?").  Only dismisses dialogs whose text
        matches a known safe pattern.

        When multiple files are modified, XAE shows one dialog per file
        in sequence.  After a successful dismiss the worker switches to
        a fast burst-poll so that the whole queue is cleared quickly.
        """
        if not _tai().HAS_WIN32GUI:
            return

        IDYES = 6  # MessageBox button ID for "Yes"/"Ja"

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

