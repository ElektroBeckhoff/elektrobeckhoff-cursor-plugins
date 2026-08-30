"""Generate autodocs test fixtures and golden markdown files."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "golden"

FIXTURES: dict[str, str] = {
    "pou_FB_Basic.TcPOU": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Basic" Id="{11111111-1111-1111-1111-111111111101}">
    <Declaration><![CDATA[(* Basic FB for autodocs tests. *)
FUNCTION_BLOCK FB_Basic
VAR_INPUT
    bEnable : BOOL;
    nValue  : INT := 0;
END_VAR
VAR_OUTPUT
    bDone : BOOL;
END_VAR
VAR_IN_OUT
    stData : ST_TestData;
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[bDone := bEnable;]]></ST></Implementation>
  </POU>
</TcPlcObject>
""",
    "pou_FB_Extends.TcPOU": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Extends" Id="{11111111-1111-1111-1111-111111111102}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Extends EXTENDS FB_Base
VAR_INPUT
    bStart : BOOL;
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>
""",
    "pou_FB_Methods.TcPOU": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Methods" Id="{11111111-1111-1111-1111-111111111103}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Methods
]]></Declaration>
    <Method Name="M_DoWork" Id="{22222222-2222-2222-2222-222222222201}">
      <Declaration><![CDATA[(* Performs work on input data. *)
METHOD M_DoWork : BOOL
VAR_INPUT
    nStep : INT;
END_VAR
VAR_OUTPUT
    bOk : BOOL;
END_VAR
]]></Declaration>
    </Method>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>
""",
    "pou_FB_Properties.TcPOU": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Properties" Id="{11111111-1111-1111-1111-111111111104}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Properties
]]></Declaration>
    <Property Name="Count" Id="{33333333-3333-3333-3333-333333333301}">
      <Declaration><![CDATA[PROPERTY Count : INT]]></Declaration>
      <Get Name="Get" Id="{33333333-3333-3333-3333-333333333302}"><Declaration><![CDATA[]]></Declaration></Get>
    </Property>
    <Property Name="Name" Id="{33333333-3333-3333-3333-333333333303}">
      <Declaration><![CDATA[PROPERTY Name : STRING]]></Declaration>
      <Get Name="Get" Id="{33333333-3333-3333-3333-333333333304}"><Declaration><![CDATA[]]></Declaration></Get>
      <Set Name="Set" Id="{33333333-3333-3333-3333-333333333305}"><Declaration><![CDATA[]]></Declaration></Set>
    </Property>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>
