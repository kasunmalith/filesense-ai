from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from filesense_ai.core.models import ImageRecord
from filesense_ai.core.paths import data_directory


class ImageCatalog:
    def __init__(self, connection: sqlite3.Connection, cache: Path | None = None) -> None:
        self.db = connection
        database_path = connection.execute("PRAGMA database_list").fetchone()[2]
        default_cache = (
            Path(database_path).parent / "thumbnails"
            if database_path
            else data_directory() / "thumbnails"
        )
        self.cache = cache or default_cache
        self.cache.mkdir(parents=True, exist_ok=True)

    def records(
        self,
        query: str = "",
        root_ids: list[str] | None = None,
        extension: str | None = None,
        modified_after_ns: int | None = None,
        min_width: int = 0,
        min_height: int = 0,
        limit: int = 120,
        offset: int = 0,
    ) -> list[ImageRecord]:
        sql = "SELECT f.id,f.path,f.size,f.mtime_ns,i.width,i.height,i.phash FROM files f JOIN images i ON i.file_id=f.id JOIN roots r ON r.id=f.root_id WHERE f.status='ok' AND r.enabled=1"
        params: list[object] = []
        if query:
            sql += " AND f.path LIKE ? ESCAPE '\\'"
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        if root_ids:
            sql += f" AND f.root_id IN ({','.join('?' for _ in root_ids)})"
            params.extend(root_ids)
        if extension:
            sql += " AND lower(f.path) LIKE ?"
            params.append(f"%{extension.lower()}")
        if modified_after_ns is not None:
            sql += " AND f.mtime_ns>=?"
            params.append(modified_after_ns)
        if min_width:
            sql += " AND i.width>=?"
            params.append(min_width)
        if min_height:
            sql += " AND i.height>=?"
            params.append(min_height)
        sql += " ORDER BY f.path COLLATE NOCASE LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.db.execute(sql, params).fetchall()
        return [
            ImageRecord(
                row["id"],
                Path(row["path"]),
                row["width"],
                row["height"],
                row["size"],
                row["mtime_ns"],
                row["phash"],
                self.thumbnail_path(row["id"], row["mtime_ns"]),
            )
            for row in rows
        ]

    def thumbnail_path(self, file_id: str, mtime_ns: int) -> Path:
        key = hashlib.sha256(f"{file_id}:{mtime_ns}".encode()).hexdigest()
        return self.cache / f"{key}.jpg"

    def create_thumbnail(self, record: ImageRecord, size: tuple[int, int] = (320, 240)) -> Path:
        target = self.thumbnail_path(record.file_id, record.mtime_ns)
        if target.exists():
            try:
                from PIL import Image

                with Image.open(target) as cached:
                    cached.verify()
                return target
            except OSError:
                target.unlink(missing_ok=True)
        from PIL import Image, ImageOps

        with Image.open(record.path) as im:
            if im.width * im.height > 50_000_000:
                raise ValueError("Image exceeds safe preview dimensions")
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail(size)
            im.save(target, "JPEG", quality=82, optimize=True)
        with self.db:
            self.db.execute(
                "UPDATE images SET thumbnail_key=? WHERE file_id=?", (target.name, record.file_id)
            )
        return target

    def prune_orphans(self) -> int:
        valid = {
            self.thumbnail_path(row["id"], row["mtime_ns"]).name
            for row in self.db.execute(
                "SELECT id,mtime_ns FROM files WHERE kind='image' AND status='ok'"
            )
        }
        removed = 0
        for path in self.cache.glob("*.jpg"):
            if path.name not in valid:
                path.unlink(missing_ok=True)
                removed += 1
        return removed
