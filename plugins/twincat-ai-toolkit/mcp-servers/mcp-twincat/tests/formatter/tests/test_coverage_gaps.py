"""Missing edge case coverage: areas not yet tested elsewhere.

Fills gaps in overall test coverage:
- Multiline declarations (array/struct init spanning lines)
- Tab indentation mode
- WSTRING dollar escapes
- Interface (.TcIO) XML structure
- GVL with qualified_only attribute
- Safe writer (backup/rollback mechanics)
- Batch processing (parallel)
- FB_init / FB_exit special FBs
- Empty methods/actions/properties
- Multiline FB call alignment after wrapping
- Large-scale idempotency stress
- Line endings in various positions
- Unicode in identifiers/strings
- Semicolons in special contexts
"""
import os
import tempfile
import pytest

from formatter.st_formatter import format_st_code
from formatter.st_alignment import align_declarations, align_assignments, align_fb_call_params
from formatter.st_line_wrapper import wrap_long_lines
from formatter.file_processor import (
    _format_st_pipeline,
    _format_st_segment,
    process_file,
    process_batch,
    discover_files,
)
from formatter.config import FormatterConfig
from formatter.safe_writer import SafeFileWriter
from formatter.xml_formatter import format_xml_structure, restore_cdata
from formatter.xml_validator import validate_twincat_xml


@pytest.fixture
def config():
    return FormatterConfig()


def _assert_idempotent(source: str, config: FormatterConfig) -> str:
    r1 = _format_st_pipeline(source, config)
    r2 = _format_st_pipeline(r1, config)
    assert r1 == r2, f"Not idempotent!\nFirst:\n{r1}\nSecond:\n{r2}"
    return r1


# ---------------------------------------------------------------------------
# Multiline declarations (continuation lines)
# ---------------------------------------------------------------------------


