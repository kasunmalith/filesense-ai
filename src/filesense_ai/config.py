from __future__ import annotations

import json
import logging
import logging.handlers
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from filesense_ai.core.models import AppSettings
from filesense_ai.core.paths import data_directory


def setup_logging(data_dir: Path) -> None:
    logger = logging.getLogger("filesense_ai")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        data_dir / "logs" / "filesense.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_directory() / "settings.json"

    def load(self) -> AppSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            data.pop("schema_version", None)
            allowed = {
                key: value for key, value in data.items() if key in AppSettings.__dataclass_fields__
            }
            settings = AppSettings(**allowed)
        except (OSError, ValueError, TypeError, AttributeError):
            return AppSettings()
        settings.theme = (
            settings.theme
            if isinstance(settings.theme, str) and settings.theme in {"dark", "light"}
            else "dark"
        )
        settings.max_file_size_mb = _bounded_int(settings.max_file_size_mb, 50, 1, 2048)
        settings.max_document_chars = _bounded_int(
            settings.max_document_chars, 2_000_000, 1000, 10_000_000
        )
        settings.max_indexed_files = _bounded_int(settings.max_indexed_files, 100_000, 1, 1_000_000)
        pages = {"Overview", "Search", "Images", "Duplicates", "Ask Files", "Settings"}
        settings.start_page = (
            settings.start_page
            if isinstance(settings.start_page, str) and settings.start_page in pages
            else "Overview"
        )
        if not isinstance(settings.excluded_patterns, list):
            settings.excluded_patterns = []
        settings.excluded_patterns = [
            value.strip()[:128]
            for value in settings.excluded_patterns[:100]
            if isinstance(value, str) and value.strip()
        ]
        if not isinstance(settings.ollama_model, str):
            settings.ollama_model = ""
        settings.ollama_model = settings.ollama_model[:128]
        if not isinstance(settings.model_cache_path, str):
            settings.model_cache_path = ""
        if not isinstance(settings.enabled_text_model, bool):
            settings.enabled_text_model = False
        if not isinstance(settings.enabled_image_model, bool):
            settings.enabled_image_model = False
        return settings

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                data = asdict(settings)
                data["schema_version"] = 1
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            Path(temp_name).unlink(missing_ok=True)


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return min(maximum, max(minimum, value))
