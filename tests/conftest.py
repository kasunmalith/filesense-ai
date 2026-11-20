import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from filesense_ai.db.connection import Database


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    yield db
    db.close()
