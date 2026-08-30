"""TwinCAT autodocs — generate Markdown API docs from PLC source files."""
from autodocs.paths import resolve_output_root
from autodocs.pipeline import process_folder
from autodocs.types import AutodocsReport

__all__ = ["process_folder", "AutodocsReport", "resolve_output_root"]
