from __future__ import annotations

import sqlite3
from pathlib import Path

from filesense_ai.db.schema import SCHEMA, SCHEMA_VERSION


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=30000")
        self.initialize()

    def initialize(self) -> None:
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"Database schema {version} is newer than this app supports")
        try:
            self.connection.executescript(SCHEMA)
        except sqlite3.Error:
            self.connection.rollback()
            raise

    def close(self) -> None:
        self.connection.close()

    def reset_index(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM chunk_fts")
            self.connection.execute("DELETE FROM roots")
            self.connection.execute("DELETE FROM indexing_runs")
