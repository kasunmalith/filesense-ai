from __future__ import annotations

import sqlite3
import struct
from typing import Protocol

from filesense_ai.core.errors import ModelUnavailableError, OptionalDependencyError
from filesense_ai.core.models import SearchHit

TEXT_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"


class TextEmbeddingBackend(Protocol):
    @property
    def model_id(self) -> str: ...
    def load(self) -> None: ...
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_queries(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerBackend:
    def __init__(self, cache_path: str | None = None, local_files_only: bool = True) -> None:
        self.cache_path, self.local_files_only, self._model = cache_path, local_files_only, None

    @property
    def model_id(self) -> str:
        return TEXT_MODEL_ID

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise OptionalDependencyError(
                "Install the semantic extra to use local text embeddings"
            ) from exc
        try:
            self._model = SentenceTransformer(
                self.model_id,
                cache_folder=self.cache_path,
                device="cpu",
                local_files_only=self.local_files_only,
            )
        except Exception as exc:
            raise ModelUnavailableError(
                "The text model is not cached. Use Settings to download it first."
            ) from exc

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        self.load()
        return self._model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=32
        ).tolist()


def index_text_embeddings(
    connection: sqlite3.Connection, backend: TextEmbeddingBackend, batch_size: int = 32
) -> int:
    backend.load()
    rows = connection.execute(
        "SELECT id,text FROM chunks WHERE embedding_model IS NOT ? OR embedding_model<>? OR embedding_blob IS NULL ORDER BY id",
        (backend.model_id, backend.model_id),
    ).fetchall()
    indexed = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        vectors = backend.embed_documents([r["text"] for r in batch])
        if len(vectors) != len(batch) or not vectors:
            continue
        width = len(vectors[0])
        if any(len(vector) != width for vector in vectors):
            raise ValueError("Embedding backend returned inconsistent dimensions")
        blobs = [struct.pack(f"<{len(vector)}f", *vector) for vector in vectors]
        with connection:
            connection.executemany(
                "UPDATE chunks SET embedding_model=?,embedding_blob=? WHERE id=?",
                [
                    (backend.model_id, blob, row["id"])
                    for row, blob in zip(batch, blobs, strict=True)
                ],
            )
        indexed += len(batch)
    return indexed


def semantic_search(
    connection: sqlite3.Connection, query: str, backend: TextEmbeddingBackend, limit: int = 100
) -> list[SearchHit]:
    if not query.strip():
        return []
    backend.load()
    query_vector = backend.embed_queries([query])[0]
    q = tuple(float(value) for value in query_vector)
    rows = connection.execute(
        "SELECT c.id,c.text,c.embedding_blob,f.id file_id,f.path,f.kind,s.locator FROM chunks c JOIN files f ON f.id=c.file_id JOIN roots r ON r.id=f.root_id JOIN segments s ON s.id=c.segment_id WHERE f.status='ok' AND r.enabled=1 AND c.embedding_model=? AND c.embedding_blob IS NOT NULL",
        (backend.model_id,),
    ).fetchall()
    scored = []
    for row in rows:
        if len(row["embedding_blob"]) % 4:
            continue
        vector = struct.unpack(f"<{len(row['embedding_blob']) // 4}f", row["embedding_blob"])
        if len(vector) != len(q):
            continue
        score = sum(left * right for left, right in zip(q, vector, strict=True))
        scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], item[1]["path"].casefold(), item[1]["id"]))
    from pathlib import Path

    return [
        SearchHit(
            row["file_id"],
            Path(row["path"]),
            Path(row["path"]).name,
            row["kind"],
            row["text"],
            row["locator"],
            score,
            ("similar meaning",),
        )
        for score, row in scored[:limit]
    ]
