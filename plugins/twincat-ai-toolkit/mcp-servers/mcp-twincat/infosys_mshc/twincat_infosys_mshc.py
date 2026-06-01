"""
Offline InfoSys MSHC search for Beckhoff TwinCAT documentation.

Reads the locally installed .mshc file (ZIP archive with ~55k HTML pages)
from the Microsoft Help Viewer and provides title-based index search plus
full page reading with structured extraction of syntax blocks, I/O tables,
methods, and requirements.

No external dependencies beyond the Python standard library.
"""

import html
import json
import logging
import os
import re
import sqlite3
import time
import zipfile
from typing import Dict, List, Optional

log = logging.getLogger("twincat-mcp.infosys-mshc")

_MSHC_BASE_DIR = (
    r"C:\ProgramData\Microsoft\HelpLibrary2\Catalogs\VisualStudio15\ContentStore"
)

_LANG_MAP = {
    "en": ("EN-US", "BKINFOSYS3_VS_100_EN-US.9.mshc"),
    "de": ("DE-DE", "BKINFOSYS3_VS_100_DE-DE.9.mshc"),
}

DEFAULT_MSHC_PATH = os.path.join(
    _MSHC_BASE_DIR, "EN-US", "BKINFOSYS3_VS_100_EN-US.9.mshc"
)


def resolve_mshc_path(language: str = "en", file_path: str = "") -> str:
    """Resolve the .mshc file path from language code or explicit path."""
    if file_path:
        return file_path
    lang = language.lower().strip()
    if lang in _LANG_MAP:
        folder, filename = _LANG_MAP[lang]
        return os.path.join(_MSHC_BASE_DIR, folder, filename)
    return DEFAULT_MSHC_PATH

_TYPE_PREFIXES = {
    "FB_": "FUNCTION_BLOCK",
    "ST_": "STRUCT",
    "E_": "ENUM",
    "I_": "INTERFACE",
    "F_": "FUNCTION",
    "T_": "TYPE",
}

_RE_TITLE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_MULTI_WS = re.compile(r"[ \t]+")
_RE_MULTI_NL = re.compile(r"\n{3,}")
_RE_H2 = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
_RE_TABLE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_RE_TABLE_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_RE_CODE_BLOCK = re.compile(
    r"<(?:pre|code)[^>]*>(.*?)</(?:pre|code)>", re.IGNORECASE | re.DOTALL
)
_RE_DESCRIPTION_META = re.compile(
    r'<meta\s+name="Description"\s+content="(.*?)"', re.IGNORECASE
)
_RE_DISPLAY_VERSION = re.compile(
    r'<meta\s+name="Microsoft\.Help\.DisplayVersion"\s+content="(.*?)"',
    re.IGNORECASE,
)


def _strip_tags(text: str) -> str:
    text = text.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    text = _RE_TAG.sub("", text)
    text = html.unescape(text)
    text = _RE_MULTI_WS.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = _RE_MULTI_NL.sub("\n\n", text)
    return text.strip()


def _detect_type(title: str) -> str:
    for prefix, type_name in _TYPE_PREFIXES.items():
        if title.startswith(prefix):
            return type_name
    return "article"


def _cache_dir() -> str:
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "twincat-mcp-infosys-mshc")
    os.makedirs(d, exist_ok=True)
    return d


def _cache_path_for(mshc_path: str) -> str:
    """Derive a JSON cache file path in temp dir, keyed by mshc basename."""
    base = os.path.splitext(os.path.basename(mshc_path))[0]
    return os.path.join(_cache_dir(), f"_index_cache_{base}.json")


def _fts5_db_path_for(mshc_path: str) -> str:
    """Derive a SQLite FTS5 database path in temp dir, keyed by mshc basename."""
    base = os.path.splitext(os.path.basename(mshc_path))[0]
    return os.path.join(_cache_dir(), f"_fts5_{base}.db")


_RE_FTS5_SPECIAL = re.compile(r'[^\w\s*"_]', re.UNICODE)


