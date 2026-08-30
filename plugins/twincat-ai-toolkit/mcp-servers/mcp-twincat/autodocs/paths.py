"""Path resolution for autodocs input/output."""
from __future__ import annotations

from pathlib import Path


def resolve_output_root(input_path: Path, output_path: Path | str | None = None) -> Path:
    """Resolve the project/repo root where docs/ and README.md live.

    When *output_path* is omitted or empty, infer repo root from *input_path*:

    1. Walk upward from ``input_path``; first directory containing ``README.md``
       or ``.git`` wins.
    2. If none found, use ``input_path.parent`` (solution folder → repo root).

    Docs are always written to ``<resolved>/docs/`` by ``process_folder``.
    """
    input_path = input_path.resolve()

    if output_path is not None and str(output_path).strip():
        return Path(output_path).resolve()

    current = input_path
    while True:
        if (current / "README.md").is_file() or (current / ".git").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    return input_path.parent
