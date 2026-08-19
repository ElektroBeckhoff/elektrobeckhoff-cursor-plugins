"""Replace NWL blocks with generated ST in .TcPOU XML."""
from __future__ import annotations

import re
from typing import Optional

from migrator.types import TcFile
from migrator.xml_reader import _regenerate_guids


def _replace_nwl_block(text: str, start_tag: str, st_code: str) -> str:
    """Replace an <Implementation><NWL>...</NWL></Implementation> block following *start_tag*."""
    anchor = text.find(start_tag)
    if anchor < 0:
        return text

    search_from = anchor + len(start_tag)
    impl_open = text.find("<Implementation>", search_from)
    if impl_open < 0:
        return text

    nwl_open = text.find("<NWL>", impl_open)
    if nwl_open < 0:
        return text

    nwl_close = text.find("</NWL>", nwl_open)
    if nwl_close < 0:
        return text

    impl_close = text.find("</Implementation>", nwl_close)
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


def write_st_to_xml(tc: TcFile, regenerate_ids: bool = False) -> Optional[str]:
    if tc.xml_root is None:
        return None

    raw_text = tc.path.read_text(encoding=tc.encoding)

    if "<POU " not in raw_text and "<POU>" not in raw_text:
        return None
    if "<NWL>" not in raw_text:
        return None

    pou_tag_match = re.search(r'<POU\s[^>]*>', raw_text)
    if not pou_tag_match:
        return None
    pou_tag = pou_tag_match.group(0)

    result = _replace_nwl_block(raw_text, pou_tag, tc.generated_st)
    if result == raw_text:
        return None

    if tc.edge_vars:
        unique_vars = list(dict.fromkeys(tc.edge_vars))
        decl_lines = "\n".join(f"    {name} : {etype};" for name, etype in unique_vars)
        edge_block = (
            "\nVAR\n"
            "    // Auto-generated edge detection instances [FBD Migration]\n"
            f"{decl_lines}\n"
            "END_VAR"
        )
        cdata_open = result.find("<Declaration><![CDATA[")
        if cdata_open >= 0:
            cdata_start = cdata_open + len("<Declaration><![CDATA[")
            cdata_close = result.find("]]></Declaration>", cdata_start)
            if cdata_close >= 0:
                old_decl = result[cdata_start:cdata_close]
                new_decl = old_decl.rstrip() + "\n" + edge_block + "\n"
                result = result[:cdata_start] + new_decl + result[cdata_close:]

    for action in tc.actions:
        if action.st_code and action.name:
            action_tag = f'<Action Name="{action.name}"'
            result = _replace_nwl_block(result, action_tag, action.st_code)

    if regenerate_ids:
        result = _regenerate_guids(result)

    return result
