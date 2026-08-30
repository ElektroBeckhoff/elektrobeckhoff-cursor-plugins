"""Autodocs configuration constants."""

VAR_HEADERS = ("VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT")
SECTION_KEYS = {"VAR_INPUT": "INPUT", "VAR_OUTPUT": "OUTPUT", "VAR_IN_OUT": "IN_OUT"}
SECTION_ORDER = (
    "SIGNATURE",
    "DESCRIPTION",
    "DUT",
    "GVL",
    "RETURN",
    "INPUT",
    "OUTPUT",
    "IN_OUT",
    "PROPERTIES",
    "METHODS",
)
# Optional access qualifier in TwinCAT signatures (METHOD/PROPERTY/TYPE/FUNCTION)
QUAL = r"(?:\s+(?:INTERNAL|PUBLIC|PRIVATE|PROTECTED))?"
