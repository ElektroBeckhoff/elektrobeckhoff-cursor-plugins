"""Replace CFC blocks with generated ST in .TcPOU XML."""
from __future__ import annotations

import re
from typing import Optional

from migrator.types import TcFile
from migrator.xml_reader import _regenerate_guids


def _replace_cfc_block(text: str, start_tag: str, st_code: str) -> str:
    """Replace <Implementation><CFC>...</CFC></Implementation> with ST."""
    anchor = text.find(start_tag)
    if anchor < 0:
        return text

    search_from = anchor + len(start_tag)
    impl_open = text.find("<Implementation>", search_from)
    if impl_open < 0:
        return text

    cfc_open = text.find("<CFC>", impl_open)
    if cfc_open < 0:
        return text

    cfc_close = text.find("</CFC>", cfc_open)
    if cfc_close < 0:
        return text

    impl_close = text.find("</Implementation>", cfc_close)
    if impl_close < 0:
        return text
    impl_close_end = impl_close + len("</Implementation>")

    indent = "      "
    new_impl = (
        "<Implementation>\n"
        f"{indent}<ST><![CDATA[{st_code}]]></ST>\n"
        "    </Implementation>"
    )
    return text[:impl_open] + new_impl + text[impl_close_end:]


def write_cfc_st_to_xml(tc: TcFile, regenerate_ids: bool = False) -> Optional[str]:
    if tc.xml_root is None:
        return None

    raw_text = tc.path.read_text(encoding=tc.encoding)

    if "<POU " not in raw_text and "<POU>" not in raw_text:
        return None
    if "<CFC>" not in raw_text:
        return None

    pou_tag_match = re.search(r'<POU\s[^>]*>', raw_text)
    if not pou_tag_match:
        return None
    pou_tag = pou_tag_match.group(0)

    result = _replace_cfc_block(raw_text, pou_tag, tc.generated_st)
    if result == raw_text:
        return None

    if regenerate_ids:
        result = _regenerate_guids(result)

    return result
