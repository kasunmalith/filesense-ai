# Contributing

Thanks for considering a contribution. Please keep changes focused, privacy-safe, and testable.

1. Use Python 3.12 x64 and create a virtual environment.
2. Install `python -m pip install -e ".[dev,spreadsheet,duplicates,chat]"`.
3. Set `QT_QPA_PLATFORM=offscreen` before running GUI tests.
4. Run `python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .`, and `python -m compileall -q src tests`.
5. Use synthetic fixture files only. Never commit private indexed files, databases, logs, or model weights.
6. Update docs when behavior or supported formats change.

For security issues, follow [SECURITY.md](SECURITY.md) and do not open a public issue containing private file contents.
