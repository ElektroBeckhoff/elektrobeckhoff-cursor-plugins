"""Search algorithms and query ranking for InfoSys MSHC documentation."""

import logging
import os
import sqlite3
import zipfile
from typing import Any, Dict, List, Optional, Set

from infosys_mshc.constants import READ_LIMIT, RE_FTS5_SPECIAL
from infosys_mshc.html_parser import strip_tags

log = logging.getLogger("twincat-mcp.infosys-mshc")


def fts5_sanitize(query: str) -> str:
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
        return RE_FTS5_SPECIAL.sub("", q)
    tokens = RE_FTS5_SPECIAL.sub(" ", q).split()
    return " ".join(t for t in tokens if t)


_fts5_sanitize = fts5_sanitize


def score_entry(entry: Dict[str, Any], score: int) -> Dict[str, Any]:
    """Wrap an index entry with a match relevance score."""
    r: Dict[str, Any] = {
        "title": entry["title"],
        "type": entry["type"],
        "component": entry["component"],
        "path": entry["path"],
        "score": score,
    }
    desc = entry.get("description", "")
    if desc:
        r["description"] = desc
    return r


_scored = score_entry


def search_title(
    entries: List[Dict[str, Any]], q_lower: str, limit: int
) -> List[Dict[str, Any]]:
    """Search entries by exact, prefix, or substring title match."""
    results: List[Dict[str, Any]] = []
    for e in entries:
        if len(results) >= limit:
            break
        t = e["title"].lower()
        if t == q_lower:
            results.append(score_entry(e, 100))
        elif t.startswith(q_lower):
            results.append(score_entry(e, 90))
        elif q_lower in t:
            results.append(score_entry(e, 70))
    return results


def search_symbol(
    entries: List[Dict[str, Any]], q_lower: str, limit: int
) -> List[Dict[str, Any]]:
    """Search entries by title filtered to IEC symbols (excluding articles)."""
    results: List[Dict[str, Any]] = []
    for e in entries:
        if len(results) >= limit:
            break
        if e.get("type") == "article":
            continue
        t = e["title"].lower()
        if t == q_lower:
            results.append(score_entry(e, 100))
        elif t.startswith(q_lower):
            results.append(score_entry(e, 90))
        elif q_lower in t:
            results.append(score_entry(e, 70))
    return results


def search_fulltext(
    fts5_conn: Optional[sqlite3.Connection],
    mshc_path: str,
    entries: List[Dict[str, Any]],
    query: str,
    limit: int,
    exclude: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Search documentation pages by BM25 ranking using SQLite FTS5."""
    if fts5_conn is None:
        return search_fulltext_legacy(mshc_path, entries, query, limit, exclude)

    exclude = exclude or set()
    fts_query = fts5_sanitize(query)
    if not fts_query:
        return []

    try:
        rows = fts5_conn.execute(
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
        return search_fulltext_legacy(mshc_path, entries, query, limit, exclude)

    results: List[Dict[str, Any]] = []
    for title, typ, comp, path, _bm25_score, snippet in rows:
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


def search_fulltext_legacy(
    mshc_path: str,
    entries: List[Dict[str, Any]],
    query: str,
    limit: int,
    exclude: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Fallback substring search scanning zip content when FTS5 DB is unavailable."""
    if not os.path.isfile(mshc_path):
        return []
    exclude = exclude or set()
    q_lower = query.lower()
    results: List[Dict[str, Any]] = []
    with zipfile.ZipFile(mshc_path, "r") as zf:
        for e in entries:
            if len(results) >= limit:
                break
            if e["path"] in exclude:
                continue
            try:
                raw = zf.read(e["path"])[:READ_LIMIT].decode(
                    "utf-8", errors="ignore"
                )
                text = strip_tags(raw).lower()
                if q_lower in text:
                    idx = text.find(q_lower)
                    start = max(0, idx - 80)
                    end = min(len(text), idx + len(q_lower) + 120)
                    snippet = text[start:end].replace("\n", " ").strip()
                    r = score_entry(e, 30)
                    r["snippet"] = f"...{snippet}..."
                    results.append(r)
            except Exception:
                continue
    return results


def search_auto(
    entries: List[Dict[str, Any]],
    title_map: Dict[str, Dict[str, Any]],
    query: str,
    query_lower: str,
    limit: int,
    fts5_conn: Optional[sqlite3.Connection] = None,
    mshc_path: str = "",
) -> List[Dict[str, Any]]:
    """Auto-search strategy: exact title -> prefix -> substring -> BM25 fulltext fallback."""
    results: List[Dict[str, Any]] = []

    exact = title_map.get(query_lower)
    if exact:
        results.append(score_entry(exact, 100))

    seen_paths = {r["path"] for r in results}
    for e in entries:
        if len(results) >= limit:
            break
        t = e["title"].lower()
        if t == query_lower and e["path"] not in seen_paths:
            results.append(score_entry(e, 70))
            seen_paths.add(e["path"])
        elif t.startswith(query_lower) and e["path"] not in seen_paths:
            results.append(score_entry(e, 90))
            seen_paths.add(e["path"])

    if len(results) < limit:
        for e in entries:
            if len(results) >= limit:
                break
            if e["path"] in seen_paths:
                continue
            if query_lower in e["title"].lower():
                results.append(score_entry(e, 70))
                seen_paths.add(e["path"])

    if not results:
        ft = search_fulltext(
            fts5_conn, mshc_path, entries, query, limit, exclude=seen_paths
        )
        results.extend(ft)

    return results[:limit]
