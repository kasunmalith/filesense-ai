# FileSense AI development progress

All 10 numbered development prompts and `START_HERE_FOR_CODEX.txt` were read in order before implementation. The completed implementation below follows those stage boundaries. Private prompt files are intentionally excluded from Git.

## Stage 01 — Foundation and desktop shell

Completed the installable Python package, configuration, local app-data handling, logging, and native PySide6 window with six pages. Added the required Energetic Edge credit link at the bottom of the application sidebar. Source and bundled startup smoke checks pass.

## Stage 02 — Discovery, extraction, and local index

Completed selected-root recursive discovery, symlink and size limits, supported text extraction, SQLite/FTS5 schema, incremental scan state, cancellation, and per-file error handling. Tests cover generated PDF, DOCX, TXT, CSV, and XLSX fixtures, malformed inputs, and scan behavior.

## Stage 03 — Optional semantic retrieval

Added user-triggered MiniLM setup, local embedding persistence, semantic search, and reciprocal-rank hybrid retrieval. Tests use deterministic fake embeddings. Downloading weights and real model inference were not part of this run.

## Stage 04 — Search workflow

Connected background indexing and search workers to the interface. Added type/root filters, result previews, highlighting, and open, reveal, and copy-path actions. The generated-data UI indexing/search/preview integration test passes.

## Stage 05 — Image browsing and CLIP

Added local image metadata, orientation-aware safe thumbnails, filename search, root/type/date/dimension filters, pagination, and opt-in OpenCLIP indexing/search. Catalog and fake-vector behavior are tested. Real CLIP weights and inference remain unverified.

## Stage 06 — Duplicate review

Added exact SHA-256 duplicate groups and perceptual-hash image suggestions with CSV metadata export. The app explains the review-only behavior; it does not delete or move source files. Service tests pass.

## Stage 07 — Settings and usability

Added light/dark themes, scan limits, exclusions, model cache selection, shortcut handling, accessible names, persisted page/window preferences, and model-state messaging. Settings and UI construction tests pass.

## Stage 08 — Grounded local chat

Added local retrieval, source citation validation, optional local embeddings, and streamed Ollama responses restricted to a literal loopback endpoint. Tests use a local mock HTTP service and verify remote endpoints are rejected. No live Ollama model was used.

## Stage 09 — Safety and regression pass

Added documentation and regression coverage for protected app-data paths, bounded extraction and previews, corrupt inputs, image limits, cancellation, local-only processing, and prompt injection boundaries. Fixed issues found during regression runs and reviewed synthetic performance behavior.

## Stage 10 — Portfolio and Windows packaging

Completed README, architecture/decisions/limitations/testing/security/licensing docs, issue templates, Windows CI and build workflows, PyInstaller spec, bootstrap/build scripts, changelog, screenshot, and portfolio summary. Built a core onedir executable and smoke-launched it. The optional AI-inclusive workflow and public repository setup were not run.

## Final verification (2026-11-20)

- Pytest: **28 passed**.
- Ruff lint: passed.
- Ruff format check: passed, 54 files.
- Python compile check: passed.
- Source startup smoke: passed.
- Core PyInstaller onedir build: passed; see `dist\FileSenseAI\FileSenseAI.exe`.
- Bundled executable startup smoke: passed and created its local DB/settings.

See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) and [docs/TESTING.md](docs/TESTING.md) for environment details and limits.
