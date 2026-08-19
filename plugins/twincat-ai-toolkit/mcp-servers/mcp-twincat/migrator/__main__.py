"""CLI entry point: ``python -m migrator fbd|cfc|auto``."""
from __future__ import annotations

import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(
            "Usage: python -m migrator <command> [OPTIONS]\n\n"
            "Commands:\n"
            "  fbd   Migrate FBD/FUP (NWL) implementations to ST\n"
            "  cfc   Migrate CFC implementations to ST\n"
            "  auto  Auto-detect NWL/CFC per file and migrate\n"
        )
        return 0 if args and args[0] in ("-h", "--help") else 1

    command = args[0].lower()
    rest = args[1:]

    if command == "fbd":
        from migrator.fbd import main as fbd_main
        return fbd_main(rest)
    if command == "cfc":
        from migrator.cfc import main as cfc_main
        return cfc_main(rest)
    if command == "auto":
        from migrator.router import main as auto_main
        return auto_main(rest)

    print(f"Unknown command: {command!r}. Use fbd, cfc, or auto.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
