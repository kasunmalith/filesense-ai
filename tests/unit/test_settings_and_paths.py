import json

from filesense_ai.config import SettingsStore
from filesense_ai.core.models import AppSettings
from filesense_ai.core.paths import data_directory


def test_data_directory_uses_qt_location_and_creates_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("FILESENSE_DATA_DIR", raising=False)
    location = tmp_path / "user data"
    result = data_directory(location)
    assert result == location
    assert result.is_dir()


def test_data_directory_override_wins(tmp_path, monkeypatch):
    override = tmp_path / "portable"
    monkeypatch.setenv("FILESENSE_DATA_DIR", str(override))
    assert data_directory(tmp_path / "qt") == override


def test_settings_atomic_round_trip_and_version(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    expected = AppSettings(theme="light", max_file_size_mb=15, excluded_patterns=["private-cache"])
    store.save(expected)
    loaded = store.load()
    assert loaded == expected
    assert json.loads(store.path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    assert SettingsStore(path).load() == AppSettings()
