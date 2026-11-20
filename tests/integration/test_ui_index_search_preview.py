from filesense_ai.db.connection import Database
from filesense_ai.db.repositories import Repository
from filesense_ai.indexing.service import IndexingService
from filesense_ai.ui.main_window import MainWindow


def test_index_keyword_search_and_preview_flow(qtbot, tmp_path):
    root = tmp_path / "synthetic-sample"
    root.mkdir()
    (root / "travel.txt").write_text(
        "Synthetic trip expense: lodging and hotel breakfast receipt.", encoding="utf-8"
    )
    data = tmp_path / "app-data"
    database = Database(data / "filesense.sqlite3")
    root_id = Repository(database.connection).add_root(root)
    result = IndexingService(database.connection, protected_paths={data}).index_root(root_id)
    database.close()
    assert result["indexed"] == 1

    window = MainWindow(data)
    qtbot.addWidget(window)
    window.navigate("Search")
    window.search_input.setText("hotel receipt")
    window._start_search()
    qtbot.waitUntil(lambda: window.results_list.count() == 1, timeout=5000)
    window.results_list.setCurrentRow(0)
    window._show_result_preview(window.results_list.currentItem())
    assert "hotel breakfast" in window.preview_text.toPlainText()
    assert "In indexed folder: travel.txt" in window.preview_path.text()
    assert str(root) not in window.preview_path.text()
    window.close()
