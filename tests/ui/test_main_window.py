import sys
from types import SimpleNamespace

from filesense_ai.ui.main_window import NAVIGATION, MainWindow


def test_native_window_starts_without_ai_and_exposes_all_pages(qtbot, tmp_path):
    window = MainWindow(tmp_path / "app-data")
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle() == "FileSense AI"
    assert [
        window.stack.widget(i).property("pageName") for i in range(window.stack.count())
    ] == list(NAVIGATION)
    assert window.settings.enabled_text_model is False
    assert "torch" not in sys.modules
    assert "open_clip" not in sys.modules
    window.navigate("Search")
    assert window.page_title.text() == "Search"
    window.close()


def test_latest_image_request_is_queued_and_stale_results_are_ignored(qtbot, tmp_path):
    window = MainWindow(tmp_path / "app-data")
    qtbot.addWidget(window)
    window.image_list.addItem("old result")
    window.image_worker = SimpleNamespace(isRunning=lambda: True)

    window._start_image_worker("mountains", False, 0)
    window._start_image_worker("beach", False, 0)

    assert window._pending_image_request == ("beach", False, 0)
    assert window.image_list.count() == 0
    window._images_loaded(1, 0, [], False)
    assert "Waiting for the current" in window.image_count.text()
    window.close()
