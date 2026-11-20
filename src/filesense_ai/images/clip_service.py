from __future__ import annotations

import struct
from pathlib import Path
from typing import Protocol

from filesense_ai.core.errors import ModelUnavailableError, OptionalDependencyError


class ClipBackend(Protocol):
    model_id: str

    def load(self) -> None: ...
    def embed_images(self, paths: list[Path]) -> list[list[float]]: ...
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class OpenClipBackend:
    model_id = "ViT-B-32/laion2b_s34b_b79k"

    def __init__(self, cache_dir: str | None = None) -> None:
        self.cache_dir, self.model, self.preprocess, self.tokenizer, self.torch = (
            cache_dir,
            None,
            None,
            None,
            None,
        )

    def load(self) -> None:
        if self.model is not None:
            return
        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise OptionalDependencyError(
                "Install the image-ai extra to enable CLIP image search"
            ) from exc
        try:
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                "ViT-B-32", pretrained="laion2b_s34b_b79k", cache_dir=self.cache_dir, device="cpu"
            )
            self.tokenizer = open_clip.get_tokenizer("ViT-B-32")
            self.torch = torch
            self.model.eval()
        except Exception as exc:
            raise ModelUnavailableError(
                "The CLIP weights are not cached. Use Settings to obtain them explicitly."
            ) from exc

    def embed_images(self, paths: list[Path]) -> list[list[float]]:
        from PIL import Image, ImageOps

        self.load()
        vectors = []
        with self.torch.no_grad():
            for path in paths:
                with Image.open(path) as source:
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    tensor = self.preprocess(image).unsqueeze(0)
                vector = self.model.encode_image(tensor)
                vector /= vector.norm(dim=-1, keepdim=True)
                vectors.append(vector.cpu().float().numpy()[0].tolist())
        return vectors

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.load()
        with self.torch.no_grad():
            tokens = self.tokenizer(texts)
            vectors = self.model.encode_text(tokens)
            vectors /= vectors.norm(dim=-1, keepdim=True)
            return vectors.cpu().float().numpy().tolist()


def index_clip_images(
    connection, backend: ClipBackend, paths: list[tuple[str, Path]], batch_size: int = 16
) -> int:
    backend.load()
    count = 0
    for start in range(0, len(paths), batch_size):
        batch = paths[start : start + batch_size]
        vectors = backend.embed_images([path for _, path in batch])
        with connection:
            connection.executemany(
                "UPDATE images SET clip_model=?,clip_embedding_blob=? WHERE file_id=?",
                [
                    (backend.model_id, struct.pack(f"<{len(vector)}f", *vector), file_id)
                    for (file_id, _), vector in zip(batch, vectors, strict=True)
                ],
            )
        count += len(batch)
    return count


def search_clip_images(
    connection, query: str, backend: ClipBackend, limit: int = 100
) -> list[tuple[str, float]]:
    backend.load()
    q = tuple(float(value) for value in backend.embed_texts([query])[0])
    rows = connection.execute(
        "SELECT file_id,clip_embedding_blob FROM images WHERE clip_model=? AND clip_embedding_blob IS NOT NULL",
        (backend.model_id,),
    ).fetchall()
    scored = []
    for row in rows:
        blob = row["clip_embedding_blob"]
        if len(blob) % 4:
            continue
        vector = struct.unpack(f"<{len(blob) // 4}f", blob)
        if len(vector) == len(q):
            score = sum(left * right for left, right in zip(q, vector, strict=True))
            scored.append((row["file_id"], score))
    return sorted(scored, key=lambda pair: (-pair[1], pair[0]))[:limit]
