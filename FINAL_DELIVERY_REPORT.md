# FileSense AI — delivery report

## Delivered

FileSense AI is a Windows-first Python/PySide6 desktop app for local file search. The source, test suite, project docs, Windows CI/build workflows, synthetic demo-data script, and app screenshot are in this workspace. The local core executable is at `dist\FileSenseAI\FileSenseAI.exe`.

The app supports selected-folder incremental indexing, SQLite/FTS5 keyword search, PDF/DOCX/text/CSV and optional XLSX extraction, previews, local image browsing and filters, duplicate review, and configurable exclusions. Optional MiniLM semantic search, OpenCLIP image search, and Ollama chat are user-enabled features. Source files are not changed by indexing or duplicate review.

## Verification

- 28 tests passed.
- Ruff lint and format checks passed.
- `compileall` and source `--smoke` checks passed.
- PyInstaller produced the core onedir bundle on the Windows host.
- The bundled executable `--smoke` startup created an isolated SQLite database and settings file.

See [PROGRESS.md](PROGRESS.md), [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md), and [docs/TESTING.md](docs/TESTING.md) for stage and test records.

## Build and run

On Windows, see [README.md](README.md) for source setup. To build the AI-inclusive onedir package with Python 3.12 x64, run:

```powershell
scripts\build_windows.ps1
```

That script installs the optional model libraries before packaging. Model weights remain outside the app bundle and require explicit in-app setup. The committed workflow in `.github/workflows/build-windows.yml` creates an unsigned build artifact when run by GitHub Actions.

## Scope and follow-up

This workspace now contains a GitHub-ready project tree, but it has no GitHub remote and has not been published. The local executable is a core build because the large optional AI libraries and weights were not installed here. The AI-inclusive GitHub Actions workflow, real model downloads/inference, live Ollama, code signing, and public publishing remain unverified. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).
