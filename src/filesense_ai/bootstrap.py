from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from filesense_ai.config import setup_logging
from filesense_ai.core.paths import data_directory
from filesense_ai.ui.main_window import MainWindow
from filesense_ai.ui.theme import apply_theme


def main() -> int:
    smoke = "--smoke" in sys.argv[1:]
    app = QApplication([sys.argv[0]])
    app.setApplicationName("FileSense AI")
    app.setOrganizationName("Energetic Edge")
    app.setOrganizationDomain("energeticedge.lk")
    app.setApplicationVersion("0.1.0")
    app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    data_dir = data_directory(app_data)
    setup_logging(data_dir)
    try:
        window = MainWindow(data_dir)
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        icon = bundle_root / "assets" / "filesense-ai.svg"
        if icon.exists():
            window.setWindowIcon(QIcon(str(icon)))
        apply_theme(app, window.settings.theme)
        window.show()
        if smoke:
            app.processEvents()
            window.close()
            return 0
        return app.exec()
    except Exception:
        logging.getLogger("filesense_ai").exception("Application startup failed")
        QMessageBox.critical(
            None,
            "FileSense AI could not start",
            f"Startup failed. See the local log at:\n{data_dir / 'logs' / 'filesense.log'}",
        )
        return 1
