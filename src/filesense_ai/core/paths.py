from __future__ import annotations

import os
from pathlib import Path


def data_directory(app_data_location: str | Path | None = None) -> Path:
    """Return an app-owned data directory, with an override for portable use/tests."""
    override = os.environ.get("FILESENSE_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif app_data_location:
        path = Path(app_data_location)
    elif os.name == "nt":
        path = (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            / "EnergeticEdge"
            / "FileSenseAI"
        )
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "filesense-ai"
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalized_path(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path))).casefold()
