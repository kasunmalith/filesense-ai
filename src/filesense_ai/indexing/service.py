from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import sqlite3
import uuid
from collections.abc import Callable
from pathlib import Path

from filesense_ai.core.models import CancellationToken, IndexEvent
from filesense_ai.core.paths import normalized_path
from filesense_ai.db.repositories import Repository, utc_now
from filesense_ai.indexing.discovery import DEFAULT_EXCLUDES, discover
from filesense_ai.indexing.extractors import extract

logger = logging.getLogger("filesense_ai.indexing")


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    clean = " ".join(text.split())
    if not clean:
        return []
    result, start = [], 0
    while start < len(clean):
        end = min(len(clean), start + size)
        if end < len(clean):
            split = clean.rfind(" ", start + size // 2, end)
            if split > start:
                end = split
        result.append(clean[start:end].strip())
        if end >= len(clean):
            break
        start = max(start + 1, end - overlap)
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class IndexingService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        max_file_size: int = 50 * 1024 * 1024,
        max_chars: int = 2_000_000,
        max_files: int = 100_000,
        protected_paths: set[Path] | None = None,
    ) -> None:
        self.db, self.repo = connection, Repository(connection)
        self.max_file_size, self.max_chars, self.max_files = max_file_size, max_chars, max_files
        self.protected_paths = protected_paths or set()

    def index_root(
        self,
        root_id: str,
        token: CancellationToken | None = None,
        emit: Callable[[IndexEvent], None] | None = None,
    ) -> dict[str, int | str]:
        token = token or CancellationToken()
        emit = emit or (lambda _: None)
        root_row = self.db.execute(
            "SELECT * FROM roots WHERE id=? AND enabled=1", (root_id,)
        ).fetchone()
        if not root_row:
            raise ValueError("Selected folder is unavailable or disabled")
        root = Path(root_row["path"])
        if not root.is_dir():
            raise ValueError("Selected folder is unavailable")
        excludes = set(DEFAULT_EXCLUDES) | set(json.loads(root_row["excluded_patterns"] or "[]"))
        scan = discover(root, self.max_file_size, excludes, self.protected_paths)
        if len(scan.files) > self.max_files:
            scan.files = scan.files[: self.max_files]
            scan.complete = False
            scan.errors += 1
        run_id = uuid.uuid4().hex
        started = utc_now()
        with self.db:
            self.db.execute(
                "INSERT INTO indexing_runs(id,root_id,started_at,status) VALUES(?,?,?,'running')",
                (run_id, root_id, started),
            )
        stats = {"scanned": 0, "indexed": 0, "skipped": 0, "errors": scan.errors}
        present: set[str] = set()
        cancelled = False
        for item in scan.files:
            if token.cancelled:
                cancelled = True
                break
            stats["scanned"] += 1
            norm = normalized_path(item.path)
            present.add(norm)
            existing = self.db.execute(
                "SELECT id,size,mtime_ns,status FROM files WHERE normalized_path=?", (norm,)
            ).fetchone()
            if (
                existing
                and existing["size"] == item.size
                and existing["mtime_ns"] == item.mtime_ns
                and existing["status"] == "ok"
            ):
                stats["skipped"] += 1
                emit(IndexEvent("progress", str(item.path), **stats))
                continue
            try:
                before = item.path.stat()
                if (
                    before.st_size != item.size
                    or before.st_mtime_ns != item.mtime_ns
                    or before.st_size > self.max_file_size
                ):
                    raise OSError(
                        "File changed or exceeded the configured size limit; retry on the next scan"
                    )
                file_hash = sha256(item.path)
                extracted = extract(item.path, self.max_chars)
                after = item.path.stat()
                if (
                    before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                    or after.st_size != item.size
                    or after.st_mtime_ns != item.mtime_ns
                ):
                    raise OSError("File changed while indexing; retry on the next scan")
                file_id = hashlib.sha256(norm.encode("utf-8", errors="surrogatepass")).hexdigest()
                chunks = [
                    (segment.position, idx, text)
                    for segment in extracted.segments
                    for idx, text in enumerate(chunk_text(segment.text))
                ]
                values = {
                    "id": file_id,
                    "root_id": root_id,
                    "path": str(item.path),
                    "normalized_path": norm,
                    "size": item.size,
                    "mtime_ns": item.mtime_ns,
                    "sha256": file_hash,
                    "mime": extracted.mime
                    or mimetypes.guess_type(item.path)[0]
                    or "application/octet-stream",
                    "kind": extracted.kind,
                    "indexed_at": utc_now(),
                    "status": "ok",
                    "error": None,
                    "metadata_json": json.dumps(extracted.metadata, ensure_ascii=False),
                }
                segments = [(s.locator, s.position, s.text) for s in extracted.segments]
                self.repo.replace_file(values, segments, chunks)
                if extracted.kind == "image":
                    from filesense_ai.duplicates.service import DuplicateService

                    DuplicateService(self.db).set_phash(file_id, item.path)
                stats["indexed"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.warning(
                    "Indexing failed for file id %s (%s)",
                    hashlib.sha256(norm.encode()).hexdigest()[:12],
                    type(exc).__name__,
                )
                if existing:
                    with self.db:
                        self.db.execute(
                            "UPDATE files SET status='error',error=?,indexed_at=? WHERE id=?",
                            (str(exc)[:300], utc_now(), existing["id"]),
                        )
            emit(IndexEvent("progress", str(item.path), **stats))
        if scan.complete and not cancelled:
            self.repo.delete_stale(root_id, present)
            from filesense_ai.images.catalog import ImageCatalog

            ImageCatalog(self.db).prune_orphans()
        status = "cancelled" if cancelled else "complete" if scan.complete else "partial"
        with self.db:
            self.db.execute(
                "UPDATE indexing_runs SET completed_at=?,status=?,scanned=?,indexed=?,skipped=?,errors=? WHERE id=?",
                (
                    utc_now(),
                    status,
                    stats["scanned"],
                    stats["indexed"],
                    stats["skipped"],
                    stats["errors"],
                    run_id,
                ),
            )
        emit(
            IndexEvent(
                status,
                scanned=stats["scanned"],
                indexed=stats["indexed"],
                skipped=stats["skipped"],
                errors=stats["errors"],
            )
        )
        return {**stats, "status": status}