def _fts5_sanitize(query: str) -> str:
    """Sanitize a user query for FTS5 MATCH syntax.

    Passes through phrases ("..."), prefix wildcards (term*), and plain
    words. Strips characters that are FTS5 operators or invalid syntax.
    """
    q = query.strip()
    if not q:
        return ""
    if q.startswith('"') and q.endswith('"'):
        return q
    if "*" in q and " " not in q:
        return _RE_FTS5_SPECIAL.sub("", q)
    tokens = _RE_FTS5_SPECIAL.sub(" ", q).split()
    return " ".join(t for t in tokens if t)


class InfoSysMshcIndex:
    """In-memory index over a Beckhoff .mshc offline documentation archive."""

    def __init__(self, mshc_path: str = DEFAULT_MSHC_PATH):
        self._mshc_path = mshc_path
        self._entries: List[Dict] = []
        self._title_map: Dict[str, Dict] = {}
        self._fts5_conn: Optional[sqlite3.Connection] = None
        self._loaded = False

    def _ensure_index(self):
        if self._loaded:
            return
        cache = _cache_path_for(self._mshc_path)
        fts5_db = _fts5_db_path_for(self._mshc_path)
        if self._try_load_cache(cache, fts5_db):
            self._loaded = True
            return
        self._build_index()
        self._save_cache(cache)
        self._loaded = True

    def _try_load_cache(self, cache_path: str, fts5_db: str) -> bool:
        if not os.path.isfile(cache_path):
            return False
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("mshc_path") != self._mshc_path:
                return False
            stat = os.stat(self._mshc_path)
            if (data.get("mshc_mtime") != stat.st_mtime
                    or data.get("mshc_size") != stat.st_size):
                return False
            self._entries = data["entries"]
            self._title_map = {e["title"].lower(): e for e in self._entries}

            if not self._try_open_fts5(fts5_db):
                return False

            log.info(
                "Loaded MSHC index from cache (%d entries, FTS5 ready)",
                len(self._entries),
            )
            return True
        except Exception as exc:
            log.debug("Cache load failed: %s", exc)
            return False

    def _try_open_fts5(self, fts5_db: str) -> bool:
        """Open and validate an existing FTS5 database."""
        if not os.path.isfile(fts5_db):
            return False
        try:
            conn = sqlite3.connect(fts5_db)
            stat = os.stat(self._mshc_path)
            meta = dict(
                conn.execute("SELECT key, value FROM meta").fetchall()
            )
            if meta.get("mshc_path") != self._mshc_path:
                conn.close()
                return False
            if float(meta.get("mshc_mtime", -1)) != stat.st_mtime:
                conn.close()
                return False
            if int(meta.get("mshc_size", -1)) != stat.st_size:
                conn.close()
                return False
            cnt = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            if cnt != len(self._entries):
                conn.close()
                return False
            self._fts5_conn = conn
            return True
        except Exception as exc:
            log.debug("FTS5 DB validation failed: %s", exc)
            return False

    _FTS5_BODY_LIMIT = 16384

    def _build_index(self):
        if not os.path.isfile(self._mshc_path):
            raise FileNotFoundError(
                f"MSHC file not found: {self._mshc_path}\n"
                "Install TwinCAT 3 offline documentation via "
                "Help > Add and Remove Help Content in TcXaeShell."
            )
        log.info("Building MSHC index from %s ...", self._mshc_path)
        t0 = time.time()
        entries: List[Dict] = []

        fts5_db = _fts5_db_path_for(self._mshc_path)
        if os.path.exists(fts5_db):
            os.remove(fts5_db)
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
            "INSERT INTO meta VALUES ('mshc_path', ?)", (self._mshc_path,)
        )
        conn.execute(
            "INSERT INTO meta VALUES ('mshc_mtime', ?)", (str(stat.st_mtime),)
        )
        conn.execute(
            "INSERT INTO meta VALUES ('mshc_size', ?)", (str(stat.st_size),)
        )
        conn.execute("""
            CREATE VIRTUAL TABLE pages USING fts5(
                title, type, component, path, body,
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
                    m = _RE_TITLE.search(header)
                    if not m:
                        continue
                    title = html.unescape(m.group(1)).strip()
                    if not title:
                        continue
                    parts = info.filename.split("/")
                    component = parts[0] if len(parts) > 1 else ""
                    sym_type = _detect_type(title)
                    entries.append({
                        "title": title,
                        "type": sym_type,
                        "component": component,
                        "path": info.filename,
                        "size": info.file_size,
                    })
                    body = _strip_tags(
                        raw_bytes[: self._FTS5_BODY_LIMIT].decode(
                            "utf-8", errors="ignore"
                        )
                    )
                    conn.execute(
                        "INSERT INTO pages(title, type, component, path, body)"
                        " VALUES(?,?,?,?,?)",
                        (title, sym_type, component, info.filename, body),
                    )
                except Exception:
                    continue

        conn.commit()
        conn.execute("PRAGMA synchronous=NORMAL")
        self._fts5_conn = conn
        self._entries = entries
        self._title_map = {e["title"].lower(): e for e in entries}
        elapsed = time.time() - t0
        log.info(
            "MSHC index built: %d entries in %.1fs (FTS5 DB: %s)",
            len(entries), elapsed, fts5_db,
        )

    def _save_cache(self, cache_path: str):
        try:
            stat = os.stat(self._mshc_path)
            data = {
                "mshc_path": self._mshc_path,
                "mshc_mtime": stat.st_mtime,
                "mshc_size": stat.st_size,
                "entries": self._entries,
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            log.info("MSHC index cache written to %s", cache_path)
        except Exception as exc:
            log.warning("Could not write index cache: %s", exc)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self, query: str, limit: int = 10, mode: str = "auto"
    ) -> Dict:
        self._ensure_index()
        q = query.strip()
        if not q:
            return {"query": query, "mode": mode, "count": 0, "results": []}

        q_lower = q.lower()

        if mode == "title":
            results = self._search_title(q_lower, limit)
        elif mode == "symbol":
            results = self._search_symbol(q_lower, limit)
        elif mode == "fulltext":
            results = self._search_fulltext(q, limit)
        else:
            results = self._search_auto(q, q_lower, limit)

        return {
            "query": query,
            "mode": mode,
            "count": len(results),
            "results": results,
        }

    def _search_auto(
        self, q: str, q_lower: str, limit: int
    ) -> List[Dict]:
        results: List[Dict] = []

        exact = self._title_map.get(q_lower)
        if exact:
            results.append(self._scored(exact, 100))

        seen_paths = {r["path"] for r in results}
        for e in self._entries:
            if len(results) >= limit:
                break
            t = e["title"].lower()
            if t == q_lower and e["path"] not in seen_paths:
                results.append(self._scored(e, 70))
                seen_paths.add(e["path"])
            elif t.startswith(q_lower) and e["path"] not in seen_paths:
                results.append(self._scored(e, 90))
                seen_paths.add(e["path"])

        if len(results) < limit:
            for e in self._entries:
                if len(results) >= limit:
                    break
                if e["path"] in seen_paths:
                    continue
                if q_lower in e["title"].lower():
                    results.append(self._scored(e, 70))
                    seen_paths.add(e["path"])

        if not results:
            ft = self._search_fulltext(
                q, limit, exclude=seen_paths,
            )
            results.extend(ft)

        return results[:limit]

    def _search_title(self, q_lower: str, limit: int) -> List[Dict]:
        results = []
        for e in self._entries:
            if len(results) >= limit:
                break
            t = e["title"].lower()
            if t == q_lower:
                results.append(self._scored(e, 100))
            elif t.startswith(q_lower):
                results.append(self._scored(e, 90))
            elif q_lower in t:
                results.append(self._scored(e, 70))
        return results

    def _search_symbol(self, q_lower: str, limit: int) -> List[Dict]:
        results = []
        for e in self._entries:
            if len(results) >= limit:
                break
            if e["type"] == "article":
                continue
            t = e["title"].lower()
            if t == q_lower:
                results.append(self._scored(e, 100))
            elif t.startswith(q_lower):
                results.append(self._scored(e, 90))
            elif q_lower in t:
                results.append(self._scored(e, 70))
        return results

    def _search_fulltext(
        self, query: str, limit: int, exclude: Optional[set] = None,
    ) -> List[Dict]:
        if self._fts5_conn is None:
            return self._search_fulltext_legacy(query, limit, exclude)

        exclude = exclude or set()
        fts_query = _fts5_sanitize(query)
        if not fts_query:
            return []

        try:
            rows = self._fts5_conn.execute(
                """
                SELECT title, type, component, path,
                       bm25(pages) AS score,
                       snippet(pages, 4, '>>>', '<<<', '...', 32) AS snippet
                FROM pages
                WHERE pages MATCH ?
                ORDER BY bm25(pages)
                LIMIT ?
                """,
                (fts_query, limit + len(exclude)),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            log.debug("FTS5 query failed (%s), falling back", exc)
            return self._search_fulltext_legacy(query, limit, exclude)

        results: List[Dict] = []
        for title, typ, comp, path, bm25_score, snippet in rows:
            if path in exclude:
                continue
            if len(results) >= limit:
                break
            r = {
                "title": title,
                "type": typ,
                "component": comp,
                "path": path,
                "score": 30,
                "snippet": (snippet or "").replace("\n", " ").strip(),
            }
            results.append(r)
        return results

    def _search_fulltext_legacy(
        self, query: str, limit: int, exclude: Optional[set] = None,
    ) -> List[Dict]:
        """Fallback substring search when FTS5 DB is unavailable."""
        if not os.path.isfile(self._mshc_path):
            return []
        exclude = exclude or set()
        q_lower = query.lower()
        results: List[Dict] = []
        _READ_LIMIT = 16384
        with zipfile.ZipFile(self._mshc_path, "r") as zf:
            for e in self._entries:
                if len(results) >= limit:
                    break
                if e["path"] in exclude:
                    continue
                try:
                    raw = zf.read(e["path"])[:_READ_LIMIT].decode(
                        "utf-8", errors="ignore"
                    )
                    text = _strip_tags(raw).lower()
                    if q_lower in text:
                        idx = text.find(q_lower)
                        start = max(0, idx - 80)
                        end = min(len(text), idx + len(q_lower) + 120)
                        snippet = text[start:end].replace("\n", " ").strip()
                        r = self._scored(e, 30)
                        r["snippet"] = f"...{snippet}..."
                        results.append(r)
                except Exception:
                    continue
        return results

    @staticmethod
    def _scored(entry: Dict, score: int) -> Dict:
        return {
            "title": entry["title"],
            "type": entry["type"],
            "component": entry["component"],
            "path": entry["path"],
            "score": score,
        }

    # ------------------------------------------------------------------
    # Read page
    # ------------------------------------------------------------------

    def read_page(self, html_path: str) -> Dict:
        if not os.path.isfile(self._mshc_path):
            raise FileNotFoundError(f"MSHC file not found: {self._mshc_path}")
        with zipfile.ZipFile(self._mshc_path, "r") as zf:
            try:
                raw = zf.read(html_path).decode("utf-8", errors="replace")
            except KeyError:
                raise FileNotFoundError(
                    f"Page not found in MSHC archive: {html_path}"
                )
        return self._parse_page(raw, html_path)

    def _parse_page(self, raw_html: str, html_path: str) -> Dict:
        parts = html_path.split("/")
        component = parts[0] if len(parts) > 1 else ""

        title_m = _RE_TITLE.search(raw_html)
        title = html.unescape(title_m.group(1)).strip() if title_m else ""
        sym_type = _detect_type(title)

        desc_m = _RE_DESCRIPTION_META.search(raw_html)
        description = html.unescape(desc_m.group(1)).strip() if desc_m else ""

        version_m = _RE_DISPLAY_VERSION.search(raw_html)
        display_version = (
            html.unescape(version_m.group(1)).strip() if version_m else ""
        )

        syntax = self._extract_syntax(raw_html)
        sections = self._split_sections(raw_html)

        inputs = self._parse_param_table(sections.get("inputs", ""))
        outputs = self._parse_param_table(sections.get("outputs", ""))
        parameters = self._parse_param_table(sections.get("parameter", ""))
        if not inputs and not outputs and parameters:
            inputs = parameters
            parameters = []

        methods = self._extract_methods(sections.get("methods", ""))
        if not methods:
            methods = self._extract_methods(
                sections.get("event-driven methods (callback methods)", "")
            )

        requirements = self._extract_requirements(
            sections.get("requirements", "")
        )
        if display_version and not requirements.get("library"):
            req_parts = display_version.split("(", 1)
            requirements["library"] = req_parts[0].strip()
            if len(req_parts) > 1:
                requirements["twincat_version"] = req_parts[1].rstrip(")")

        full_text = _strip_tags(raw_html)

        result: Dict = {
            "title": title,
            "component": component,
            "type": sym_type,
            "path": html_path,
            "description": description,
            "syntax": syntax,
        }
        if inputs:
            result["inputs"] = inputs
        if outputs:
            result["outputs"] = outputs
        if parameters:
            result["parameters"] = parameters
        if methods:
            result["methods"] = methods
        if requirements:
            result["requirements"] = requirements
        result["full_text"] = full_text
        return result

    @staticmethod
    def _extract_syntax(raw_html: str) -> str:
        blocks = _RE_CODE_BLOCK.findall(raw_html)
        for block in blocks:
            text = _strip_tags(block)
            if any(kw in text for kw in (
                "FUNCTION_BLOCK", "FUNCTION ", "VAR_INPUT", "VAR_OUTPUT",
                "TYPE ", "METHOD ", "PROPERTY ", "PROGRAM ",
                "END_VAR", "END_TYPE", "END_STRUCT",
            )):
                return text
        return ""

    _SECTION_ALIASES: Dict[str, str] = {
        "eingänge": "inputs",
        "eingaenge": "inputs",
        "ausgänge": "outputs",
        "ausgaenge": "outputs",
        "ein-/ausgänge": "inputs",
        "ein-/ausgaenge": "inputs",
        "methoden": "methods",
        "voraussetzungen": "requirements",
        "ereignisgesteuerte methoden (callback-methoden)":
            "event-driven methods (callback methods)",
    }

    @classmethod
    def _split_sections(cls, raw_html: str) -> Dict[str, str]:
        headings = list(_RE_H2.finditer(raw_html))
        if not headings:
            return {}
        sections: Dict[str, str] = {}
        for i, m in enumerate(headings):
            name = _strip_tags(m.group(1)).strip().lower()
            key = cls._SECTION_ALIASES.get(name, name)
            start = m.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(raw_html)
            sections[key] = raw_html[start:end]
        return sections

    @staticmethod
    def _parse_param_table(section_html: str) -> List[Dict]:
        if not section_html:
            return []
        rows = _RE_TABLE_ROW.findall(section_html)
        params = []
        for row in rows:
            cells = _RE_TABLE_CELL.findall(row)
            if len(cells) < 2:
                continue
            name = _strip_tags(cells[0]).strip()
            typ = _strip_tags(cells[1]).strip()
            desc = _strip_tags(cells[2]).strip() if len(cells) > 2 else ""
            if not name or name.lower() in ("name", "parameter"):
                continue
            params.append({"name": name, "type": typ, "description": desc})
        return params

    @staticmethod
    def _extract_methods(section_html: str) -> List[Dict]:
        if not section_html:
            return []
        rows = _RE_TABLE_ROW.findall(section_html)
        methods: List[Dict] = []
        for row in rows:
            cells = _RE_TABLE_CELL.findall(row)
            if len(cells) < 1:
                continue
            name = _strip_tags(cells[0]).strip()
            desc = _strip_tags(cells[1]).strip() if len(cells) > 1 else ""
            if not name or name.lower() in ("name", "method name", "methodenname"):
                continue
            methods.append({"name": name, "description": desc})
        if methods:
            return methods
        text = _strip_tags(section_html)
        fallback: List[Dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("name"):
                continue
            token = line.split("(")[0].split("-")[0].split(":")[0].strip()
            if token and len(token) < 80 and " " not in token:
                fallback.append({"name": token, "description": ""})
        return fallback

    @staticmethod
    def _extract_requirements(section_html: str) -> Dict:
        if not section_html:
            return {}
        rows = _RE_TABLE_ROW.findall(section_html)
        reqs: Dict = {}
        for row in rows:
            cells = _RE_TABLE_CELL.findall(row)
            if len(cells) < 2:
                continue
            key = _strip_tags(cells[0]).strip().lower()
            val = _strip_tags(cells[1]).strip()
            if "plc lib" in key or "plc librar" in key or "tc3 plc lib" in key:
                reqs["library"] = val
            elif "twincat" in key and "version" in key:
                reqs["twincat_version"] = val
            elif "development" in key or "engineering" in key:
                reqs["development_environment"] = val
            elif "target" in key:
                reqs["target_platform"] = val
        return reqs
