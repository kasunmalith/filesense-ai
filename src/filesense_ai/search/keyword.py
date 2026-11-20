from __future__ import annotations

import re
import sqlite3

from filesense_ai.core.models import SearchHit


def fts_query(query: str) -> str:
    terms = re.findall(r"[\w\u0080-\uffff]+", query, flags=re.UNICODE)
    return " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:20])


def keyword_search(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 100,
    offset: int = 0,
    kind: str | None = None,
    root_ids: list[str] | None = None,
) -> list[SearchHit]:
    terms = re.findall(r"[\w\u0080-\uffff]+", query, flags=re.UNICODE)[:20]
    if not terms:
        return []
    expressions = [fts_query(query), " OR ".join(f'"{term}"' for term in terms)]
    params: list[object] = []
    filters = ["f.status='ok'"]
    if kind:
        if kind.startswith("ext:"):
            filters.append("lower(f.path) LIKE ? ESCAPE '\\'")
            params.append(
                "%" + kind[4:].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").lower()
            )
        else:
            filters.append("f.kind=?")
            params.append(kind)
    if root_ids:
        filters.append(f"f.root_id IN ({','.join('?' for _ in root_ids)})")
        params.extend(root_ids)
    sql = f"""SELECT f.id file_id,f.path,f.kind,c.text snippet,s.locator,
        bm25(chunk_fts,0,0,1.0,0.25,1.0) rank
        FROM chunk_fts JOIN chunks c ON c.id=CAST(chunk_fts.chunk_id AS INTEGER)
        JOIN files f ON f.id=chunk_fts.file_id JOIN roots r ON r.id=f.root_id JOIN segments s ON s.id=c.segment_id
        WHERE chunk_fts MATCH ? AND r.enabled=1 AND {" AND ".join(filters)}
        ORDER BY rank ASC, f.path COLLATE NOCASE LIMIT ? OFFSET ?"""
    rows = []
    for expression in expressions:
        rows = connection.execute(sql, [expression, *params, limit, offset]).fetchall()
        if rows:
            break
    return [
        SearchHit(
            row["file_id"],
            __import__("pathlib").Path(row["path"]),
            __import__("pathlib").Path(row["path"]).name,
            row["kind"],
            row["snippet"],
            row["locator"],
            1.0 / (1 + index),
            ("matching words",),
        )
        for index, row in enumerate(rows)
    ]
