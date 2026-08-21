"""MSHC archive indexing, cache management, and search/read orchestrator."""

import html
import logging
import os
import sqlite3
import threading
import time
import zipfile
from typing import Any, Dict, List, Optional, Set

from infosys_mshc.constants import (
    DEFAULT_MAX_FULL_TEXT_CHARS,
    DEFAULT_MAX_METHODS,
    DEFAULT_MAX_PARAMS,
    FTS5_BODY_LIMIT,
    NOT_INSTALLED_MSG,
    RE_DESCRIPTION_META,
    RE_DISPLAY_VERSION,
    RE_TITLE,
    SCHEMA_VERSION,
    SECTION_ALIASES,
)
from infosys_mshc.html_parser import (
    detect_type,
    extract_library_and_parent,
    extract_methods,
    extract_requirements,
    extract_syntax,
    parse_page,
    parse_param_table,
    split_sections,
    strip_tags,
)
from infosys_mshc.paths import DEFAULT_MSHC_PATH, fts5_db_path_for
from infosys_mshc.search import (
    score_entry,
    search_auto,
    search_fulltext,
    search_fulltext_legacy,
    search_symbol,
    search_title,
)

log = logging.getLogger("twincat-mcp.infosys-mshc")


class InfoSysMshcIndex:
    """In-memory index and query engine for a Beckhoff .mshc offline documentation archive."""

    _FTS5_BODY_LIMIT = FTS5_BODY_LIMIT
    _SECTION_ALIASES = SECTION_ALIASES

    def __init__(self, mshc_path: str = DEFAULT_MSHC_PATH):
        self._mshc_path = mshc_path
        self._entries: List[Dict[str, Any]] = []
        self._title_map: Dict[str, Dict[str, Any]] = {}
        self._fts5_conn: Optional[sqlite3.Connection] = None
        self._zf: Optional[zipfile.ZipFile] = None
        self._zip_lock = threading.Lock()
        self._mshc_mtime: float = -1.0
        self._mshc_size: int = -1
        self._loaded = False

    def close(self) -> None:
        """Close the SQLite FTS5 database connection and cached ZipFile handle."""
        if self._fts5_conn is not None:
            try:
                self._fts5_conn.close()
            except Exception:
                pass
            self._fts5_conn = None

        with self._zip_lock:
            if self._zf is not None:
                try:
                    self._zf.close()
                except Exception:
                    pass
                self._zf = None

    def __del__(self) -> None:
        self.close()

    def __enter__(self) -> "InfoSysMshcIndex":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _get_zip(self) -> zipfile.ZipFile:
        """Get or open a persistent ZipFile handle, checking for mtime changes."""
        if not os.path.isfile(self._mshc_path):
            raise FileNotFoundError(
                f"MSHC file not found: {self._mshc_path}\n{NOT_INSTALLED_MSG}"
            )

        stat = os.stat(self._mshc_path)
        with self._zip_lock:
            if self._zf is not None:
                if (
                    self._mshc_mtime != stat.st_mtime
                    or self._mshc_size != stat.st_size
                ):
                    log.info(
                        "MSHC archive changed on disk (mtime/size mismatch), reloading: %s",
                        self._mshc_path,
                    )
                    try:
                        self._zf.close()
                    except Exception:
                        pass
                    self._zf = None
                    self._loaded = False
                    if self._fts5_conn is not None:
                        try:
                            self._fts5_conn.close()
                        except Exception:
                            pass
                        self._fts5_conn = None

            if self._zf is None:
                self._zf = zipfile.ZipFile(self._mshc_path, "r")
                self._mshc_mtime = stat.st_mtime
                self._mshc_size = stat.st_size

            return self._zf

    def _ensure_index(self) -> None:
        """Ensure that index metadata and database connections are loaded."""
        if not os.path.isfile(self._mshc_path):
            raise FileNotFoundError(
                f"MSHC file not found: {self._mshc_path}\n{NOT_INSTALLED_MSG}"
            )

        stat = os.stat(self._mshc_path)
        if (
            self._loaded
            and self._mshc_mtime == stat.st_mtime
            and self._mshc_size == stat.st_size
        ):
            return

        fts5_db = fts5_db_path_for(self._mshc_path)
        if self._try_load_db(fts5_db):
            self._loaded = True
            return

        self._build_index()
        self._loaded = True

    def _try_load_db(self, fts5_db: str) -> bool:
        """Open and validate an existing FTS5 database (Schema v2), load entries."""
        if not os.path.isfile(fts5_db):
            return False
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(fts5_db)
            stat = os.stat(self._mshc_path)
            meta = dict(
                conn.execute("SELECT key, value FROM meta").fetchall()
            )
            if meta.get("schema_version") != SCHEMA_VERSION:
                log.info(
                    "FTS5 DB schema version mismatch (%s vs %s), rebuilding",
                    meta.get("schema_version"),
                    SCHEMA_VERSION,
                )
                conn.close()
                return False
            if meta.get("mshc_path") != self._mshc_path:
                conn.close()
                return False
            if float(meta.get("mshc_mtime", -1)) != stat.st_mtime:
                conn.close()
                return False
            if int(meta.get("mshc_size", -1)) != stat.st_size:
                conn.close()
                return False

            rows = conn.execute(
                "SELECT title, type, component, path, library, parent, qualified_name, description"
                " FROM entries"
            ).fetchall()
            if not rows:
                conn.close()
                return False

            self._entries = [
                {
                    "title": r[0],
                    "type": r[1],
                    "component": r[2],
                    "path": r[3],
                    "library": r[4] or "",
                    "parent": r[5] or "",
                    "qualified_name": r[6] or "",
                    "description": r[7] or "",
                }
                for r in rows
            ]
            self._title_map = {e["title"].lower(): e for e in self._entries}
            self._fts5_conn = conn
            self._mshc_mtime = stat.st_mtime
            self._mshc_size = stat.st_size
            log.info(
                "Loaded MSHC index from DB (%d entries, schema v%s)",
                len(self._entries),
                SCHEMA_VERSION,
            )
            return True
        except Exception as exc:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            log.debug("FTS5 DB load failed: %s", exc)
            return False

    def _build_index(self) -> None:
        """Parse MSHC archive and populate SQLite FTS5 database (Schema v2)."""
        if not os.path.isfile(self._mshc_path):
            raise FileNotFoundError(
                f"MSHC file not found: {self._mshc_path}\n{NOT_INSTALLED_MSG}"
            )
        log.info("Building MSHC index from %s ...", self._mshc_path)
        t0 = time.time()
        entries: List[Dict[str, Any]] = []

        fts5_db = fts5_db_path_for(self._mshc_path)
        use_memory = False
        for suffix in ("", "-shm", "-wal"):
            p = fts5_db + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    use_memory = True
        if use_memory:
            log.warning("FTS5 DB locked, using in-memory index (non-persistent)")
            conn = sqlite3.connect(":memory:")
        else:
            conn = sqlite3.connect(fts5_db)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        stat = os.stat(self._mshc_path)
        conn.execute(
            "INSERT INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,)
        )
        conn.execute(
            "INSERT INTO meta VALUES ('mshc_path', ?)", (self._mshc_path,)
        )
        conn.execute(
            "INSERT INTO meta VALUES ('mshc_mtime', ?)", (str(stat.st_mtime),)
        )
        conn.execute(
            "INSERT INTO meta VALUES ('mshc_size', ?)", (str(stat.st_size),)
        )
        conn.execute("""
            CREATE TABLE entries (
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                component TEXT NOT NULL,
                path TEXT NOT NULL PRIMARY KEY,
                library TEXT NOT NULL DEFAULT '',
                parent TEXT NOT NULL DEFAULT '',
                qualified_name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE pages USING fts5(
                title, type, component, path, library, parent, qualified_name, body,
                tokenize='unicode61'
            )
        """)

        with zipfile.ZipFile(self._mshc_path, "r") as zf:
            for info in zf.infolist():
                if not info.filename.endswith(".html"):
                    continue
                try:
                    raw_bytes = zf.read(info.filename)
                    header = raw_bytes[:4096].decode("utf-8", errors="ignore")
                    m = RE_TITLE.search(header)
                    if not m:
                        continue
                    title = html.unescape(m.group(1)).strip()
                    if not title:
                        continue
                    parts = info.filename.split("/")
                    component = parts[0] if len(parts) > 1 else ""
                    desc_m = RE_DESCRIPTION_META.search(header)
                    desc = (
                        html.unescape(desc_m.group(1)).strip()
                        if desc_m
                        else ""
                    )
                    syntax = extract_syntax(header)
                    sym_type = detect_type(title, description=desc, syntax=syntax)
                    dv_m = RE_DISPLAY_VERSION.search(header)
                    display_version = (
                        html.unescape(dv_m.group(1)).strip() if dv_m else ""
                    )
                    library, parent, qualified_name = extract_library_and_parent(
                        title, display_version, component
                    )

                    entries.append({
                        "title": title,
                        "type": sym_type,
                        "component": component,
                        "path": info.filename,
                        "library": library,
                        "parent": parent,
                        "qualified_name": qualified_name,
                        "description": desc,
                    })
                    body = strip_tags(
                        raw_bytes[: self._FTS5_BODY_LIMIT].decode(
                            "utf-8", errors="ignore"
                        )
                    )
                    conn.execute(
                        "INSERT INTO entries VALUES(?,?,?,?,?,?,?,?)",
                        (
                            title,
                            sym_type,
                            component,
                            info.filename,
                            library,
                            parent,
                            qualified_name,
                            desc,
                        ),
                    )
                    conn.execute(
                        "INSERT INTO pages(title, type, component, path, library, parent, qualified_name, body)"
                        " VALUES(?,?,?,?,?,?,?,?)",
                        (
                            title,
                            sym_type,
                            component,
                            info.filename,
                            library,
                            parent,
                            qualified_name,
                            body,
                        ),
                    )
                except Exception:
                    continue

        conn.commit()
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self._fts5_conn = conn
        self._entries = entries
        self._title_map = {e["title"].lower(): e for e in entries}
        self._mshc_mtime = stat.st_mtime
        self._mshc_size = stat.st_size
        elapsed = time.time() - t0
        log.info(
            "MSHC index built: %d entries in %.1fs (DB: %s, schema v%s)",
            len(entries),
            elapsed,
            fts5_db,
            SCHEMA_VERSION,
        )

    def search(
        self,
        query: str,
        limit: int = 10,
        mode: str = "auto",
        library: str = "",
        parent: str = "",
    ) -> Dict[str, Any]:
        """Search the documentation archive by query and mode, with optional library/parent filters."""
        self._ensure_index()
        q = query.strip()
        if not q:
            return {"query": query, "mode": mode, "count": 0, "results": []}

        q_lower = q.lower()

        if mode == "title":
            results = self._search_title(q_lower, limit, library=library, parent=parent)
        elif mode == "symbol":
            results = self._search_symbol(q_lower, limit, library=library, parent=parent)
        elif mode == "fulltext":
            results = self._search_fulltext(q, limit, library=library, parent=parent)
        else:
            results = self._search_auto(q, q_lower, limit, library=library, parent=parent)

        return {
            "query": query,
            "mode": mode,
            "count": len(results),
            "results": results,
        }

    def read_page(
        self,
        html_path: str,
        include_full_text: bool = True,
        max_full_text_chars: int = DEFAULT_MAX_FULL_TEXT_CHARS,
        max_methods: int = DEFAULT_MAX_METHODS,
        max_params: int = DEFAULT_MAX_PARAMS,
    ) -> Dict[str, Any]:
        """Read a documentation page by archive-relative path using cached ZipFile handle."""
        zf = self._get_zip()
        with self._zip_lock:
            try:
                raw = zf.read(html_path).decode("utf-8", errors="replace")
            except KeyError:
                raise FileNotFoundError(
                    f"Page not found in MSHC archive: {html_path}"
                )
        return self._parse_page(
            raw,
            html_path,
            include_full_text=include_full_text,
            max_full_text_chars=max_full_text_chars,
            max_methods=max_methods,
            max_params=max_params,
        )

    # ------------------------------------------------------------------
    # Compatibility methods / delegators
    # ------------------------------------------------------------------

    def _search_auto(
        self,
        q: str,
        q_lower: str,
        limit: int,
        library: str = "",
        parent: str = "",
    ) -> List[Dict[str, Any]]:
        return search_auto(
            self._entries,
            self._title_map,
            q,
            q_lower,
            limit,
            self._fts5_conn,
            self._mshc_path,
            library=library,
            parent=parent,
        )

    def _search_title(
        self,
        q_lower: str,
        limit: int,
        library: str = "",
        parent: str = "",
    ) -> List[Dict[str, Any]]:
        return search_title(self._entries, q_lower, limit, library=library, parent=parent)

    def _search_symbol(
        self,
        q_lower: str,
        limit: int,
        library: str = "",
        parent: str = "",
    ) -> List[Dict[str, Any]]:
        return search_symbol(self._entries, q_lower, limit, library=library, parent=parent)

    def _search_fulltext(
        self,
        query: str,
        limit: int,
        exclude: Optional[Set[str]] = None,
        library: str = "",
        parent: str = "",
    ) -> List[Dict[str, Any]]:
        return search_fulltext(
            self._fts5_conn,
            self._mshc_path,
            self._entries,
            query,
            limit,
            exclude,
            library=library,
            parent=parent,
        )

    def _search_fulltext_legacy(
        self,
        query: str,
        limit: int,
        exclude: Optional[Set[str]] = None,
        library: str = "",
        parent: str = "",
    ) -> List[Dict[str, Any]]:
        return search_fulltext_legacy(
            self._mshc_path,
            self._entries,
            query,
            limit,
            exclude,
            library=library,
            parent=parent,
        )

    @staticmethod
    def _scored(entry: Dict[str, Any], score: int) -> Dict[str, Any]:
        return score_entry(entry, score)

    def _parse_page(
        self,
        raw_html: str,
        html_path: str,
        include_full_text: bool = True,
        max_full_text_chars: int = DEFAULT_MAX_FULL_TEXT_CHARS,
        max_methods: int = DEFAULT_MAX_METHODS,
        max_params: int = DEFAULT_MAX_PARAMS,
    ) -> Dict[str, Any]:
        return parse_page(
            raw_html,
            html_path,
            include_full_text=include_full_text,
            max_full_text_chars=max_full_text_chars,
            max_methods=max_methods,
            max_params=max_params,
        )

    @staticmethod
    def _extract_syntax(raw_html: str) -> str:
        return extract_syntax(raw_html)

    @classmethod
    def _split_sections(cls, raw_html: str) -> Dict[str, str]:
        return split_sections(raw_html)

    @staticmethod
    def _parse_param_table(section_html: str) -> List[Dict[str, str]]:
        return parse_param_table(section_html)

    @staticmethod
    def _extract_methods(section_html: str) -> List[Dict[str, str]]:
        return extract_methods(section_html)

    @staticmethod
    def _extract_requirements(section_html: str) -> Dict[str, str]:
        return extract_requirements(section_html)
