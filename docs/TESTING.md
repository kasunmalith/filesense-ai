# Testing and verification

## Environment

The supported CI and primary build target is Windows x64 with Python 3.12. The authoring host was Windows 11 with Python 3.13.14. Tests use generated local fixture files; regular tests do not download model weights or require a live Ollama service.

## Reproduce source checks

```powershell
python -m pip install -e "[dev,spreadsheet,duplicates,chat]"
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src tests
python -m filesense_ai --smoke
```

The test suite covers settings/path validation, SQLite and FTS5, incremental and cancelled scans, extraction limits and malformed inputs, semantic ranking with fake embeddings, search and preview UI flow, image metadata/thumbnail and fake CLIP behavior, duplicate suggestions, and local Ollama HTTP/citation behavior.

## Recorded result

On 2026-11-20:

- `python -m pytest -q` — **28 passed in 4.64s**.
- `python -m ruff check .` — passed.
- `python -m ruff format --check .` — passed (56 files).
- `python -m compileall -q src tests` — passed.
- `python -m filesense_ai --smoke` — passed.
- Core `FileSenseAI.spec` PyInstaller onedir build — passed on the Windows host.
- Bundled executable `--smoke` — initialized its SQLite database and settings directory successfully.

## Not covered by this run

Optional model download and real inference, live Ollama/model behavior, a full human-driven interactive EXE session, the AI-inclusive GitHub Actions build, code signing, and publication were not run. Model-dependent tests must use already-cached weights and should be marked `slow`; keep network-dependent model tests out of regular CI.
