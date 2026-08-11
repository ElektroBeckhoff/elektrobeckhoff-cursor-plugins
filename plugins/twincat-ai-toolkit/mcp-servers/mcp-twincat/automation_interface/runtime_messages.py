"""Collect and classify TwinCAT runtime / activate messages for MCP agents."""

from __future__ import annotations

import re


# Activate / boot failure phrases (not always severity=error in TwinCAT output)
_ACTIVATE_CANCEL_RX = re.compile(
    r"activating\s+configuration\s+canceled"
    r"|activate\s+configuration\s+cancel"
    r"|value\s+out\s+of\s+range"
    r"|aktivierung.*(abgebrochen|fehlgeschlagen)"
    r"|konfiguration\s+aktivieren.*(abgebrochen|fehlgeschlagen)",
    re.I,
)

_BOOT_WRITTEN_RX = re.compile(
    r"boot\s*project|bootprojekt|save\s+to\s+registry|registry\s+written",
    re.I,
)

# Patterns that should block the agent and often need user attention
_FINDING_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "page_fault",
        "error",
        re.compile(r"page\s*fault|speicherzugriffsfehler|access\s*violation", re.I),
    ),
    (
        "fatal",
        "error",
        re.compile(r"fatal(en)?\s*fehler|fatal\s*error|zielsystem meldet", re.I),
    ),
    (
        "license",
        "error",
        re.compile(
            r"license\s+not\s+found|license\s+violation|checking\s+twincat\s+licenses"
            r"|lizenz.*(fehlt|nicht)",
            re.I,
        ),
    ),
    (
        "safeop_aborted",
        "error",
        re.compile(
            r"SAFEOP|AdsError:\s*1823|0x71f|device aborted the action"
            r"|failed to connect to network adapter",
            re.I,
        ),
    ),
    (
        "ads_error",
        "error",
        re.compile(r"AdsError:\s*\d+|ADS\s*ERROR", re.I),
    ),
    (
        "exception",
        "error",
        re.compile(r"\bexception\b|ausnahmefehler|unhandled", re.I),
    ),
]


def classify_runtime_text(*parts: str) -> list[dict]:
    """Return unique findings {id, severity, matched_line}."""
    text = "\n".join(p for p in parts if p)
    if not text.strip():
        return []
    findings: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        for fid, severity, rx in _FINDING_RULES:
            if not rx.search(line_s):
                continue
            key = f"{fid}|{line_s[:160]}"
            if key in seen:
                continue
            seen.add(key)
            findings.append({
                "id": fid,
                "severity": severity,
                "matched_line": line_s[:400],
            })
    return findings


def tail_text(text: str, max_chars: int = 12000) -> str:
    t = text or ""
    if len(t) <= max_chars:
        return t
    return t[-max_chars:]


def text_since_baseline(text: str, baseline_len: int) -> str:
    """Return text appended after a prior length snapshot (window since activate)."""
    t = text or ""
    if baseline_len <= 0:
        return t
    if baseline_len >= len(t):
        # Pane may have been cleared/rotated — treat full text as incomplete window
        return t
    return t[baseline_len:]


def looks_like_activate_canceled(*parts: str) -> bool:
    blob = "\n".join(p for p in parts if p)
    return bool(blob and _ACTIVATE_CANCEL_RX.search(blob))


def looks_like_boot_written(*parts: str) -> bool:
    blob = "\n".join(p for p in parts if p)
    return bool(blob and _BOOT_WRITTEN_RX.search(blob))


def severity_summary(findings: list[dict]) -> dict[str, int]:
    error_count = 0
    warning_count = 0
    for f in findings or []:
        sev = (f.get("severity") or "").lower()
        if sev == "error":
            error_count += 1
        elif sev == "warning":
            warning_count += 1
    return {"error_count": error_count, "warning_count": warning_count}


def infer_build_outcome(*parts: str) -> str:
    """Best-effort build_outcome: success | failed | warning | unknown."""
    blob = "\n".join(p for p in parts if p).lower()
    if not blob.strip():
        return "unknown"
    if looks_like_activate_canceled(blob):
        return "failed"
    if re.search(r"\b\d+\s+fehler\b|\berror\(s\)\b|\bbuild\s+failed\b", blob):
        return "failed"
    if re.search(r"\bwrn\b|\bwarning\(s\)\b|\b\d+\s+warnung", blob):
        return "warning"
    if re.search(r"erfolgreich|succeeded|\b0\s+error", blob):
        return "success"
    return "unknown"
