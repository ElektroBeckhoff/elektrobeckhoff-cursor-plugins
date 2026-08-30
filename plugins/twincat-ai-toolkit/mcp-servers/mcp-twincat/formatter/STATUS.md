# ST-Formatter — Status

## Aktueller Stand (2026-08-30)

**Ziel: Settings-Fixpunkt & Produktionstauglichkeit** — beliebiger Input (inkl. maximal kollabierter Oneliner, unstrukturierter Zuweisungen, gestörter Einrückung) → byte-identisches Golden bei Default-Settings.

**Corpus-Abdeckung:** **103/103 Fixtures (100% Fixpunkt-Gates bestanden)**
- **15 Samples (`fixtures/raw/samples/`):** Komplexe Großdateien (bis >1.000 Zeilen pro Baustein) mit Zustandsautomaten, FIFO-Puffern, Logging und Motion-Koordinatoren.
- **88 Syntax-Fixtures (`fixtures/raw/syntax/`):** Vollständige IEC 61131-3 & TwinCAT 3 Syntax-Abdeckung (Kontrollfluss, OOP, AT %I/%Q, PROGRAM, ACTION, Disable-Regionen, Enums, Calls, Pragmas, bedingte Kompilierung, String-Escapes, dynamischer Speicher `__NEW`/`__DELETE`, System-Introspektion `__VARINFO`, `__QUERYPOINTER`, `__XADD`, `TEST_AND_SET`, `__POSITION`, `__POUNAME`, partielle Variablenzugriffe `.%X`, `.%B`, Pointer-Array-Indizierung, generische `ANY`-Typen, Fluent Interfaces und mehrzeilige Array-Initialisierungen).

**Unit- & Integrationstests:** **893 Tests (100% Passed)**

---

### Pipeline-Architektur (`_format_st_segment`)

1. **Core Spacing (`format_st_code`):** Normalisierung von Token-Abständen, Operator-Spacing, Keyword-Großschreibung.
2. **Statement Normalize (`st_statement_normalize`):** Zerlegung an `;`, Kontrollfluss-Keywords, Compiler-Direktiven und Formatting-Disable-Regionen.
3. **Column-Anchor Reindent (`st_indent_anchor`):** Stack-basierte Spaltenanker für `IF/ELSIF/ELSE`, `CASE`, `FOR`, `WHILE`, `REPEAT`.
4. **Join & Alignment (`st_alignment`):** Doppelpunkt-Ausrichtung in Deklarationen, `:=` Zuweisungsausrichtung, Enum-Elemente, mehrzeilige Struct-/Array-Initialisierungen (`align_array_struct_inits`).
5. **Line Wrapper (`st_line_wrapper`):** Automatisches Umbrechen bei Überschreiten der Zeilenlänge (`wrap_at`), Erhalt von `THEN`/`DO`-Suffixen.
6. **XML & CDATA Handling (`xml_formatter`, `xml_writer`, `safe_writer`):** Erhaltung von UTF-8 / BOM, GUID-Integrität und XML-Struktur.

---

### Ordner-Struktur

```text
mcp-twincat/
├── formatter/                     # Core Formatter Package (20 Module)
│   ├── defaults.json              # Standard-Konfiguration
│   ├── INDENT_ANCHOR_SPEC.md      # Spezifikation des Einrückungs-Algorithmus
│   └── STATUS.md                  # Projekt-Status
└── tests/formatter/
    ├── fixtures/                  # 103 Testdateien (raw, golden, oneline)
    ├── scripts/                   # Verifikations-, Test- und Generierungs-Tools
    │   ├── verify_4gate_fixpoint.py            # 4-Gate Fixpunkt-Runner (Raw, Golden, Oneline)
    │   ├── verify_raw_golden_byte_match.py     # Byte-Vergleichs-Engine & CLI Runner
    │   ├── verify_stweep_xae_parity.py         # TwinCAT XAE Compiler & STweep Paritäts-Prüfer
    │   ├── audit_formatter_config_parity.py    # Config / Schema Auditor
    │   ├── generate_oneline_stress_fixtures.py # Oneliner Stress-Fixture Generator
    │   ├── generate_messy_raw_fixtures.py      # Raw Deformations-Generator
    │   ├── sync_golden_from_formatted_raw.py   # Golden Sync Helper
    │   └── messy_corpus_transforms.py          # Deformations-Transformations-Engine
    └── tests/                     # 31 Pytest-Testmodule (893 Tests)
```
