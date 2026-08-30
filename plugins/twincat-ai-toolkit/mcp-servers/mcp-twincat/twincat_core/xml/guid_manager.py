"""GUID management and validation for TwinCAT3 XML objects."""
from __future__ import annotations

import re
import uuid
from typing import Optional, Set

RE_GUID = re.compile(
    r"\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}"
)
RE_GUID_PLAIN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
RE_XML_ID_ATTR = re.compile(r'Id="(\{?[0-9a-fA-F\-]+\}?)"', re.IGNORECASE)

_KNOWN_FAKE_PREFIXES: Set[str] = {
    "a1b2c3d4", "b2c3d4e5", "c3d4e5f6", "d4e5f6a7", "e4f5a6b7", "f5a6b7c8",
    "12345678", "abcdef01", "abcdef12", "01234567", "89abcdef",
}

_HEX_SEQ = "0123456789abcdef"


def is_valid_guid(value: str) -> bool:
    """Check whether value is a valid GUID (with or without braces)."""
    t = value.strip().strip("{}")
    try:
        uuid.UUID(t)
        return True
    except (ValueError, AttributeError):
        return False


def is_fake_ai_guid(value: str) -> bool:
    """Detect AI-generated fake GUIDs that have obvious non-random patterns.

    Checks both hyphenated structure and 32 hex-digit sequence.
    """
    t = value.strip().strip("{}").lower()
    try:
        uuid.UUID(t)
    except (ValueError, AttributeError):
        return False

    hex_only = t.replace("-", "")
    if len(hex_only) != 32:
        return False

    # 5+ consecutive identical hex digits
    if re.search(r"(.)\1{4,}", hex_only):
        return True

    # 6+ consecutive ascending hex digits
    asc_run = 1
    for i in range(1, len(hex_only)):
        prev_idx = _HEX_SEQ.index(hex_only[i - 1])
        curr_idx = _HEX_SEQ.index(hex_only[i])
        if curr_idx == prev_idx + 1:
            asc_run += 1
            if asc_run >= 6:
                return True
        else:
            asc_run = 1

    # 6+ consecutive descending hex digits
    desc_run = 1
    for i in range(1, len(hex_only)):
        prev_idx = _HEX_SEQ.index(hex_only[i - 1])
        curr_idx = _HEX_SEQ.index(hex_only[i])
        if curr_idx == prev_idx - 1:
            desc_run += 1
            if desc_run >= 6:
                return True
        else:
            desc_run = 1

    # Low entropy: fewer than 6 distinct hex digits in the entire GUID
    if len(set(hex_only)) < 6:
        return True

    segments = t.split("-")
    if len(segments) != 5:
        return False

    # Known fake prefixes (first segment, 8 hex digits)
    if segments[0] in _KNOWN_FAKE_PREFIXES:
        return True

    # Counter suffix: last segment (12 hex) is 75%+ one digit with small counter
    last = segments[4]
    if len(last) == 12:
        from collections import Counter
        counts = Counter(last)
        most_common_char, most_common_count = counts.most_common(1)[0]
        if most_common_count >= 9:
            return True

    # Segment-sequence: 2+ segments are ascending hex sequences
    seq_count = 0
    for seg in segments:
        if len(seg) >= 4 and seg in _HEX_SEQ:
            seq_count += 1
    if seq_count >= 2:
        return True

    # Mirrored adjacent segments
    for i in range(len(segments) - 1):
        if len(segments[i]) >= 4 and segments[i] == segments[i + 1][::-1]:
            return True

    return False


def normalize_guid(value: str, braces: bool = True) -> str:
    """Normalize a GUID string to canonical lowercase, optionally with braces."""
    t = value.strip().strip("{}")
    norm = str(uuid.UUID(t)).lower()
    return f"{{{norm}}}" if braces else norm


def generate_guid(braces: bool = True) -> str:
    """Generate a new random UUID v4 string formatted as a TwinCAT GUID."""
    norm = str(uuid.uuid4()).lower()
    return f"{{{norm}}}" if braces else norm


def extract_all_guids(xml_text: str) -> list[str]:
    """Extract all valid GUID strings found in Id="..." attributes."""
    guids: list[str] = []
    for m in RE_XML_ID_ATTR.finditer(xml_text):
        val = m.group(1)
        if is_valid_guid(val):
            guids.append(normalize_guid(val, braces=True))
    return guids


def find_duplicate_guids(xml_text: str) -> list[str]:
    """Find any duplicate GUID values appearing in Id="..." attributes."""
    seen: set[str] = set()
    dups: list[str] = []
    for g in extract_all_guids(xml_text):
        if g in seen:
            if g not in dups:
                dups.append(g)
        else:
            seen.add(g)
    return dups


def regenerate_all_guids(xml_text: str) -> str:
    """Replace all GUIDs in Id="{...}" attributes with fresh random UUID v4 GUIDs."""
    return RE_XML_ID_ATTR.sub(lambda m: f'Id="{generate_guid(braces=True)}"', xml_text)