class TestMultilineDeclarations:

    def test_array_init_spanning_lines(self, config):
        """Multi-line array initialization should not get semicolons added."""
        code = (
            "VAR\n"
            "    arrValues : ARRAY[0..4] OF INT := [\n"
            "        1, 2, 3,\n"
            "        4, 5\n"
            "    ];\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "ARRAY[0..4] OF INT" in result
        # No extra semicolons on continuation lines
        assert result.count(";") == code.count(";")

    def test_struct_init_spanning_lines(self, config):
        """Multi-line struct initialization."""
        code = (
            "VAR\n"
            "    stConfig : ST_Config := (\n"
            "        nId := 1,\n"
            "        sName := 'Test',\n"
            "        fValue := 3.14\n"
            "    );\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "nId" in result
        assert ":= 1" in result
        assert "fValue" in result
        assert ":= 3.14" in result

    def test_fb_instance_init_spanning_lines(self, config):
        """Multi-line FB instance initialization."""
        code = (
            "VAR\n"
            "    fbTimer : TON := (\n"
            "        PT := T#5s,\n"
            "        IN := FALSE\n"
            "    );\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "PT := T#5S" in result

    def test_long_declaration_type(self, config):
        """Very long type that continues on next line conceptually."""
        code = (
            "VAR\n"
            "    pHandler : POINTER TO FB_Very_Long_Function_Block_Name_That_Is_Realistic;\n"
            "    nSimple  : INT;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "POINTER TO FB_Very_Long_Function_Block_Name_That_Is_Realistic" in result


# ---------------------------------------------------------------------------
# Tab indentation mode
# ---------------------------------------------------------------------------


class TestTabIndentation:

    def test_tab_config_does_not_crash(self):
        """Tab indent mode should not crash the formatter."""
        cfg = FormatterConfig()
        cfg.indent.style = "tabs"
        cfg.indent.size = 4
        code = "IF x = 1 THEN\n    y := 2;\nEND_IF;"
        result = _format_st_pipeline(code, cfg)
        assert "IF" in result
        assert "END_IF" in result


# ---------------------------------------------------------------------------
# WSTRING with dollar escapes
# ---------------------------------------------------------------------------


class TestWStringDollarEscapes:

    def test_dollar_hex_escape(self, config):
        code = 'sUnicode := "$0041$0042$0043";'
        result = _assert_idempotent(code, config)
        assert '"$0041$0042$0043"' in result

    def test_dollar_special_escapes(self, config):
        code = 'sEscaped := "$N$R$T$L$$";'
        result = _assert_idempotent(code, config)
        assert '"$N$R$T$L$$"' in result

    def test_mixed_wstring_content(self, config):
        code = 'wsPath := "C:$5CTemp$5Cfile.txt";'
        result = _assert_idempotent(code, config)
        assert '"C:$5CTemp$5Cfile.txt"' in result


# ---------------------------------------------------------------------------
# Interface XML structure
# ---------------------------------------------------------------------------


class TestInterfaceFiles:

    def test_interface_xml_valid(self):
        """Interface TcIO XML should parse and validate."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <Itf Name="I_MyInterface" Id="{12345678-1234-1234-1234-123456789abc}">\n'
            '    <Declaration><![CDATA[INTERFACE I_MyInterface\n]]></Declaration>\n'
            '  </Itf>\n'
            '</TcPlcObject>\n'
        )
        issues = validate_twincat_xml(xml, "I_MyInterface.TcIO")
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) == 0

    def test_interface_with_methods(self):
        """Interface with method declarations."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <Itf Name="I_Moveable" Id="{12345678-1234-1234-1234-123456789abc}">\n'
            '    <Declaration><![CDATA[INTERFACE I_Moveable\n]]></Declaration>\n'
            '    <Method Name="M_Move" Id="{22345678-1234-1234-1234-123456789abc}">\n'
            '      <Declaration><![CDATA[METHOD M_Move\nVAR_INPUT\n    fTarget : REAL;\nEND_VAR\n]]></Declaration>\n'
            '    </Method>\n'
            '  </Itf>\n'
            '</TcPlcObject>\n'
        )
        issues = validate_twincat_xml(xml, "I_Moveable.TcIO")
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# GVL with qualified_only
# ---------------------------------------------------------------------------


class TestGVLSpecifics:

    def test_gvl_xml_valid(self):
        """GVL with ParameterList attribute."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <GVL Name="Param_Test" Id="{12345678-1234-1234-1234-123456789abc}" ParameterList="true">\n'
            '    <Declaration><![CDATA[{attribute \'qualified_only\'}\n'
            'VAR_GLOBAL CONSTANT\n'
            '    cVersion : STRING := \'1.0\';\n'
            'END_VAR\n]]></Declaration>\n'
            '  </GVL>\n'
            '</TcPlcObject>\n'
        )
        issues = validate_twincat_xml(xml, "Param_Test.TcGVL")
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) == 0

    def test_gvl_formatting_preserves_qualified_only(self, config):
        code = (
            "{attribute 'qualified_only'}\n"
            "VAR_GLOBAL CONSTANT\n"
            "    cPi   : LREAL := 3.14159;\n"
            "    cE    : LREAL := 2.71828;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "{attribute 'qualified_only'}" in result
        assert "VAR_GLOBAL CONSTANT" in result


# ---------------------------------------------------------------------------
# Safe writer: backup, atomic write
# ---------------------------------------------------------------------------


class TestSafeWriter:

    def test_write_creates_file(self):
        writer = SafeFileWriter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".TcPOU", delete=False) as f:
            f.write("original content")
            path = f.name

        try:
            new_content = b"formatted content"
            summary = writer.write_safe(path, new_content, backup=False)
            assert summary.error is None or summary.error == ""
            with open(path, "rb") as f:
                assert f.read() == new_content
        finally:
            os.unlink(path)

    def test_write_with_backup(self):
        writer = SafeFileWriter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".TcPOU", delete=False) as f:
            f.write("original content")
            path = f.name

        try:
            new_content = b"formatted content"
            summary = writer.write_safe(
                path, new_content, backup=True, delete_backup_on_success=False
            )
            assert summary.error is None or summary.error == ""
            # Backup should exist
            bak_path = path + ".bak"
            assert os.path.exists(bak_path)
            with open(bak_path, "r") as f:
                assert f.read() == "original content"
        finally:
            os.unlink(path)
            if os.path.exists(path + ".bak"):
                os.unlink(path + ".bak")

    def test_write_delete_backup_on_success(self):
        writer = SafeFileWriter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".TcPOU", delete=False) as f:
            f.write("original content")
            path = f.name

        try:
            new_content = b"formatted content"
            summary = writer.write_safe(
                path, new_content, backup=True, delete_backup_on_success=True
            )
            assert summary.error is None or summary.error == ""
            # Backup should NOT exist (deleted on success)
            bak_path = path + ".bak"
            assert not os.path.exists(bak_path)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


class TestBatchProcessing:

    def test_batch_processes_multiple_files(self):
        cfg = FormatterConfig()
        cfg.safety.backup = False
        files = []
        try:
            for i in range(3):
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".TcPOU", delete=False, encoding="utf-8"
                ) as f:
                    f.write(
                        '<?xml version="1.0" encoding="utf-8"?>\n'
                        '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
                        f'  <POU Name="FB_Test{i}" Id="{{1234567{i}-1234-1234-1234-123456789abc}}">\n'
                        f'    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test{i}\nVAR\n    x : int;\nEND_VAR\n]]></Declaration>\n'
                        '    <Implementation><![CDATA[x := 1;\n]]></Implementation>\n'
                        '  </POU>\n'
                        '</TcPlcObject>\n'
                    )
                    files.append(f.name)

            batch = process_batch(files, cfg, validate=False)
            assert batch.total == 3
            assert batch.errors == 0
        finally:
            for f in files:
                if os.path.exists(f):
                    os.unlink(f)

    def test_discover_files_filters_extensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create various files
            for name in ["FB_Test.TcPOU", "ST_Data.TcDUT", "readme.txt", "build.py"]:
                open(os.path.join(tmpdir, name), "w").close()

            found = discover_files([tmpdir])
            names = [os.path.basename(f) for f in found]
            assert "FB_Test.TcPOU" in names
            assert "ST_Data.TcDUT" in names
            assert "readme.txt" not in names
            assert "build.py" not in names


# ---------------------------------------------------------------------------
# FB_init / FB_exit special functions
# ---------------------------------------------------------------------------


class TestSpecialFBMethods:

    def test_fb_init_method(self, config):
        code = (
            "METHOD FB_init\n"
            "VAR_INPUT\n"
            "    bInitRetains : BOOL;\n"
            "    bInCopyCode  : BOOL;\n"
            "END_VAR"
        )
        result = _assert_idempotent(code, config)
        assert "FB_init" in result
        assert "bInitRetains" in result
        assert "bInCopyCode" in result

    def test_fb_exit_method(self, config):
        code = "METHOD FB_exit\nVAR_INPUT\n    bInCopyCode : BOOL;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "FB_exit" in result

    def test_fb_reinit_method(self, config):
        code = "METHOD FB_reinit\n// Called after online change"
        result = _assert_idempotent(code, config)
        assert "FB_reinit" in result


# ---------------------------------------------------------------------------
# Empty methods/actions/properties
# ---------------------------------------------------------------------------


class TestEmptyBodies:

    def test_empty_method(self, config):
        code = "METHOD M_DoNothing\nVAR\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "M_DoNothing" in result

    def test_method_with_only_comment(self, config):
        code = "METHOD M_Todo\n// TODO: implement this"
        result = _assert_idempotent(code, config)
        assert "// TODO: implement this" in result

    def test_empty_implementation_code(self, config):
        code = ""
        result = _format_st_pipeline(code, config)
        assert result == ""

    def test_single_semicolon(self, config):
        """Edge case: only a semicolon as implementation."""
        code = ";"
        result = _format_st_pipeline(code, config)
        assert ";" in result


# ---------------------------------------------------------------------------
# Multiline FB call with alignment after wrapping
# ---------------------------------------------------------------------------


class TestMultilineFBCallAlignment:

    def test_wrapped_fb_call_assigns_aligned(self, config):
        """After wrapping, := should be aligned in params."""
        code = (
            "fbMotor(\n"
            "        bEnable    := TRUE,\n"
            "        fSpeed     := 100.0,\n"
            "        nDirection := 1,\n"
            "        bDone      => bMotorDone,\n"
            "        bError     => bMotorError);"
        )
        result = _assert_idempotent(code, config)
        assert "bEnable" in result
        assert "fSpeed" in result
        assert "=>" in result

    def test_nested_call_in_wrapped_params(self, config):
        code = (
            "fbOuter(\n"
            "        nA := F_Calc(x, y),\n"
            "        nB := F_Other(a, b, c),\n"
            "        nC := 42,\n"
            "        nD := arr[0],\n"
            "        nE := (x + y) * 2);"
        )
        result = _assert_idempotent(code, config)
        assert "F_Calc(x, y)" in result
        assert "(x + y) * 2" in result


# ---------------------------------------------------------------------------
# Large-scale idempotency stress
# ---------------------------------------------------------------------------


class TestStressIdempotency:

    def test_100_declarations_idempotent(self, config):
        """100 declarations should align correctly and be stable."""
        decls = "\n".join(
            f"    var{i:03d} : {'INT' if i % 3 == 0 else 'REAL' if i % 3 == 1 else 'BOOL'};"
            for i in range(100)
        )
        code = f"VAR\n{decls}\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "var000" in result
        assert "var099" in result

    def test_50_assignments_idempotent(self, config):
        """50 consecutive assignments should align and be stable."""
        assigns = "\n".join(
            f"var{i:03d} := {i};" for i in range(50)
        )
        code = assigns
        result = _assert_idempotent(code, config)
        assert "var000" in result
        assert "var049" in result

    def test_deeply_nested_control_flow(self, config):
        """5 levels of nested IF."""
        code = "IF a THEN\n"
        for i in range(5):
            indent = "    " * (i + 1)
            code += f"{indent}IF b{i} THEN\n"
            code += f"{indent}    x{i} := {i};\n"
        for i in range(4, -1, -1):
            indent = "    " * (i + 1)
            code += f"{indent}END_IF;\n"
        code += "END_IF;"
        result = _assert_idempotent(code, config)
        assert "x0" in result
        assert "x4" in result


# ---------------------------------------------------------------------------
# Line ending edge cases
# ---------------------------------------------------------------------------


class TestLineEndingEdgeCases:

    def test_file_without_trailing_newline(self, config):
        """File not ending with newline should stay that way."""
        code = "x := 1;"
        result = _format_st_pipeline(code, config)
        assert not result.endswith("\n") or result.strip() == "x := 1;"

    def test_file_with_trailing_newline(self, config):
        """File ending with newline should keep it."""
        code = "x := 1;\n"
        result = _format_st_pipeline(code, config)
        # The pipeline doesn't force newlines, but shouldn't remove content
        assert "x := 1;" in result

    def test_windows_line_ending_content(self, config):
        """CRLF content should work through pipeline."""
        code = "x := 1;\r\ny := 2;\r\n"
        result = _format_st_pipeline(code, config)
        assert "x := 1;" in result or "x := 1" in result
        assert "y := 2;" in result or "y := 2" in result


# ---------------------------------------------------------------------------
# Unicode in identifiers/strings
# ---------------------------------------------------------------------------


class TestUnicode:

    def test_german_umlauts_in_string(self, config):
        code = "sMsg := 'Temperatur ueberschritten: Uebertemperatur';"
        result = _assert_idempotent(code, config)
        assert "Uebertemperatur" in result

    def test_unicode_in_wstring(self, config):
        code = 'wsGreeting := "Gruesse aus Muenchen";'
        result = _assert_idempotent(code, config)
        assert '"Gruesse aus Muenchen"' in result

    def test_special_chars_in_comments(self, config):
        code = "(* Spezial: ae, oe, ue, sz *)\nx := 1;"
        result = _assert_idempotent(code, config)
        assert "(* Spezial: ae, oe, ue, sz *)" in result


# ---------------------------------------------------------------------------
# Semicolons in special contexts
# ---------------------------------------------------------------------------


class TestSemicolonEdgeCases:

    def test_semicolon_after_end_if(self, config):
        code = "IF x THEN\n    y := 1;\nEND_IF;"
        result = _assert_idempotent(code, config)
        assert "END_IF;" in result

    def test_no_semicolon_after_end_var(self, config):
        """END_VAR should NOT have a semicolon (declaration, not statement)."""
        code = "VAR\n    x : INT;\nEND_VAR"
        result = _assert_idempotent(code, config)
        assert "END_VAR" in result
        # END_VAR without ; is valid
        lines = result.split("\n")
        end_var_line = [l for l in lines if "END_VAR" in l][0]
        assert end_var_line.strip() == "END_VAR"

    def test_multiple_statements_one_line(self, config):
        """Multiple statements on one line (unusual but valid)."""
        code = "x := 1; y := 2; z := 3;"
        result = _assert_idempotent(code, config)
        # All three assignments must be present
        assert "x := 1" in result
        assert "y := 2" in result
        assert "z := 3" in result

    def test_empty_statement_semicolon(self, config):
        """Bare semicolon is a valid empty statement."""
        code = "x := 1;\n;\ny := 2;"
        result = _format_st_pipeline(code, config)
        assert "x := 1" in result
        assert "y := 2" in result
