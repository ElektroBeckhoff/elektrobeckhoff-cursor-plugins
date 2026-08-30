"""Surgical patcher for TwinCAT XML documents.

Performs point-in-time substring replacements on CDATA spans without
re-serializing the surrounding XML tree, preserving comments, formatting,
and unknown tags byte-for-byte.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence, Tuple

from .types import CdataKind, CdataSpan, TcXmlDocument


def patch_cdata_span(doc: TcXmlDocument, span: CdataSpan, new_content: str) -> str:
    """Replace content of a single CDATA span in the document."""
    if span.content == new_content:
        return doc.raw_text

    return (
        doc.raw_text[: span.content_start]
        + new_content
        + doc.raw_text[span.content_end :]
    )


def patch_cdata_spans(
    doc: TcXmlDocument,
    patches: Sequence[Tuple[CdataSpan, str]],
) -> str:
    """Apply multiple span patches safely by processing in reverse offset order.

    Sorting in descending order of start position ensures earlier offsets
    remain valid as string length changes during replacement.
    """
    if not patches:
        return doc.raw_text

    # Sort descending by content_start to avoid offset invalidation
    sorted_patches = sorted(
        patches,
        key=lambda item: item[0].content_start,
        reverse=True,
    )

    text = doc.raw_text
    for span, new_content in sorted_patches:
        if span.content == new_content:
            continue
        text = text[: span.content_start] + new_content + text[span.content_end :]

    return text


def patch_by_filter(
    doc: TcXmlDocument,
    replacer: Callable[[CdataSpan], Optional[str]],
) -> Tuple[str, int]:
    """Apply a replacer function to all CDATA spans.

    If replacer returns None or identical string, span is unchanged.
    Returns (new_raw_text, number_of_modified_spans).
    """
    patches: list[Tuple[CdataSpan, str]] = []

    for span in doc.cdata_spans:
        new_val = replacer(span)
        if new_val is not None and new_val != span.content:
            patches.append((span, new_val))

    if not patches:
        return doc.raw_text, 0

    new_text = patch_cdata_spans(doc, patches)
    return new_text, len(patches)


def patch_declaration(doc: TcXmlDocument, new_declaration: str) -> str:
    """Replace root object declaration (POU, DUT, GVL, Itf)."""
    span = doc.get_declaration_span()
    if span is None:
        raise ValueError(f"No root declaration CDATA found in document: {doc.file_path or doc.root_object_name}")
    return patch_cdata_span(doc, span, new_declaration)


def patch_implementation(doc: TcXmlDocument, new_implementation: str) -> str:
    """Replace root POU body implementation."""
    span = doc.get_implementation_span()
    if span is None:
        raise ValueError(f"No root implementation CDATA found in document: {doc.file_path or doc.root_object_name}")
    return patch_cdata_span(doc, span, new_implementation)


def patch_method(
    doc: TcXmlDocument,
    method_name: str,
    new_declaration: Optional[str] = None,
    new_implementation: Optional[str] = None,
) -> str:
    """Replace declaration and/or implementation of a specific method."""
    patches: list[Tuple[CdataSpan, str]] = []
    spans = doc.get_method_spans(method_name)
    if not spans:
        raise ValueError(f"Method '{method_name}' not found in document.")

    for span in spans:
        if span.kind == CdataKind.METHOD_DECLARATION and new_declaration is not None:
            patches.append((span, new_declaration))
        elif span.kind == CdataKind.METHOD_IMPLEMENTATION and new_implementation is not None:
            patches.append((span, new_implementation))

    return patch_cdata_spans(doc, patches)


def patch_action(
    doc: TcXmlDocument,
    action_name: str,
    new_implementation: str,
) -> str:
    """Replace implementation of a specific action."""
    spans = doc.get_action_spans(action_name)
    if not spans:
        raise ValueError(f"Action '{action_name}' not found in document.")

    for span in spans:
        if span.kind == CdataKind.ACTION_IMPLEMENTATION:
            return patch_cdata_span(doc, span, new_implementation)

    raise ValueError(f"Action '{action_name}' has no implementation CDATA.")
