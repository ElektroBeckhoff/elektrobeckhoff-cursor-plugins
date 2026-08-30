"""Lossless file I/O with encoding, BOM, and CRLF preservation."""
from __future__ import annotations

import codecs
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

from .types import TcXmlDocument, XmlEncodingInfo


@dataclass
class WriteSummary:
    """Outcome of an atomic write operation."""
    path: str
    written: bool = False
    original_hash: str = ""
    new_hash: str = ""
    backup_path: str = ""
    error: Optional[str] = None


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hash of byte buffer."""
    return hashlib.sha256(data).hexdigest()


def detect_encoding_info(raw_bytes: bytes) -> Tuple[str, XmlEncodingInfo]:
    """Detect encoding, BOM, line ending, and XML declaration from raw file bytes."""
    has_bom = False
    encoding = "utf-8"
    decoded_text = ""

    if raw_bytes.startswith(codecs.BOM_UTF8):
        has_bom = True
        raw_to_decode = raw_bytes[len(codecs.BOM_UTF8):]
        encoding = "utf-8"
        decoded_text = raw_to_decode.decode("utf-8", errors="replace")
    elif raw_bytes.startswith(codecs.BOM_UTF16_LE):
        has_bom = True
        encoding = "utf-16-le"
        decoded_text = raw_bytes[len(codecs.BOM_UTF16_LE):].decode("utf-16-le", errors="replace")
    else:
        for enc in ("utf-8", "utf-8-sig", "latin-1", "windows-1252"):
            try:
                decoded_text = raw_bytes.decode(enc)
                encoding = "utf-8" if enc == "utf-8-sig" else enc
                if enc == "utf-8-sig" and raw_bytes.startswith(codecs.BOM_UTF8):
                    has_bom = True
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            decoded_text = raw_bytes.decode("utf-8", errors="replace")
            encoding = "utf-8"

    # Detect line ending
    line_ending = "\r\n" if "\r\n" in decoded_text else "\n"

    # Extract XML declaration
    xml_decl = '<?xml version="1.0" encoding="utf-8"?>'
    if decoded_text.startswith("<?xml"):
        decl_end = decoded_text.find("?>")
        if decl_end >= 0:
            xml_decl = decoded_text[: decl_end + 2]

    info = XmlEncodingInfo(
        encoding=encoding,
        has_bom=has_bom,
        line_ending=line_ending,
        xml_declaration=xml_decl,
    )
    return decoded_text, info


def encode_document(text: str, encoding_info: XmlEncodingInfo) -> bytes:
    """Encode string back to bytes preserving exact line endings, BOM and encoding."""
    # Standardize line endings according to encoding_info
    target_le = encoding_info.line_ending
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if target_le == "\r\n":
        normalized = normalized.replace("\n", "\r\n")

    enc = encoding_info.encoding or "utf-8"
    encoded = normalized.encode(enc, errors="replace")

    if encoding_info.has_bom and enc.lower() in ("utf-8", "utf_8"):
        return codecs.BOM_UTF8 + encoded

    return encoded


def read_file_lossless(path: Union[str, Path]) -> Tuple[str, XmlEncodingInfo]:
    """Read a file and detect all encoding/format metadata."""
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")

    raw_bytes = p.read_bytes()
    return detect_encoding_info(raw_bytes)


def write_file_safe(
    path: Union[str, Path],
    content: bytes,
    *,
    backup: bool = True,
    delete_backup_on_success: bool = True,
) -> WriteSummary:
    """Atomically write content to file with hash check, backup, and rollback on error."""
    target = Path(path).resolve()
    summary = WriteSummary(path=str(target))

    if not target.parent.exists():
        summary.error = f"Parent directory does not exist: {target.parent}"
        return summary

    original_hash = ""
    if target.exists():
        if not os.access(target, os.W_OK):
            summary.error = f"File is read-only: {target}"
            return summary
        original_bytes = target.read_bytes()
        original_hash = compute_sha256(original_bytes)
        summary.original_hash = original_hash

    new_hash = compute_sha256(content)
    summary.new_hash = new_hash

    if original_hash == new_hash:
        summary.written = False
        return summary

    backup_path = ""
    try:
        if backup and target.exists():
            backup_path = str(target) + ".bak"
            shutil.copy2(str(target), backup_path)
            summary.backup_path = backup_path

        fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=str(target.parent))
        try:
            os.write(fd, content)
            os.close(fd)
            os.replace(tmp_path, str(target))
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

        verify_hash = compute_sha256(target.read_bytes())
        if verify_hash != new_hash:
            if backup_path and os.path.exists(backup_path):
                os.replace(backup_path, str(target))
            summary.error = "Hash verification failed after write"
            return summary

        if delete_backup_on_success and backup_path and os.path.exists(backup_path):
            try:
                os.unlink(backup_path)
            except OSError:
                pass
            summary.backup_path = ""

        summary.written = True
        return summary

    except OSError as e:
        if backup_path and os.path.exists(backup_path):
            try:
                os.replace(backup_path, str(target))
            except OSError:
                pass
        summary.error = f"Write failed: {e}"
        return summary


def save_document_lossless(
    doc: TcXmlDocument,
    path: Optional[Union[str, Path]] = None,
    *,
    backup: bool = True,
    delete_backup_on_success: bool = True,
) -> WriteSummary:
    """Encode and safely write a TcXmlDocument back to disk."""
    target_path = Path(path).resolve() if path else doc.file_path
    if not target_path:
        raise ValueError("Cannot save document without a valid file_path.")

    content_bytes = encode_document(doc.raw_text, doc.encoding_info)
    return write_file_safe(
        target_path,
        content_bytes,
        backup=backup,
        delete_backup_on_success=delete_backup_on_success,
    )
