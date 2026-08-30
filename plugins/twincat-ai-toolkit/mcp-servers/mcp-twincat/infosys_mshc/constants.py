"""Constants and regular expressions for InfoSys MSHC."""

import html
import re

HELPLIB_ROOTS = [
    r"C:\ProgramData\Microsoft\HelpLibrary2\Catalogs",
]
_HELPLIB_ROOTS = HELPLIB_ROOTS

LANG_FOLDER = {
    "en": "EN-US",
    "de": "DE-DE",
}
_LANG_FOLDER = LANG_FOLDER

MSHC_PATTERN = "BKINFOSYS3_VS_100_{lang_folder}.*.mshc"
_MSHC_PATTERN = MSHC_PATTERN

SCHEMA_VERSION = "2"
_SCHEMA_VERSION = SCHEMA_VERSION

TYPE_PREFIXES = {
    "FB_": "FUNCTION_BLOCK",
    "ST_": "STRUCT",
    "E_": "ENUM",
    "I_": "INTERFACE",
    "F_": "FUNCTION",
    "T_": "TYPE",
    "M_": "METHOD",
    "P_": "PROPERTY",
}
_TYPE_PREFIXES = TYPE_PREFIXES

SECTION_ALIASES = {
    "eingänge": "inputs",
    "eingaenge": "inputs",
    "ausgänge": "outputs",
    "ausgaenge": "outputs",
    "ein-/ausgänge": "inputs",
    "ein-/ausgaenge": "inputs",
    "eigenschaften": "properties",
    "properties": "properties",
    "property": "properties",
    "methoden": "methods",
    "voraussetzungen": "requirements",
    "rückgabewert": "return_value",
    "rueckgabewert": "return_value",
    "return value": "return_value",
    "returns": "return_value",
    "ereignisgesteuerte methoden (callback-methoden)": (
        "event-driven methods (callback methods)"
    ),
}
_SECTION_ALIASES = SECTION_ALIASES

NOT_INSTALLED_MSG = (
    "The TwinCAT 3 offline documentation (InfoSys) is not installed.\n"
    "Install it using ONE of these methods:\n"
    "  1. Download and run TC3-InfoSys.exe from:\n"
    "     https://download.beckhoff.com/download/Software/TwinCAT/TwinCAT3/InfoSystem/\n"
    "     (Run as Administrator, select 'Complete' or choose your language/VS version)\n"
    "  2. In TcXaeShell: Help > Manage Help Settings > Install content from online\n"
    "     > Add 'Beckhoff Information System' > Update\n"
    "After installation, restart the MCP server."
)
_NOT_INSTALLED_MSG = NOT_INSTALLED_MSG

FTS5_BODY_LIMIT = 16384
_FTS5_BODY_LIMIT = FTS5_BODY_LIMIT

READ_LIMIT = 16384
_READ_LIMIT = READ_LIMIT

DEFAULT_MAX_FULL_TEXT_CHARS = 1000
_DEFAULT_MAX_FULL_TEXT_CHARS = DEFAULT_MAX_FULL_TEXT_CHARS

DEFAULT_MAX_METHODS = 50
_DEFAULT_MAX_METHODS = DEFAULT_MAX_METHODS

DEFAULT_MAX_PARAMS = 50
_DEFAULT_MAX_PARAMS = DEFAULT_MAX_PARAMS

DEFAULT_MAX_RESPONSE_CHARS = 8000
_DEFAULT_MAX_RESPONSE_CHARS = DEFAULT_MAX_RESPONSE_CHARS

RE_TITLE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_RE_TITLE = RE_TITLE

RE_TAG = re.compile(r"<[^>]+>")
_RE_TAG = RE_TAG

RE_MULTI_WS = re.compile(r"[ \t]+")
_RE_MULTI_WS = RE_MULTI_WS

RE_MULTI_NL = re.compile(r"\n{3,}")
_RE_MULTI_NL = RE_MULTI_NL

RE_H2 = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
_RE_H2 = RE_H2

RE_TABLE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_RE_TABLE_ROW = RE_TABLE_ROW

RE_TABLE_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_RE_TABLE_CELL = RE_TABLE_CELL

RE_CODE_BLOCK = re.compile(
    r"<(?:pre|code)[^>]*>(.*?)</(?:pre|code)>", re.IGNORECASE | re.DOTALL
)
_RE_CODE_BLOCK = RE_CODE_BLOCK

RE_DESCRIPTION_META = re.compile(
    r'<meta\s+name="Description"\s+content="(.*?)"', re.IGNORECASE
)
_RE_DESCRIPTION_META = RE_DESCRIPTION_META

RE_DISPLAY_VERSION = re.compile(
    r'<meta\s+name="Microsoft\.Help\.DisplayVersion"\s+content="(.*?)"',
    re.IGNORECASE,
)
_RE_DISPLAY_VERSION = RE_DISPLAY_VERSION

RE_FTS5_SPECIAL = re.compile(r'[^\w\s*"_]', re.UNICODE)
_RE_FTS5_SPECIAL = RE_FTS5_SPECIAL
