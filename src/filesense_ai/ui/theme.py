from __future__ import annotations

from PySide6.QtGui import QColor, QPalette


def apply_theme(app, theme: str) -> None:
    dark = theme == "dark"
    colors = {
        "canvas": "#10141C" if dark else "#F4F6FA",
        "surface": "#171D28" if dark else "#FFFFFF",
        "surface2": "#202838" if dark else "#E9EDF4",
        "border": "#303A4C" if dark else "#D2D8E2",
        "text": "#EAF0FA" if dark else "#172033",
        "muted": "#AAB7CC" if dark else "#58657A",
        "accent": "#6CA7FF",
        "accent_hover": "#8AB8FF",
        "danger": "#FF8B8B",
    }
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["canvas"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["surface2"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["surface2"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        QWidget {{ font-family: 'Segoe UI'; font-size: 10pt; color: {colors["text"]}; }}
        QMainWindow, QWidget#root {{ background: {colors["canvas"]}; }}
        QFrame#sidebar {{ background: {colors["surface"]}; border-right: 1px solid {colors["border"]}; }}
        QFrame#panel, QGroupBox {{ background: {colors["surface"]}; border: 1px solid {colors["border"]}; border-radius: 10px; }}
        QGroupBox {{ margin-top: 12px; padding: 14px 10px 10px; font-weight: 600; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
        QPushButton {{ background: {colors["surface2"]}; border: 1px solid {colors["border"]}; border-radius: 7px; padding: 8px 12px; }}
        QPushButton:hover {{ border-color: {colors["accent"]}; }}
        QPushButton:focus, QLineEdit:focus, QComboBox:focus {{ border: 2px solid {colors["accent"]}; }}
        QPushButton#primary {{ background: {colors["accent"]}; border-color: {colors["accent"]}; color: #081322; font-weight: 650; }}
        QPushButton#primary:hover {{ background: {colors["accent_hover"]}; }}
        QPushButton#nav {{ text-align: left; padding: 10px 12px; border: 0; background: transparent; }}
        QPushButton#nav:checked {{ background: {colors["surface2"]}; color: {colors["accent"]}; font-weight: 650; }}
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QListWidget, QTableWidget {{ background: {colors["surface"]}; border: 1px solid {colors["border"]}; border-radius: 7px; padding: 7px; selection-background-color: {colors["accent"]}; }}
        QLabel#title {{ font-size: 21pt; font-weight: 650; }}
        QLabel#subtitle, QLabel#muted {{ color: {colors["muted"]}; }}
        QStatusBar {{ border-top: 1px solid {colors["border"]}; color: {colors["muted"]}; }}
        QScrollArea {{ border: 0; }}
    """)
