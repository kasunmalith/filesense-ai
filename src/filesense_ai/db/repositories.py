from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from filesense_ai.core.paths import normalized_path


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Repository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.db = connection

    def add_root(self, path: Path, excludes: list[str] | None = None) -> str:
        norm = normalized_path(path)
        row = self.db.execute("SELECT id FROM roots WHERE normalized_path=?", (norm,)).fetchone()
        if row:
            with self.db:
                self.db.execute("UPDATE roots SET enabled=1 WHERE id=?", (row["id"],))
            return row["id"]
        root_id = uuid4().hex
        with self.db:
            self.db.execute(
                "INSERT INTO roots(id,path,normalized_path,created_at,excluded_patterns) VALUES(?,?,?,?,?)",
                (root_id, str(path), norm, utc_now(), json.dumps(excludes or [])),
            )
        return root_id

    def roots(self) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM roots ORDER BY path COLLATE NOCASE"))

    def root(self, root_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM roots WHERE id=?", (root_id,)).fetchone()

    def file_count(self, root_id: str) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM files WHERE root_id=? AND status='ok'", (root_id,)
        ).fetchone()[0]

    def file_root_path(self, file_id: str) -> Path | None:
        row = self.db.execute(
            "SELECT r.path FROM files f JOIN roots r ON r.id=f.root_id WHERE f.id=?", (file_id,)
        ).fetchone()
        return Path(row["path"]) if row else None

    def preview_segments(self, file_id: str, limit: int = 120) -> list[sqlite3.Row]:
        return list(
            self.db.execute(
                "SELECT locator,text FROM segments WHERE file_id=? ORDER BY position LIMIT ?",
                (file_id, limit),
            )
        )

    def has_text_embeddings(self, model_id: str) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM chunks WHERE embedding_model=? AND embedding_blob IS NOT NULL LIMIT 1",
                (model_id,),
            ).fetchone()
            is not None
        )

    def has_image_embeddings(self, model_id: str) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM images WHERE clip_model=? AND clip_embedding_blob IS NOT NULL LIMIT 1",
                (model_id,),
            ).fetchone()
            is not None
        )

    def update_root_exclusions(self, patterns: list[str]) -> None:
        with self.db:
            self.db.execute(
                "UPDATE roots SET excluded_patterns=?",
                (json.dumps(patterns, ensure_ascii=False),),
            )

    def remove_root(self, root_id: str) -> None:
        with self.db:
            file_ids = [
                row[0]
                for row in self.db.execute("SELECT id FROM files WHERE root_id=?", (root_id,))
            ]
            for file_id in file_ids:
                self._remove_file(file_id)
            self.db.execute("DELETE FROM roots WHERE id=?", (root_id,))

    def set_root_enabled(self, root_id: str, enabled: bool) -> None:
        with self.db:
            self.db.execute("UPDATE roots SET enabled=? WHERE id=?", (int(enabled), root_id))

    def stats(self) -> dict[str, int]:
        row = self.db.execute(
            "SELECT COUNT(*) files, COALESCE(SUM(CASE WHEN kind='image' THEN 1 ELSE 0 END),0) images, COALESCE(SUM(CASE WHEN kind='document' THEN 1 ELSE 0 END),0) documents FROM files WHERE status='ok'"
        ).fetchone()
        return dict(row)

    def replace_file(
        self, values: dict, segments: list[tuple[str, int, str]], chunks: list[tuple[int, int, str]]
    ) -> None:
        with self.db:
            existing = self.db.execute(
                "SELECT id FROM files WHERE normalized_path=?", (values["normalized_path"],)
            ).fetchone()
            if existing and existing["id"] != values["id"]:
                self._remove_file(existing["id"])
            self._remove_file(values["id"])
            self.db.execute(
                "INSERT INTO files(id,root_id,path,normalized_path,size,mtime_ns,sha256,mime,kind,indexed_at,status,error,metadata_json) VALUES(:id,:root_id,:path,:normalized_path,:size,:mtime_ns,:sha256,:mime,:kind,:indexed_at,:status,:error,:metadata_json)",
                values,
            )
            if values["kind"] == "image":
                metadata = json.loads(values["metadata_json"])
                self.db.execute(
                    "INSERT INTO images(file_id,width,height) VALUES(?,?,?)",
                    (values["id"], metadata["width"], metadata["height"]),
                )
            for locator, position, text in segments:
                segment_id = self.db.execute(
                    "INSERT INTO segments(file_id,locator,position,text) VALUES(?,?,?,?)",
                    (values["id"], locator, position, text),
                ).lastrowid
                for ordinal, chunk_text in enumerate(c for sid, _, c in chunks if sid == position):
                    chunk_id = self.db.execute(
                        "INSERT INTO chunks(file_id,segment_id,ordinal,text) VALUES(?,?,?,?)",
                        (values["id"], segment_id, ordinal, chunk_text),
                    ).lastrowid
                    self.db.execute(
                        "INSERT INTO chunk_fts(chunk_id,file_id,filename,path,text) VALUES(?,?,?,?,?)",
                        (
                            chunk_id,
                            values["id"],
                            Path(values["path"]).name,
                            values["path"],
                            chunk_text,
                        ),
                    )

    def _remove_file(self, file_id: str) -> None:
        self.db.execute("DELETE FROM chunk_fts WHERE file_id=?", (file_id,))
        self.db.execute("DELETE FROM files WHERE id=?", (file_id,))

    def remove_file(self, file_id: str) -> None:
        with self.db:
            self._remove_file(file_id)

    def delete_stale(self, root_id: str, present_normalized_paths: set[str]) -> int:
        rows = list(
            self.db.execute("SELECT id,normalized_path FROM files WHERE root_id=?", (root_id,))
        )
        stale = [
            row["id"] for row in rows if row["normalized_path"] not in present_normalized_paths
        ]
        with self.db:
            for file_id in stale:
                self._remove_file(file_id)
        return len(stale)
