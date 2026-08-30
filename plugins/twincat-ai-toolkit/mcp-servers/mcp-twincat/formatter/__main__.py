"""CLI entry point: python -m formatter [OPTIONS] [PATHS...]"""
import sys

from formatter.cli import run_cli

if __name__ == "__main__":
    sys.exit(run_cli())
