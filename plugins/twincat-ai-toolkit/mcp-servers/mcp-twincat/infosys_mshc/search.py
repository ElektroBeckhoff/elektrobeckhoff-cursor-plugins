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
        inner = q[1:-1].strip()
        if not inner or not any(c.isalnum() for c in inner):
            return ""
        return q
    if "*" in q and " " not in q:
        cleaned = RE_FTS5_SPECIAL.sub("", q)
        if any(c.isalnum() for c in cleaned):
            return cleaned
        return ""
    tokens = RE_FTS5_SPECIAL.sub(" ", q).split()
    valid_tokens = [t for t in tokens if t and any(c.isalnum() for c in t)]
    return " ".join(valid_tokens)


_fts5_sanitize = fts5_sanitize


def score_entry(entry: Dict[str, Any], score: int) -> Dict[str, Any]:
    """Wrap an index entry with a match relevance score and metadata."""
    r: Dict[str, Any] = {
        "title": entry["title"],
        "type": entry["type"],
        "component": entry["component"],
        "path": entry["path"],
        "score": score,
    }
    if entry.get("library"):
        r["library"] = entry["library"]
    if entry.get("parent"):
        r["parent"] = entry["parent"]
    if entry.get("qualified_name"):
        r["qualified_name"] = entry["qualified_name"]
    desc = entry.get("description", "")
    if desc:
        r["description"] = desc
    return r


_scored = score_entry


def _matches_filters(entry: Dict[str, Any], library: str = "", parent: str = "") -> bool:
    """Check whether an entry satisfies optional library and parent filters."""
    if library:
        lib_e = entry.get("library", "").lower()
        comp_e = entry.get("component", "").lower()
        lib_q = library.lower()
        if lib_q not in lib_e and lib_q not in comp_e:
            return False
    if parent:
        par_e = entry.get("parent", "").lower()
        tit_e = entry.get("title", "").lower()
        desc_e = entry.get("description", "").lower()
        comp_e = entry.get("component", "").lower()
        p_low = parent.lower()
        if (
            par_e != p_low
            and not tit_e.startswith(p_low + ".")
            and not tit_e.startswith(p_low + "::")
            and p_low not in desc_e
            and p_low.replace("fb_", "") not in comp_e
        ):
            return False
    return True


def search_title(
    entries: List[Dict[str, Any]],
    q_lower: str,
    limit: int,
    library: str = "",
    parent: str = "",
) -> List[Dict[str, Any]]:
    """Search entries by exact, prefix, or substring title match."""
    results: List[Dict[str, Any]] = []
    for e in entries:
        if len(results) >= limit:
            break
        if not _matches_filters(e, library, parent):
            continue
        t = e["title"].lower()
        if t == q_lower:
            results.append(score_entry(e, 100))
        elif t.startswith(q_lower):
            results.append(score_entry(e, 90))
        elif q_lower in t:
            results.append(score_entry(e, 70))
    return results


def search_symbol(
    entries: List[Dict[str, Any]],
    q_lower: str,
    limit: int,
    library: str = "",
    parent: str = "",
) -> List[Dict[str, Any]]:
    """Search entries by title filtered to IEC symbols (excluding articles)."""
    results: List[Dict[str, Any]] = []
    for e in entries:
        if len(results) >= limit:
            break
        if e.get("type") == "article":
            continue
        if not _matches_filters(e, library, parent):
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
    library: str = "",
    parent: str = "",
) -> List[Dict[str, Any]]:
    """Search documentation pages by BM25 ranking using SQLite FTS5."""
    if fts5_conn is None:
        return search_fulltext_legacy(mshc_path, entries, query, limit, exclude, library, parent)

    exclude = exclude or set()
    fts_query = fts5_sanitize(query)
    if not fts_query:
        return []

    try:
        rows = fts5_conn.execute(
            """
            SELECT title, type, component, path, library, parent, qualified_name,
                   bm25(pages) AS score,
                   snippet(pages, 7, '>>>', '<<<', '...', 32) AS snippet
            FROM pages
            WHERE pages MATCH ?
            ORDER BY bm25(pages)
            LIMIT ?
            """,
            (fts_query, (limit + len(exclude)) * 3),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        log.debug("FTS5 query failed (%s), returning empty list", exc)
        return []

    results: List[Dict[str, Any]] = []
    for title, typ, comp, path, lib, par, qname, _bm25_score, snippet in rows:
        if path in exclude:
            continue
        entry_meta = {"library": lib or "", "parent": par or "", "title": title}
        if not _matches_filters(entry_meta, library, parent):
            continue
        if len(results) >= limit:
            break
        r: Dict[str, Any] = {
            "title": title,
            "type": typ,
            "component": comp,
            "path": path,
            "score": 30,
            "snippet": (snippet or "").replace("\n", " ").strip(),
        }
        if lib:
            r["library"] = lib
        if par:
            r["parent"] = par
        if qname:
            r["qualified_name"] = qname
        results.append(r)
    return results


def search_fulltext_legacy(
    mshc_path: str,
    entries: List[Dict[str, Any]],
    query: str,
    limit: int,
    exclude: Optional[Set[str]] = None,
    library: str = "",
    parent: str = "",
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
            if not _matches_filters(e, library, parent):
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
    library: str = "",
    parent: str = "",
) -> List[Dict[str, Any]]:
    """Auto-search strategy: exact title -> prefix -> substring -> BM25 fulltext fallback."""
    results: List[Dict[str, Any]] = []

    exact = title_map.get(query_lower)
    if exact and _matches_filters(exact, library, parent):
        results.append(score_entry(exact, 100))

    seen_paths = {r["path"] for r in results}
    for e in entries:
        if len(results) >= limit:
            break
        if not _matches_filters(e, library, parent):
            continue
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
            if not _matches_filters(e, library, parent):
                continue
            if query_lower in e["title"].lower():
                results.append(score_entry(e, 70))
                seen_paths.add(e["path"])

    if not results:
        ft = search_fulltext(
            fts5_conn,
            mshc_path,
            entries,
            query,
            limit,
            exclude=seen_paths,
            library=library,
            parent=parent,
        )
        results.extend(ft)

    return results[:limit]