""",
    "pou_Func_Return.TcPOU": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="F_Return" Id="{11111111-1111-1111-1111-111111111105}">
    <Declaration><![CDATA[FUNCTION F_Return : REAL
VAR_INPUT
    fIn : REAL;
END_VAR
]]></Declaration>
    <Implementation><ST><![CDATA[F_Return := fIn;]]></ST></Implementation>
  </POU>
</TcPlcObject>
""",
    "pou_Hidden.TcPOU": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Hidden" Id="{11111111-1111-1111-1111-111111111106}">
    <Declaration><![CDATA[{attribute 'hide'}
FUNCTION_BLOCK FB_Hidden
]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>
""",
    "itf_Basic.TcIO": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_Basic" Id="{44444444-4444-4444-4444-444444444401}">
    <Declaration><![CDATA[(* Basic interface for autodocs tests. *)
INTERFACE I_Basic
]]></Declaration>
    <Method Name="Init" Id="{44444444-4444-4444-4444-444444444402}">
      <Declaration><![CDATA[METHOD Init : BOOL
VAR_INPUT
    bForce : BOOL;
END_VAR
]]></Declaration>
    </Method>
    <Property Name="Ready" Id="{44444444-4444-4444-4444-444444444403}">
      <Declaration><![CDATA[PROPERTY Ready : BOOL]]></Declaration>
      <Get Name="Get" Id="{44444444-4444-4444-4444-444444444404}"><Declaration><![CDATA[]]></Declaration></Get>
    </Property>
  </Itf>
</TcPlcObject>
""",
    "itf_Extends.TcIO": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_Extends" Id="{44444444-4444-4444-4444-444444444405}">
    <Declaration><![CDATA[INTERFACE I_Extends EXTENDS I_Base
]]></Declaration>
  </Itf>
</TcPlcObject>
""",
    "dut_Enum.TcDUT": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="E_TestMode" Id="{55555555-5555-5555-5555-555555555501}">
    <Declaration><![CDATA[(* Test enum. *)
TYPE E_TestMode : (
    Off := 0,
    On  := 1  (* Active state *)
);
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
""",
    "dut_Struct.TcDUT": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_TestData" Id="{55555555-5555-5555-5555-555555555502}">
    <Declaration><![CDATA[TYPE ST_TestData :
STRUCT
    bFlag : BOOL;
    nCount : INT := 0;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
""",
    "dut_StructExtends.TcDUT": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_Child" Id="{55555555-5555-5555-5555-555555555503}">
    <Declaration><![CDATA[TYPE ST_Child EXTENDS ST_Base : STRUCT
    fValue : REAL;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
""",
    "dut_Union.TcDUT": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="U_TestOverlay" Id="{55555555-5555-5555-5555-555555555504}">
    <Declaration><![CDATA[TYPE U_TestOverlay :
UNION
    nRaw : UDINT;
    arrBytes : ARRAY[0..3] OF BYTE;
END_UNION
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
""",
    "dut_Hidden.TcDUT": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_Hidden" Id="{55555555-5555-5555-5555-555555555505}">
    <Declaration><![CDATA[{attribute 'hide'}
TYPE ST_Hidden :
STRUCT
    nX : INT;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
""",
    "gvl_Basic.TcGVL": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <GVL Name="GVL_Basic" Id="{66666666-6666-6666-6666-666666666601}">
    <Declaration><![CDATA[(* Basic GVL for autodocs tests. *)
VAR_GLOBAL
    bSystemReady : BOOL;
    nCounter     : INT := 0;
END_VAR
VAR_GLOBAL CONSTANT
    cMaxCount : INT := 100;
END_VAR
]]></Declaration>
  </GVL>
</TcPlcObject>
""",
    "gvl_Hidden.TcGVL": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <GVL Name="GVL_Hidden" Id="{66666666-6666-6666-6666-666666666602}">
    <Declaration><![CDATA[{attribute 'hide'}
VAR_GLOBAL
    nSecret : INT;
END_VAR
]]></Declaration>
  </GVL>
</TcPlcObject>
""",
}

# Support types referenced by cross-refs
EXTRA_FIXTURES: dict[str, str] = {
    "pou_FB_Base.TcPOU": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <POU Name="FB_Base" Id="{77777777-7777-7777-7777-777777777701}">
    <Declaration><![CDATA[FUNCTION_BLOCK FB_Base
]]></Declaration>
    <Implementation><ST><![CDATA[]]></ST></Implementation>
  </POU>
</TcPlcObject>
""",
    "itf_I_Base.TcIO": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <Itf Name="I_Base" Id="{77777777-7777-7777-7777-777777777702}">
    <Declaration><![CDATA[INTERFACE I_Base
]]></Declaration>
  </Itf>
</TcPlcObject>
""",
    "dut_ST_Base.TcDUT": """<?xml version="1.0" encoding="utf-8"?>
<TcPlcObject Version="1.1.0.1">
  <DUT Name="ST_Base" Id="{77777777-7777-7777-7777-777777777703}">
    <Declaration><![CDATA[TYPE ST_Base :
STRUCT
    nId : INT;
END_STRUCT
END_TYPE
]]></Declaration>
  </DUT>
</TcPlcObject>
""",
}


def write_raw_fixtures() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    mini = RAW / "miniproject"
    mini.mkdir(exist_ok=True)
    all_fixtures = {**FIXTURES, **EXTRA_FIXTURES}
    for name, content in all_fixtures.items():
        (RAW / name).write_text(content, encoding="utf-8")
    for fname in ("pou_FB_Basic.TcPOU", "dut_Enum.TcDUT", "gvl_Basic.TcGVL", "itf_Basic.TcIO"):
        (mini / fname).write_text((RAW / fname).read_text(encoding="utf-8"), encoding="utf-8")


def generate_golden() -> None:
    from autodocs.markdown import write_or_update_markdown
    from autodocs.parsers.dut import parse_tcDut
    from autodocs.parsers.gvl import parse_tcGvl
    from autodocs.parsers.itf import parse_tcItf
    from autodocs.parsers.pou import parse_tcPou
    from autodocs.type_index import build_type_index

    GOLDEN.mkdir(parents=True, exist_ok=True)
    type_index = build_type_index(RAW)
    docs_root = GOLDEN  # flat golden/*.md mirrors docs output content

    parsers = {
        ".TcPOU": parse_tcPou,
        ".TcIO": parse_tcItf,
        ".TcDUT": parse_tcDut,
        ".TcGVL": parse_tcGvl,
    }

    for name in FIXTURES:
        src = RAW / name
        ext = src.suffix
        parser = parsers[ext]
        out_file = docs_root / (src.stem + ".md")
        parsed = parser(src, type_index, out_file, docs_root)
        if parsed is None:
            print(f"SKIP hidden: {name}")
            continue
        out_file.parent.mkdir(parents=True, exist_ok=True)
        write_or_update_markdown(out_file, parsed["title"], parsed["sections"])
        print(f"Golden: {out_file.name}")


if __name__ == "__main__":
    write_raw_fixtures()
    generate_golden()
    print("Done.")
