from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from filesense_ai.core.models import CancellationToken, IndexEvent
from filesense_ai.db.connection import Database


class IndexWorker(QThread):
    progress = Signal(object)
    result = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        db_path: Path,
        root_id: str,
        max_file_size: int,
        max_chars: int,
        max_files: int,
        semantic_enabled: bool = False,
        model_cache: Path | None = None,
    ) -> None:
        super().__init__()
        self.db_path, self.root_id = db_path, root_id
        self.max_file_size, self.max_chars, self.max_files = max_file_size, max_chars, max_files
        self.semantic_enabled = semantic_enabled
        self.model_cache = model_cache or db_path.parent / "models"
        self.token = CancellationToken()

    def run(self) -> None:
        database = None
        try:
            from filesense_ai.indexing.service import IndexingService

            database = Database(self.db_path)
            value = IndexingService(
                database.connection,
                self.max_file_size,
                self.max_chars,
                self.max_files,
                protected_paths={self.db_path.parent},
            ).index_root(self.root_id, self.token, self.progress.emit)
            if self.semantic_enabled and value["status"] == "complete":
                try:
                    from filesense_ai.search.semantic import (
                        SentenceTransformerBackend,
                        index_text_embeddings,
                    )

                    backend = SentenceTransformerBackend(
                        str(self.model_cache), local_files_only=True
                    )
                    backend.load()
                    value["semantic_indexed"] = index_text_embeddings(database.connection, backend)
                except Exception as exc:
                    self.progress.emit(
                        IndexEvent(
                            "semantic",
                            message=f"Text vectors were not refreshed; keyword indexing completed ({type(exc).__name__}).",
                        )
                    )
            self.result.emit(value)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if database:
                database.close()


class SearchWorker(QThread):
    result = Signal(int, object)
    failed = Signal(int, str)

    def __init__(
        self,
        db_path: Path,
        generation: int,
        query: str,
        mode: str,
        kind: str | None,
        root_ids: list[str],
        semantic: bool,
        model_cache: Path,
    ) -> None:
        super().__init__()
        self.db_path, self.generation, self.query, self.mode = db_path, generation, query, mode
        self.kind, self.root_ids, self.semantic, self.model_cache = (
            kind,
            root_ids,
            semantic,
            model_cache,
        )

    def run(self) -> None:
        database = None
        try:
            from filesense_ai.search.hybrid import hybrid_search
            from filesense_ai.search.keyword import keyword_search

            database = Database(self.db_path)
            backend = None
            if self.mode != "Keyword" and self.semantic:
                from filesense_ai.search.semantic import SentenceTransformerBackend

                backend = SentenceTransformerBackend(str(self.model_cache), local_files_only=True)
            if self.mode == "Keyword" or backend is None:
                hits = keyword_search(
                    database.connection, self.query, kind=self.kind, root_ids=self.root_ids or None
                )
            elif self.mode == "Semantic":
                from filesense_ai.search.semantic import semantic_search

                hits = semantic_search(database.connection, self.query, backend)
                if self.kind:
                    hits = (
                        [hit for hit in hits if hit.path.suffix.lower() == self.kind[4:].lower()]
                        if self.kind.startswith("ext:")
                        else [hit for hit in hits if hit.kind == self.kind]
                    )
                if self.root_ids:
                    hits = [
                        hit
                        for hit in hits
                        if database.connection.execute(
                            "SELECT root_id FROM files WHERE id=?", (hit.file_id,)
                        ).fetchone()[0]
                        in self.root_ids
                    ]
            else:
                hits = hybrid_search(
                    database.connection,
                    self.query,
                    backend,
                    kind=self.kind,
                    root_ids=self.root_ids or None,
                )
            self.result.emit(self.generation, hits)
        except Exception as exc:
            self.failed.emit(self.generation, str(exc))
        finally:
            if database:
                database.close()


class ImageWorker(QThread):
    result = Signal(int, object, bool)
    failed = Signal(str)

    def __init__(
        self,
        db_path: Path,
        query: str = "",
        clip: bool = False,
        model_cache: Path | None = None,
        root_ids: list[str] | None = None,
        extension: str | None = None,
        modified_after_ns: int | None = None,
        min_width: int = 0,
        min_height: int = 0,
        offset: int = 0,
    ) -> None:
        super().__init__()
        self.db_path, self.query, self.clip, self.model_cache = db_path, query, clip, model_cache
        self.root_ids = root_ids
        self.extension, self.modified_after_ns = extension, modified_after_ns
        self.min_width, self.min_height, self.offset = min_width, min_height, offset

    def run(self) -> None:
        database = None
        try:
            from filesense_ai.images.catalog import ImageCatalog

            database = Database(self.db_path)
            catalog = ImageCatalog(database.connection)
            filters = {
                "root_ids": self.root_ids,
                "extension": self.extension,
                "modified_after_ns": self.modified_after_ns,
                "min_width": self.min_width,
                "min_height": self.min_height,
            }
            if self.clip and self.query:
                from filesense_ai.images.clip_service import OpenClipBackend, search_clip_images

                backend = OpenClipBackend(str(self.model_cache))
                scores = dict(
                    search_clip_images(database.connection, self.query, backend, limit=100_000)
                )
                records = catalog.records(**filters, limit=100_000)
                by_id = {item.file_id: item for item in records}
                records = [by_id[file_id] for file_id in scores if file_id in by_id]
                records.sort(key=lambda item: -scores[item.file_id])
                has_more = len(records) > self.offset + 120
                records = records[self.offset : self.offset + 120]
            else:
                records = catalog.records(
                    query=self.query,
                    **filters,
                    limit=121,
                    offset=self.offset,
                )
                has_more = len(records) > 120
                records = records[:120]
            result = []
            for record in records:
                try:
                    thumbnail = catalog.create_thumbnail(record)
                    result.append((record, thumbnail))
                except Exception:
                    continue
            self.result.emit(self.offset, result, has_more)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if database:
                database.close()


