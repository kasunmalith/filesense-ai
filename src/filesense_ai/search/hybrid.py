from __future__ import annotations

import sqlite3

from filesense_ai.core.models import SearchHit
from filesense_ai.search.keyword import keyword_search
from filesense_ai.search.semantic import TextEmbeddingBackend, semantic_search


def hybrid_search(
    connection: sqlite3.Connection,
    query: str,
    backend: TextEmbeddingBackend | None = None,
    limit: int = 50,
    kind: str | None = None,
    root_ids: list[str] | None = None,
) -> list[SearchHit]:
    keyword = keyword_search(connection, query, limit=limit * 3, kind=kind, root_ids=root_ids)
    semantic = []
    if backend is not None:
        semantic = semantic_search(connection, query, backend, limit=limit * 3)
        if kind:
            semantic = [hit for hit in semantic if hit.kind == kind]
        if root_ids:
            allowed = set(root_ids)
            semantic = [
                hit
                for hit in semantic
                if connection.execute(
                    "SELECT root_id FROM files WHERE id=?", (hit.file_id,)
                ).fetchone()[0]
                in allowed
            ]
    ranks: dict[str, dict[str, object]] = {}
    for source in (keyword, semantic):
        for rank, hit in enumerate(source, 1):
            if kind and kind.startswith("ext:") and hit.path.suffix.lower() != kind[4:].lower():
                continue
            entry = ranks.setdefault(hit.file_id, {"hit": hit, "score": 0.0, "reasons": set()})
            entry["score"] = float(entry["score"]) + 1.0 / (60 + rank)
            entry["reasons"].update(hit.reasons)
            if hit.score > entry["hit"].score:
                entry["hit"] = hit
    values = sorted(
        ranks.values(),
        key=lambda item: (
            -float(item["score"]),
            item["hit"].path.as_posix().casefold(),
            item["hit"].file_id,
        ),
    )
    return [
        SearchHit(
            item["hit"].file_id,
            item["hit"].path,
            item["hit"].filename,
            item["hit"].kind,
            item["hit"].snippet,
            item["hit"].locator,
            float(item["score"]),
            tuple(sorted(item["reasons"])),
        )
        for item in values[:limit]
    ]
