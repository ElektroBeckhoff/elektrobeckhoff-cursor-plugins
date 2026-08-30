"""CLI runner for TwinCAT Language Server (stdio or TCP socket)."""
from __future__ import annotations

import argparse
import logging
import sys

from .server import create_lsp_server


def main() -> None:
    parser = argparse.ArgumentParser(description="TwinCAT 3 Language Server (LSP)")
    parser.add_argument("--tcp", action="store_true", help="Use TCP socket instead of stdio")
    parser.add_argument("--host", default="127.0.0.1", help="TCP host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=2087, help="TCP port to bind to (default: 2087)")
    parser.add_argument("--log-file", default=None, help="File to log output to")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_handlers = []
    if args.log_file:
        log_handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    else:
        log_handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=log_handlers,
    )

    server = create_lsp_server()

    if args.tcp:
        logging.info(f"Starting TwinCAT Language Server on TCP {args.host}:{args.port}")
        server.start_tcp(args.host, args.port)
    else:
        logging.info("Starting TwinCAT Language Server on stdio")
        server.start_io()


if __name__ == "__main__":
    main()