class DuplicateWorker(QThread):
    result = Signal(object, object)
    failed = Signal(str)

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self.db_path = db_path

    def run(self) -> None:
        database = None
        try:
            from filesense_ai.duplicates.service import DuplicateService

            database = Database(self.db_path)
            service = DuplicateService(database.connection)
            self.result.emit(service.exact_groups(), service.similar_images())
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if database:
                database.close()


class ModelWorker(QThread):
    result = Signal(str)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, db_path: Path, kind: str, model_cache: Path) -> None:
        super().__init__()
        self.db_path, self.kind, self.model_cache = db_path, kind, model_cache

    def run(self) -> None:
        database = None
        try:
            self.progress.emit("Downloading or loading the model…")
            self.model_cache.mkdir(parents=True, exist_ok=True)
            if self.kind == "text":
                from huggingface_hub import snapshot_download

                from filesense_ai.search.semantic import (
                    SentenceTransformerBackend,
                    index_text_embeddings,
                )

                self.progress.emit("Downloading sentence-transformers/all-MiniLM-L6-v2…")
                snapshot_download(
                    "sentence-transformers/all-MiniLM-L6-v2", cache_dir=str(self.model_cache)
                )
                backend = SentenceTransformerBackend(str(self.model_cache), local_files_only=True)
                backend.load()
                database = Database(self.db_path)
                count = index_text_embeddings(database.connection, backend)
                self.result.emit(f"Text model ready. Indexed {count} text chunks.")
            elif self.kind == "image":
                import os

                os.environ["TORCH_HOME"] = str(self.model_cache)
                from filesense_ai.images.clip_service import OpenClipBackend, index_clip_images

                backend = OpenClipBackend(str(self.model_cache))
                backend.load()
                database = Database(self.db_path)
                rows = database.connection.execute(
                    "SELECT f.id,f.path FROM files f JOIN images i ON i.file_id=f.id WHERE f.status='ok' ORDER BY f.id"
                ).fetchall()
                count = index_clip_images(
                    database.connection, backend, [(row["id"], Path(row["path"])) for row in rows]
                )
                self.result.emit(f"CLIP image search ready. Indexed {count} images.")
            else:
                self.result.emit("No model selected.")
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if database:
                database.close()


class ChatWorker(QThread):
    token = Signal(str)
    result = Signal(object, object, object)
    failed = Signal(str)

    def __init__(
        self,
        db_path: Path,
        model: str,
        question: str,
        root_ids: list[str] | None = None,
        semantic_enabled: bool = False,
        model_cache: Path | None = None,
    ) -> None:
        super().__init__()
        self.db_path, self.model, self.question, self.root_ids = (
            db_path,
            model,
            question,
            root_ids or None,
        )
        self.cancelled = False
        self.semantic_enabled = semantic_enabled
        self.model_cache = model_cache or db_path.parent / "models"

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        database = None
        try:
            from filesense_ai.chat.ollama_client import OllamaClient
            from filesense_ai.chat.retrieval import build_prompt, valid_citations

            database = Database(self.db_path)
            backend = None
            if self.semantic_enabled:
                try:
                    from filesense_ai.search.semantic import SentenceTransformerBackend

                    backend = SentenceTransformerBackend(
                        str(self.model_cache), local_files_only=True
                    )
                    backend.load()
                except Exception:
                    backend = None
            prompt = build_prompt(
                database.connection,
                self.question,
                root_ids=self.root_ids,
                embedding_backend=backend,
            )
            if not prompt.citations:
                self.result.emit("I could not find that in the selected files.", [], [])
                return
            client = OllamaClient()
            pieces = []
            for piece in client.stream_chat(self.model, prompt.system, prompt.user):
                if self.cancelled:
                    break
                pieces.append(piece)
                self.token.emit(piece)
            response, citations, invalid = valid_citations("".join(pieces), prompt.citations)
            for source_id in invalid:
                response = response.replace(f"[{source_id}]", "[unverified citation removed]")
            self.result.emit(response, citations, invalid)
        except Exception as exc:
            self.failed.emit(f"Could not reach local Ollama: {exc}")
        finally:
            if database:
                database.close()
