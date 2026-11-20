from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from filesense_ai.db.connection import Database
from filesense_ai.db.repositories import Repository
from filesense_ai.indexing.service import IndexingService
from filesense_ai.search.keyword import keyword_search
from filesense_ai.ui.main_window import MainWindow
from filesense_ai.ui.theme import apply_theme
from scripts.create_demo_data import create_demo_data


def main() -> int:
    project = Path(__file__).resolve().parents[1]
    demo = create_demo_data(project / "demo-data" / "screenshot")
    with TemporaryDirectory(prefix="filesense-screenshot-") as temp:
        data_dir = Path(temp)
        database = Database(data_dir / "filesense.sqlite3")
        root_id = Repository(database.connection).add_root(demo)
        IndexingService(database.connection, protected_paths={data_dir}).index_root(root_id)
        database.close()

        app = QApplication(["FileSense AI screenshot"])
        app.setApplicationName("FileSense AI")
        app.setOrganizationName("Energetic Edge")
        window = MainWindow(data_dir)
        apply_theme(app, "dark")
        window.resize(1360, 860)
        window.navigate("Search")
        window.search_input.setText("lodging")
        window.show()
        hits = keyword_search(window.database.connection, "lodging")
        window._search_generation = 1
        window._search_complete(1, hits)
        if not hits:
            window.close()
            raise RuntimeError("Synthetic search did not return a result")
        window.results_list.setCurrentRow(0)
        window._show_result_preview(window.results_list.currentItem())
        app.processEvents()
        target = project / "screenshots" / "filesense-ai-search.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(target)):
            window.close()
            raise RuntimeError("Qt could not save the real UI screenshot")
        window.close()
        print(f"Saved actual FileSense AI screenshot: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
