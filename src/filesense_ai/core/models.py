from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any


@dataclass(frozen=True)
class IndexedRoot:
    id: str
    path: Path
    enabled: bool = True


@dataclass(frozen=True)
class ExtractedSegment:
    locator: str
    position: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    segment_id: int
    ordinal: int
    text: str


@dataclass(frozen=True)
class IndexEvent:
    kind: str
    path: str = ""
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    errors: int = 0
    message: str = ""


@dataclass
class CancellationToken:
    _event: Event = field(default_factory=Event)

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class SearchHit:
    file_id: str
    path: Path
    filename: str
    kind: str
    snippet: str
    locator: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ImageRecord:
    file_id: str
    path: Path
    width: int
    height: int
    size: int
    mtime_ns: int
    phash: str | None = None
    thumbnail: Path | None = None


@dataclass(frozen=True)
class DuplicateGroup:
    kind: str
    files: tuple[dict[str, Any], ...]
    distance: int | None = None


@dataclass
class AppSettings:
    theme: str = "dark"
    max_file_size_mb: int = 50
    max_document_chars: int = 2_000_000
    max_indexed_files: int = 100_000
    enabled_text_model: bool = False
    enabled_image_model: bool = False
    ollama_model: str = ""
    model_cache_path: str = ""
    start_page: str = "Overview"
    excluded_patterns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModelState:
    model_id: str
    installed: bool
    loaded: bool
    status: str
