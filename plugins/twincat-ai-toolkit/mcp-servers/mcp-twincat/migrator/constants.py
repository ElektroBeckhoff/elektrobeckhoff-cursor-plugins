"""Shared constants for TwinCAT graphical-to-ST migration."""

SCRIPT_VERSION = "1.0.0"

# File types collected during recursive scans. Only .TcPOU files with NWL/CFC
# implementations are actually migrated; .TcGVL/.TcDUT are skipped in pipeline.
# .TcIO is intentionally excluded: TwinCAT interfaces are pure contracts (method/
# property signatures only). Program code — including FBD/FUP/CFC — lives in FBs
# that IMPLEMENT the interface (.TcPOU), not in the interface file itself.
# See InfoSys: tc3_plc_intro/1033/4256456843_55762700.html (Object Interface method).
SUPPORTED_EXTENSIONS = {".tcpou", ".tcgvl", ".tcdut"}

INFIX_OPERATORS = {"And": "AND", "Or": "OR", "Xor": "XOR"}
COMPARISON_OPS = {"EQ": "=", "NE": "<>", "GT": ">", "LT": "<", "GE": ">=", "LE": "<="}
ARITHMETIC_OPS = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "MOD": "MOD"}
CONVERSION_FUNCS = {
    "INT_TO_REAL", "REAL_TO_INT", "BOOL_TO_INT", "INT_TO_BOOL",
    "DINT_TO_REAL", "REAL_TO_DINT", "LREAL_TO_REAL", "REAL_TO_LREAL",
    "INT_TO_DINT", "DINT_TO_INT", "TO_INT", "TO_REAL", "TO_BOOL",
    "TO_DINT", "TO_LREAL", "TO_STRING", "TO_WORD", "TO_DWORD",
    "BYTE_TO_INT", "INT_TO_BYTE", "WORD_TO_INT", "INT_TO_WORD",
}
IEC_FUNCTIONS = {
    "MUX", "LIMIT", "MAX", "MIN",
    "SHL", "SHR", "ROL", "ROR",
    "ABS", "SQRT", "LN", "LOG", "EXP", "EXPT",
    "SIN", "COS", "TAN", "ASIN", "ACOS", "ATAN",
    "TRUNC", "SIZEOF", "ADR", "BITADR", "INDEXOF",
}
FB_CALL_TYPES = {"FunctionBlock", "Function", "Program", "Method"}
