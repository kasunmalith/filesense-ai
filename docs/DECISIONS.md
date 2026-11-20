# Engineering decisions

## Supported runtime

Python 3.12 x64 is the documented primary runtime for Windows 10/11. Package metadata permits Python 3.13 to support local verification on the available host. No Python 3.12 interpreter was present in the authoring environment; CI targets 3.12.

## Dependencies and optional features

PySide6, pypdf, python-docx, Pillow, and charset-normalizer are base dependencies. XLSX uses the `spreadsheet` extra. MiniLM text embeddings and OpenCLIP are separate opt-in extras so keyword search and startup do not load Torch. Model downloads happen only after user action. No PyMuPDF dependency is used. SQLite/FTS5 is built into Python's standard library.

## Search and vector storage

FTS5 query terms are quoted and joined with AND. Hybrid search combines independent keyword and semantic rankings using Reciprocal Rank Fusion (k=60); raw scores from unrelated models are never mixed. Vectors are SQLite float32 blobs with a model ID and dimension checks. Search performs a bounded top-K local cosine scan. FAISS was not selected because a compatible Windows wheel was not verified in this environment; NumPy is part of the semantic extra, and a pure-Python scan preserves deterministic fallback behavior.

## Image similarity and CLIP

CLIP image and text vectors use the same ViT-B-32 checkpoint and normalized embedding space. Text MiniLM vectors are never compared with CLIP vectors. Similar image candidates use a BK-tree over 64-bit perceptual hashes with a Hamming threshold of 8. Grouping is a review aid, not proof of identical content.

## Privacy and cleanup

The app does not upload user files, run macros, or delete original files. Ollama requests are restricted to HTTP loopback. Duplicate cleanup controls are omitted. Removing a root or clearing the index deletes only local index rows and app-owned thumbnail cache entries.

## Packaging

PyInstaller onedir is the release shape. Optional Torch packages may make the build large. User databases, model weights, logs, and thumbnails remain in per-user app data. No models are embedded.
