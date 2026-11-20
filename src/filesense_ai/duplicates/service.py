from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from pathlib import Path

from filesense_ai.core.models import DuplicateGroup

_DCT_BASIS = [
    [math.cos(math.pi * frequency * (2 * position + 1) / 64) for position in range(32)]
    for frequency in range(8)
]


def hamming(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


class _BKNode:
    def __init__(self, value: str, file_id: str) -> None:
        self.value, self.ids, self.children = value, [file_id], {}

    def add(self, value: str, file_id: str) -> None:
        distance = hamming(self.value, value)
        if distance == 0:
            self.ids.append(file_id)
        elif distance in self.children:
            self.children[distance].add(value, file_id)
        else:
            self.children[distance] = _BKNode(value, file_id)

    def search(self, value: str, radius: int, found: list[tuple[str, str, int]]) -> None:
        distance = hamming(self.value, value)
        if distance <= radius:
            found.extend((file_id, value, distance) for file_id in self.ids)
        for edge, child in self.children.items():
            if distance - radius <= edge <= distance + radius:
                child.search(value, radius, found)


class DuplicateService:
    def __init__(self, connection: sqlite3.Connection, phash_threshold: int = 8) -> None:
        self.db, self.threshold = connection, phash_threshold

    def exact_groups(self) -> list[DuplicateGroup]:
        rows = self.db.execute(
            "SELECT sha256,COUNT(*) n FROM files WHERE status='ok' AND sha256 IS NOT NULL GROUP BY sha256 HAVING COUNT(*)>1 ORDER BY sha256"
        ).fetchall()
        groups = []
        for row in rows:
            files = self.db.execute(
                "SELECT id,path,size,mtime_ns FROM files WHERE sha256=? ORDER BY path COLLATE NOCASE",
                (row["sha256"],),
            ).fetchall()
            groups.append(DuplicateGroup("exact", tuple(dict(item) for item in files)))
        return groups

    def similar_images(self) -> list[DuplicateGroup]:
        rows = self.db.execute(
            "SELECT i.file_id,i.phash,f.path,f.size,f.mtime_ns FROM images i JOIN files f ON f.id=i.file_id WHERE i.phash IS NOT NULL AND f.status='ok' ORDER BY i.file_id"
        ).fetchall()
        if len(rows) < 2:
            return []
        node = _BKNode(rows[0]["phash"], rows[0]["file_id"])
        by_id = {row["file_id"]: dict(row) for row in rows}
        edges: set[tuple[str, str, int]] = set()
        for row in rows[1:]:
            matches: list[tuple[str, str, int]] = []
            node.search(row["phash"], self.threshold, matches)
            for previous_id, _, distance in matches:
                edges.add(
                    (min(previous_id, row["file_id"]), max(previous_id, row["file_id"]), distance)
                )
            node.add(row["phash"], row["file_id"])
        parent = {file_id: file_id for pair in edges for file_id in pair[:2]}

        def find(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        for left, right, _ in sorted(edges):
            parent[find(right)] = find(left)
        clusters: dict[str, set[str]] = defaultdict(set)
        for file_id in parent:
            clusters[find(file_id)].add(file_id)
        result = []
        for ids in clusters.values():
            if len(ids) > 1:
                distance = min(d for a, b, d in edges if a in ids and b in ids)
                result.append(
                    DuplicateGroup("similar-image", tuple(by_id[i] for i in sorted(ids)), distance)
                )
        return sorted(
            result, key=lambda group: tuple(item["path"].casefold() for item in group.files)
        )

    def set_phash(self, file_id: str, path: Path) -> str:
        try:
            import imagehash
            from PIL import Image, ImageOps

            with Image.open(path) as image:
                value = str(imagehash.phash(ImageOps.exif_transpose(image).convert("RGB")))
        except ImportError:
            from PIL import Image, ImageOps

            with Image.open(path) as image:
                gray = ImageOps.exif_transpose(image).convert("L").resize((32, 32))
                pixels = list(gray.getdata())
            coefficients = []
            for v in range(8):
                for u in range(8):
                    coefficient = sum(
                        pixels[y * 32 + x] * _DCT_BASIS[u][x] * _DCT_BASIS[v][y]
                        for y in range(32)
                        for x in range(32)
                    )
                    coefficients.append(coefficient)
            median = sorted(coefficients[1:])[len(coefficients[1:]) // 2]
            bits = [coefficient > median for coefficient in coefficients]
            value = f"{sum(int(bit) << (63 - i) for i, bit in enumerate(bits)):016x}"
        with self.db:
            self.db.execute("UPDATE images SET phash=? WHERE file_id=?", (value, file_id))
        return value
