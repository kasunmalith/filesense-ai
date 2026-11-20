from __future__ import annotations

import csv
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from filesense_ai.config import SettingsStore
from filesense_ai.core.paths import data_directory
from filesense_ai.db.connection import Database
from filesense_ai.db.repositories import Repository
from filesense_ai.ui.theme import apply_theme
from filesense_ai.ui.workers import (
    ChatWorker,
    DuplicateWorker,
    ImageWorker,
    IndexWorker,
    ModelWorker,
    SearchWorker,
)

logger = logging.getLogger("filesense_ai.ui")
NAVIGATION = ("Overview", "Search", "Images", "Duplicates", "Ask Files", "Settings")


def panel() -> QFrame:
    frame = QFrame()
    frame.setObjectName("panel")
    return frame


def heading(text: str, subtext: str = "") -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    title = QLabel(text)
    title.setObjectName("title")
    layout.addWidget(title)
    if subtext:
        note = QLabel(subtext)
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        layout.addWidget(note)
    return widget


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path | None = None) -> None:
        super().__init__()
        self.data_dir = data_dir or data_directory()
        self.db_path = self.data_dir / "filesense.sqlite3"
        self.database = Database(self.db_path)
        self.repo = Repository(self.database.connection)
        self.settings_store = SettingsStore(self.data_dir / "settings.json")
        self.settings = self.settings_store.load()
        self.model_cache = (
            Path(self.settings.model_cache_path)
            if self.settings.model_cache_path
            else self.data_dir / "models"
        )
        self.model_cache.mkdir(parents=True, exist_ok=True)
        self.jobs: list = []
        self._search_generation = 0
        self._current_hits = []
        self._image_items = []
        self._image_generation = 0
        self._pending_image_request: tuple[str, bool, int] | None = None
        self._duplicate_groups = []
        self._chat_citations = {}
        self._chat_history: list[tuple[str, str]] = []
        self._chat_worker = None
        self.setWindowTitle("FileSense AI")
        self.setMinimumSize(1024, 700)
        self.resize(1360, 860)
        self._build_shell()
        self._build_pages()
        self._connect_shortcuts()
        self._restore_geometry()
        self._refresh_overview()
        self._refresh_root_filters()
        self._update_model_state()
        self.navigate(
            self.settings.start_page if self.settings.start_page in NAVIGATION else "Overview"
        )

    def _build_shell(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 22, 16, 12)
        brand = QLabel("◉  FileSense AI")
        brand.setStyleSheet("font-size: 17pt; font-weight: 700; padding: 4px 2px 16px;")
        side.addWidget(brand)
        self.nav_buttons: dict[str, QPushButton] = {}
        for page in NAVIGATION:
            button = QPushButton(page)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setAccessibleName(f"Open {page} page")
            button.clicked.connect(lambda checked=False, name=page: self.navigate(name))
            self.nav_buttons[page] = button
            side.addWidget(button)
        side.addStretch(1)
        privacy = QLabel("Your indexed content stays on this device. AI features are optional.")
        privacy.setObjectName("muted")
        privacy.setWordWrap(True)
        side.addWidget(privacy)
        credit = QLabel(
            'Software Development by <a href="https://www.energeticedge.lk/">Energetic Edge (Pvt) Ltd</a>'
        )
        credit.setOpenExternalLinks(True)
        credit.setObjectName("muted")
        credit.setWordWrap(True)
        credit.setStyleSheet("font-size: 8pt; padding-top: 10px;")
        side.addWidget(credit)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(24, 18, 24, 16)
        right_layout.setSpacing(12)
        top = QHBoxLayout()
        self.page_title = QLabel("Overview")
        self.page_title.setStyleSheet("font-size: 11pt; font-weight: 600;")
        top.addWidget(self.page_title)
        top.addStretch(1)
        self.job_label = QLabel("Ready")
        self.job_label.setObjectName("muted")
        top.addWidget(self.job_label)
        right_layout.addLayout(top)
        self.stack = QStackedWidget()
        right_layout.addWidget(self.stack, 1)
        outer.addWidget(sidebar)
        outer.addWidget(right, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready")

    def _build_pages(self) -> None:
        self._build_overview()
        self._build_search()
        self._build_images()
        self._build_duplicates()
        self._build_chat()
        self._build_settings()

    def _add_page(self, name: str, widget: QWidget) -> None:
        widget.setProperty("pageName", name)
        self.stack.addWidget(widget)

    def navigate(self, name: str) -> None:
        index = NAVIGATION.index(name)
        self.stack.setCurrentIndex(index)
        self.page_title.setText(name)
        for page, button in self.nav_buttons.items():
            button.setChecked(page == name)
        self.settings.start_page = name
        self.settings_store.save(self.settings)
        if name == "Images":
            self._load_images()
        elif name == "Duplicates":
            self._load_duplicates()
        elif name == "Overview":
            self._refresh_overview()

    def _build_overview(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.addWidget(
            heading(
                "Find files by meaning, not just by filename",
                "Choose only the folders you want FileSense AI to index. Scanning never deletes or changes your files.",
            )
        )
        stats_panel = panel()
        stats_layout = QHBoxLayout(stats_panel)
        self.stat_files = QLabel("0")
        self.stat_docs = QLabel("0")
        self.stat_images = QLabel("0")
        self.stat_roots = QLabel("0")
        for title, value in (
            ("Indexed files", self.stat_files),
            ("Searchable documents", self.stat_docs),
            ("Images", self.stat_images),
            ("Folders", self.stat_roots),
        ):
            cell = QVBoxLayout()
            value.setStyleSheet("font-size: 23pt; font-weight: 700;")
            label = QLabel(title)
            label.setObjectName("muted")
            cell.addWidget(value)
            cell.addWidget(label)
            stats_layout.addLayout(cell, 1)
        layout.addWidget(stats_panel)
        manager = panel()
        manager_layout = QVBoxLayout(manager)
        title_row = QHBoxLayout()
        title = QLabel("Indexed folders")
        title.setStyleSheet("font-size: 14pt; font-weight: 650;")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.add_root_button = QPushButton("Add folder")
        self.add_root_button.setObjectName("primary")
        self.add_root_button.clicked.connect(self._add_root)
        title_row.addWidget(self.add_root_button)
        manager_layout.addLayout(title_row)
        self.root_list = QListWidget()
        self.root_list.setAccessibleName("Folders selected for indexing")
        self.root_list.currentItemChanged.connect(self._root_selection_changed)
        manager_layout.addWidget(self.root_list, 1)
        controls = QHBoxLayout()
        self.index_button = QPushButton("Index selected folder")
        self.index_button.setObjectName("primary")
        self.index_button.clicked.connect(self._start_selected_index)
        self.remove_root_button = QPushButton("Remove from index…")
        self.remove_root_button.clicked.connect(self._remove_selected_root)
        self.toggle_root_button = QPushButton("Disable folder")
        self.toggle_root_button.clicked.connect(self._toggle_selected_root)
        self.cancel_index_button = QPushButton("Cancel scan")
        self.cancel_index_button.setEnabled(False)
        self.cancel_index_button.clicked.connect(self._cancel_index)
        controls.addWidget(self.index_button)
        controls.addWidget(self.remove_root_button)
        controls.addWidget(self.toggle_root_button)
        controls.addWidget(self.cancel_index_button)
        controls.addStretch(1)
        manager_layout.addLayout(controls)
        self.index_progress = QProgressBar()
        self.index_progress.setRange(0, 0)
        self.index_progress.hide()
        manager_layout.addWidget(self.index_progress)
        self.index_detail = QLabel("No scanning runs yet.")
        self.index_detail.setObjectName("muted")
        manager_layout.addWidget(self.index_detail)
        layout.addWidget(manager, 1)
        layout.addWidget(
            heading(
                "What stays local",
                "File metadata, extracted text, indexes, thumbnails and optional model caches are stored in your app data folder. No telemetry or cloud content processing.",
            )
        )
        self._add_page("Overview", page)

    def _build_search(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.addWidget(
            heading(
                "Search your indexed files",
                "Keyword search works offline without AI models. Semantic search uses an optional local model.",
            )
        )
        controls = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Try “hotel receipt” or a filename…")
        self.search_input.setAccessibleName("Search indexed file contents")
        self.search_input.returnPressed.connect(self._start_search)
        self.search_mode = QComboBox()
        self.search_mode.addItems(["Keyword", "Hybrid", "Semantic"])
        self.search_kind = QComboBox()
        self.search_kind.addItem("All types", "")
        self.search_kind.addItem("Documents", "document")
        self.search_kind.addItem("Images", "image")
        for extension in (".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx"):
            self.search_kind.addItem(extension.upper(), f"ext:{extension}")
        self.search_root = QComboBox()
        self.search_root.addItem("All folders", "")
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("primary")
        self.search_button.clicked.connect(self._start_search)
        controls.addWidget(self.search_input, 1)
        controls.addWidget(self.search_mode)
        controls.addWidget(self.search_kind)
        controls.addWidget(self.search_root)
        controls.addWidget(self.search_button)
        layout.addLayout(controls)
        self.search_notice = QLabel("No models are loaded. Keyword mode is ready.")
        self.search_notice.setObjectName("muted")
        layout.addWidget(self.search_notice)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        results_panel = panel()
        result_layout = QVBoxLayout(results_panel)
        self.search_count = QLabel("Enter a search to see results.")
        self.search_count.setObjectName("muted")
        result_layout.addWidget(self.search_count)
        self.results_list = QListWidget()
        self.results_list.itemClicked.connect(self._show_result_preview)
        result_layout.addWidget(self.results_list, 1)
        preview_panel = panel()
        preview_layout = QVBoxLayout(preview_panel)
        self.preview_title = QLabel("Select a result")
        self.preview_title.setStyleSheet("font-weight: 650; font-size: 13pt;")
        preview_layout.addWidget(self.preview_title)
        self.preview_path = QLabel("")
        self.preview_path.setObjectName("muted")
        self.preview_path.setWordWrap(True)
        preview_layout.addWidget(self.preview_path)
        preview_actions = QHBoxLayout()
        for label, method in (
            ("Open file", self._open_result),
            ("Show in folder", self._reveal_result),
            ("Copy path", self._copy_result_path),
        ):
            button = QPushButton(label)
            button.clicked.connect(method)
            preview_actions.addWidget(button)
        preview_layout.addLayout(preview_actions)
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setAccessibleName("Extracted file preview")
        preview_layout.addWidget(self.preview_text, 1)
        splitter.addWidget(results_panel)
        splitter.addWidget(preview_panel)
        splitter.setSizes([430, 650])
        layout.addWidget(splitter, 1)
        self._add_page("Search", page)

    def _build_images(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.addWidget(
            heading(
                "Images",
                "Browse the images in your indexed folders. Optional CLIP search compares image and text vectors in the same model space.",
            )
        )
        controls = QHBoxLayout()
        self.image_query = QLineEdit()
        self.image_query.setPlaceholderText("Search image contents, e.g. sunset landscape")
        self.image_query.setAccessibleName("Search image contents or filenames")
        self.image_query.returnPressed.connect(self._search_images)
        self.image_ai = QCheckBox("Use CLIP content search")
        self.image_ai.setChecked(self.settings.enabled_image_model)
        self.image_ai.stateChanged.connect(lambda _: self._search_images())
        self.enable_clip_button = QPushButton("Download / build image model…")
        self.enable_clip_button.clicked.connect(self._enable_clip)
        self.image_count = QLabel("No images indexed yet.")
        self.image_count.setObjectName("muted")
        controls.addWidget(self.image_query, 1)
        controls.addWidget(self.image_ai)
        controls.addWidget(self.enable_clip_button)
        layout.addLayout(controls)
        filters = QHBoxLayout()
        self.image_root = QComboBox()
        self.image_root.addItem("All folders", "")
        self.image_type = QComboBox()
        self.image_type.addItem("All image types", "")
        for extension in (".jpg", ".jpeg", ".png", ".webp"):
            self.image_type.addItem(extension.upper(), extension)
        self.image_min_width = QSpinBox()
        self.image_min_width.setRange(0, 100_000)
        self.image_min_width.setPrefix("Min W ")
        self.image_min_width.setSuffix(" px")
        self.image_min_height = QSpinBox()
        self.image_min_height.setRange(0, 100_000)
        self.image_min_height.setPrefix("Min H ")
        self.image_min_height.setSuffix(" px")
        self.image_recent_days = QSpinBox()
        self.image_recent_days.setRange(0, 3650)
        self.image_recent_days.setPrefix("Modified in last ")
        self.image_recent_days.setSuffix(" days (0 = any)")
        for widget in (
            self.image_root,
            self.image_type,
            self.image_min_width,
            self.image_min_height,
            self.image_recent_days,
        ):
            filters.addWidget(widget)
        filters.addStretch(1)
        layout.addLayout(filters)
        self.image_root.currentIndexChanged.connect(self._search_images)
        self.image_type.currentIndexChanged.connect(self._search_images)
        self.image_min_width.valueChanged.connect(self._search_images)
        self.image_min_height.valueChanged.connect(self._search_images)
        self.image_recent_days.valueChanged.connect(self._search_images)
        layout.addWidget(self.image_count)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.image_list = QListWidget()
        self.image_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.image_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.image_list.setIconSize(QSize(144, 104))
        self.image_list.setGridSize(QSize(180, 145))
        self.image_list.itemClicked.connect(self._show_image_preview)
        splitter.addWidget(self.image_list)
        detail = panel()
        detail_layout = QVBoxLayout(detail)
        self.image_preview = QLabel("Select an image")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumHeight(260)
        self.image_preview.setScaledContents(False)
        detail_layout.addWidget(self.image_preview, 1)
        self.image_details = QLabel("")
        self.image_details.setWordWrap(True)
        detail_layout.addWidget(self.image_details)
        image_actions = QHBoxLayout()
        for label, method in (
            ("Open file", self._open_image),
            ("Show in folder", self._reveal_image),
            ("Copy path", self._copy_image_path),
        ):
            button = QPushButton(label)
            button.clicked.connect(method)
            image_actions.addWidget(button)
        detail_layout.addLayout(image_actions)
        splitter.addWidget(detail)
        splitter.setSizes([640, 390])
        layout.addWidget(splitter, 1)
        self.image_load_more = QPushButton("Load next 120 images")
        self.image_load_more.clicked.connect(self._load_more_images)
        self.image_load_more.hide()
        layout.addWidget(self.image_load_more, alignment=Qt.AlignmentFlag.AlignLeft)
        self._add_page("Images", page)

    def _build_duplicates(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.addWidget(
            heading(
                "Duplicate review",
                "Review-only by design. Exact matches are byte-identical; similar images are visual suggestions. Nothing is deleted or moved.",
            )
        )
        controls = QHBoxLayout()
        self.duplicate_refresh = QPushButton("Analyze indexed files")
        self.duplicate_refresh.setObjectName("primary")
        self.duplicate_refresh.clicked.connect(self._load_duplicates)
        self.duplicate_export = QPushButton("Export metadata CSV…")
        self.duplicate_export.clicked.connect(self._export_duplicates)
        controls.addWidget(self.duplicate_refresh)
        controls.addWidget(self.duplicate_export)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.duplicate_summary = QLabel("Select Analyze to inspect indexed files.")
        self.duplicate_summary.setObjectName("muted")
        layout.addWidget(self.duplicate_summary)
        self.duplicate_tabs = QTabWidget()
        self.exact_list = QListWidget()
        self.similar_list = QListWidget()
        self.duplicate_tabs.addTab(self.exact_list, "Exact matches")
        self.duplicate_tabs.addTab(self.similar_list, "Similar images")
        self.duplicate_tabs.currentChanged.connect(self._select_duplicate_list)
        self.duplicate_details = QPlainTextEdit()
        self.duplicate_details.setReadOnly(True)
        self.duplicate_details.setPlaceholderText(
            "Select a group to review its paths and estimated reclaimable space."
        )
        bottom = QHBoxLayout()
        bottom.addWidget(self.duplicate_tabs, 1)
        bottom.addWidget(self.duplicate_details, 1)
        layout.addLayout(bottom, 1)
        self.exact_list.itemClicked.connect(self._show_duplicate_group)
        self.similar_list.itemClicked.connect(self._show_duplicate_group)
        self._add_page("Duplicates", page)

    def _build_chat(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.addWidget(
            heading(
                "Ask Files",
                "Optional local Ollama chat. Retrieved excerpts are sent only to 127.0.0.1; answers may still be inaccurate.",
            )
        )
        connection = QHBoxLayout()
        self.chat_model = QLineEdit(self.settings.ollama_model)
        self.chat_model.setPlaceholderText("Installed Ollama model, e.g. llama3.2:3b")
        self.chat_model.setAccessibleName("Local Ollama model name")
        self.chat_root = QComboBox()
        self.chat_root.addItem("All indexed folders", "")
        self.chat_check = QPushButton("Check local Ollama")
        self.chat_check.clicked.connect(self._check_ollama)
        self.chat_clear = QPushButton("Clear chat")
        self.chat_clear.clicked.connect(self._clear_chat)
        connection.addWidget(QLabel("Model"))
        connection.addWidget(self.chat_model, 1)
        connection.addWidget(self.chat_root)
        connection.addWidget(self.chat_check)
        connection.addWidget(self.chat_clear)
        layout.addLayout(connection)
        self.chat_state = QLabel(
            "Ollama is optional. Install Ollama and a local model, then check the loopback connection."
        )
        self.chat_state.setObjectName("muted")
        layout.addWidget(self.chat_state)
        self.chat_transcript = QPlainTextEdit()
        self.chat_transcript.setReadOnly(True)
        self.chat_transcript.setAccessibleName("Ask Files conversation")
        layout.addWidget(self.chat_transcript, 1)
        self.sources_label = QLabel("Verified sources appear below after each answer.")
        self.sources_label.setObjectName("muted")
        layout.addWidget(self.sources_label)
        self.sources_list = QListWidget()
        self.sources_list.setMaximumHeight(104)
        self.sources_list.itemDoubleClicked.connect(self._open_citation)
        layout.addWidget(self.sources_list)
        self.chat_question = QLineEdit()
        self.chat_question.setPlaceholderText("Ask a question about your indexed files…")
        self.chat_question.returnPressed.connect(self._ask_files)
        ask_row = QHBoxLayout()
        self.chat_send = QPushButton("Ask")
        self.chat_send.setObjectName("primary")
        self.chat_send.clicked.connect(self._ask_files)
        self.chat_stop = QPushButton("Stop")
        self.chat_stop.setEnabled(False)
        self.chat_stop.clicked.connect(self._stop_chat)
        ask_row.addWidget(self.chat_question, 1)
        ask_row.addWidget(self.chat_send)
        ask_row.addWidget(self.chat_stop)
        layout.addLayout(ask_row)
        self._add_page("Ask Files", page)

    def _build_settings(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.addWidget(
            heading("Settings", "Control storage, local models, theme and index lifecycle.")
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        models = panel()
        model_layout = QVBoxLayout(models)
        model_layout.addWidget(QLabel("Optional local AI models"))
        self.text_model_state = QLabel("")
        self.text_model_state.setObjectName("muted")
        self.clip_model_state = QLabel("")
        self.clip_model_state.setObjectName("muted")
        model_layout.addWidget(self.text_model_state)
        model_layout.addWidget(self.clip_model_state)
        cache_row = QHBoxLayout()
        self.model_cache_label = QLabel(str(self.model_cache))
        self.model_cache_label.setObjectName("muted")
        self.model_cache_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cache_button = QPushButton("Choose model storage…")
        cache_button.clicked.connect(self._choose_model_cache)
        cache_row.addWidget(self.model_cache_label, 1)
        cache_row.addWidget(cache_button)
        model_layout.addLayout(cache_row)
        model_buttons = QHBoxLayout()
        self.text_model_button = QPushButton("Download + index text model…")
        self.text_model_button.clicked.connect(self._enable_text_model)
        self.clip_model_settings_button = QPushButton("Download + index CLIP model…")
        self.clip_model_settings_button.clicked.connect(self._enable_clip)
        model_buttons.addWidget(self.text_model_button)
        model_buttons.addWidget(self.clip_model_settings_button)
        model_layout.addLayout(model_buttons)
        body.addWidget(models)
        prefs = panel()
        prefs_layout = QVBoxLayout(prefs)
        prefs_layout.addWidget(QLabel("Application preferences"))
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Appearance"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(self.settings.theme)
        self.theme_combo.currentTextChanged.connect(self._set_theme)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        prefs_layout.addLayout(theme_row)
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Maximum file size to index (MB)"))
        self.max_size = QSpinBox()
        self.max_size.setRange(1, 2048)
        self.max_size.setValue(max(1, min(2048, self.settings.max_file_size_mb)))
        self.max_size.valueChanged.connect(self._save_preferences)
        size_row.addWidget(self.max_size)
        size_row.addStretch(1)
        prefs_layout.addLayout(size_row)
        character_row = QHBoxLayout()
        character_row.addWidget(QLabel("Maximum extracted characters per file"))
        self.max_chars = QSpinBox()
        self.max_chars.setRange(1000, 10_000_000)
        self.max_chars.setSingleStep(100_000)
        self.max_chars.setValue(self.settings.max_document_chars)
        self.max_chars.valueChanged.connect(self._save_preferences)
        character_row.addWidget(self.max_chars)
        character_row.addStretch(1)
        prefs_layout.addLayout(character_row)
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Maximum files per folder scan"))
        self.max_files = QSpinBox()
        self.max_files.setRange(1, 1_000_000)
        self.max_files.setSingleStep(1000)
        self.max_files.setValue(self.settings.max_indexed_files)
        self.max_files.valueChanged.connect(self._save_preferences)
        count_row.addWidget(self.max_files)
        count_row.addStretch(1)
        prefs_layout.addLayout(count_row)
        exclusion_row = QHBoxLayout()
        exclusion_row.addWidget(QLabel("Extra excluded folder names"))
        self.exclusions_input = QLineEdit(", ".join(self.settings.excluded_patterns))
        self.exclusions_input.setPlaceholderText("Separate folder names with commas")
        self.exclusions_input.editingFinished.connect(self._save_preferences)
        exclusion_row.addWidget(self.exclusions_input, 1)
        prefs_layout.addLayout(exclusion_row)
        body.addWidget(prefs)
        privacy = panel()
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.addWidget(QLabel("Privacy and storage"))
        privacy_text = QLabel(
            f"App data folder: {self.data_dir}\n\nNo telemetry or remote content analysis. Semantic models are downloaded only after you choose a model action. The English MiniLM model is not evaluated for Sinhala or Tamil semantic accuracy. Ollama is restricted to localhost."
        )
        privacy_text.setWordWrap(True)
        privacy_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        privacy_layout.addWidget(privacy_text)
        body.addWidget(privacy)
        reset = panel()
        reset_layout = QVBoxLayout(reset)
        reset_layout.addWidget(QLabel("Index management"))
        reset_note = QLabel(
            "Clearing the index removes only FileSense AI's database records. Original files stay where they are."
        )
        reset_note.setObjectName("muted")
        reset_note.setWordWrap(True)
        reset_layout.addWidget(reset_note)
        self.reset_index_button = QPushButton("Clear index…")
        self.reset_index_button.clicked.connect(self._reset_index)
        reset_layout.addWidget(self.reset_index_button, alignment=Qt.AlignmentFlag.AlignLeft)
        body.addWidget(reset)
        body.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self._add_page("Settings", page)

    def _connect_shortcuts(self) -> None:
        search_action = QAction(self)
        search_action.setShortcut(QKeySequence("Ctrl+K"))
        search_action.triggered.connect(
            lambda: (self.navigate("Search"), self.search_input.setFocus())
        )
        self.addAction(search_action)
        folder_action = QAction(self)
        folder_action.setShortcut(QKeySequence("Ctrl+O"))
        folder_action.triggered.connect(self._add_root)
        self.addAction(folder_action)
        cancel_action = QAction(self)
        cancel_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        cancel_action.triggered.connect(self._escape)
        self.addAction(cancel_action)

    def _restore_geometry(self) -> None:
        settings = QSettings("Energetic Edge", "FileSense AI")
        geometry = settings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:
        running = [job for job in self.jobs if job.isRunning()]
        if running:
            if getattr(self, "current_index_worker", None) in running:
                self.current_index_worker.token.cancel()
            if self._chat_worker in running:
                self._chat_worker.cancel()
            for job in running:
                job.wait(1500)
            if any(job.isRunning() for job in running):
                QMessageBox.information(
                    self,
                    "Background work is still running",
                    "Wait for the current model or file operation to finish, then close FileSense AI.",
                )
                event.ignore()
                return
        QSettings("Energetic Edge", "FileSense AI").setValue("window_geometry", self.saveGeometry())
        self.settings_store.save(self.settings)
        self.database.close()
        super().closeEvent(event)

    def _add_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder to index")
        if not folder:
            return
        path = Path(folder)
        if not path.is_dir():
            QMessageBox.warning(
                self, "Folder unavailable", "The selected folder is not accessible."
            )
            return
        protected = {
            self.data_dir.resolve(),
            Path(os.environ.get("WINDIR", "C:\\Windows")).resolve(),
        }
        protected.update(
            Path(value).resolve()
            for value in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"))
            if value
        )
        broad = path.resolve() == Path(path.anchor).resolve() or path.resolve() in protected
        if broad:
            answer = QMessageBox.warning(
                self,
                "Broad system folder",
                f"This folder can contain application or operating system data:\n\n{path}\n\nFileSense AI will still skip its own app-data folder. Continue only if you intend to index this broad location.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.repo.add_root(path, self.settings.excluded_patterns)
        self._refresh_overview()
        self._refresh_root_filters()
        self.statusBar().showMessage("Folder added. Start indexing when you are ready.", 5000)

    def _selected_root_id(self) -> str | None:
        item = self.root_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _root_selection_changed(self, current, _previous) -> None:
        self.toggle_root_button.setEnabled(current is not None)
        if current:
            root = self.repo.root(current.data(Qt.ItemDataRole.UserRole))
            self.toggle_root_button.setText(
                "Disable folder" if root and root["enabled"] else "Enable folder"
            )

    def _toggle_selected_root(self) -> None:
        root_id = self._selected_root_id()
        if not root_id:
            return
        enabled = self.repo.root(root_id)["enabled"]
        self.repo.set_root_enabled(root_id, not bool(enabled))
        self._refresh_overview()
        self._refresh_root_filters()

    def _start_selected_index(self) -> None:
        root_id = self._selected_root_id()
        if not root_id:
            QMessageBox.information(
                self, "Choose a folder", "Add and select a folder before indexing."
            )
            return
        worker = IndexWorker(
            self.db_path,
            root_id,
            self.max_size.value() * 1024 * 1024,
            self.settings.max_document_chars,
            self.settings.max_indexed_files,
            self.settings.enabled_text_model,
            self.model_cache,
        )
        worker.progress.connect(self._index_progress)
        worker.result.connect(self._index_complete)
        worker.failed.connect(self._job_failed)
        worker.finished.connect(lambda: self._job_finished(worker))
        self._start_job(worker)
        self.current_index_worker = worker
        self.index_progress.show()
        self.cancel_index_button.setEnabled(True)
        self.index_button.setEnabled(False)
        self.job_label.setText("Indexing selected folder…")

    def _cancel_index(self) -> None:
        worker = getattr(self, "current_index_worker", None)
        if worker and worker.isRunning():
            worker.token.cancel()
            self.cancel_index_button.setEnabled(False)
            self.index_detail.setText("Cancel requested; finishing the current file safely…")

    def _index_progress(self, event) -> None:
        if event.kind == "progress":
            self.index_detail.setText(
                f"Scanned {event.scanned} · indexed {event.indexed} · unchanged {event.skipped} · errors {event.errors}\n{Path(event.path).name}"
            )
        elif event.kind == "semantic":
            self.index_detail.setText(event.message)

    def _index_complete(self, stats: dict) -> None:
        self.index_detail.setText(
            f"Scan {stats['status']}: {stats['scanned']} files checked, {stats['indexed']} indexed, {stats['skipped']} unchanged, {stats['errors']} errors."
        )
        self.statusBar().showMessage(f"Index scan {stats['status']}.", 6000)
        self._refresh_overview()
        self._refresh_root_filters()

    def _remove_selected_root(self) -> None:
        root_id = self._selected_root_id()
        if not root_id:
            return
        row = self.repo.root(root_id)
        answer = QMessageBox.question(
            self,
            "Remove indexed folder",
            f"Remove this folder and its index records?\n\n{row['path']}\n\nThis does not delete any source files.",
            QMessageBox.StandardButton.Remove | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Remove:
            self.repo.remove_root(root_id)
            from filesense_ai.images.catalog import ImageCatalog

            ImageCatalog(self.database.connection).prune_orphans()
            self._refresh_overview()
            self._refresh_root_filters()

    def _refresh_overview(self) -> None:
        stats = self.repo.stats()
        roots = self.repo.roots()
        self.stat_files.setText(str(stats["files"]))
        self.stat_docs.setText(str(stats["documents"]))
        self.stat_images.setText(str(stats["images"]))
        self.stat_roots.setText(str(len(roots)))
        current = self._selected_root_id() if hasattr(self, "root_list") else None
        if hasattr(self, "root_list"):
            self.root_list.clear()
            for root in roots:
                count = self.repo.file_count(root["id"])
                state = "enabled" if root["enabled"] else "disabled"
                item = QListWidgetItem(
                    f"{root['path']}    ·    {count} indexed files    ·    {state}"
                )
                item.setData(Qt.ItemDataRole.UserRole, root["id"])
                item.setToolTip(root["path"])
                self.root_list.addItem(item)
                if root["id"] == current:
                    self.root_list.setCurrentItem(item)
            if self.root_list.count() and not self.root_list.currentItem():
                self.root_list.setCurrentRow(0)
            self._root_selection_changed(self.root_list.currentItem(), None)

    def _refresh_root_filters(self) -> None:
        roots = self.repo.roots()
        for combo in (
            getattr(self, "search_root", None),
            getattr(self, "chat_root", None),
            getattr(self, "image_root", None),
        ):
            if combo is None:
                continue
            selected = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("All folders", "")
            for root in roots:
                if not root["enabled"]:
                    continue
                combo.addItem(Path(root["path"]).name, root["id"])
                combo.setItemData(combo.count() - 1, root["path"], Qt.ItemDataRole.ToolTipRole)
            index = combo.findData(selected)
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)

    def _start_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            self.search_count.setText("Type a word or phrase to search indexed content.")
            self.results_list.clear()
            return
        self._search_generation += 1
        generation = self._search_generation
        mode = self.search_mode.currentText()
        if mode != "Keyword" and not self.settings.enabled_text_model:
            self.search_notice.setText(
                "Text model is not enabled. Showing keyword results; download and index the optional model in Settings for semantic search."
            )
            mode = "Keyword"
        else:
            self.search_notice.setText("Local retrieval; no indexed content leaves this device.")
        root_id = self.search_root.currentData()
        worker = SearchWorker(
            self.db_path,
            generation,
            query,
            mode,
            self.search_kind.currentData() or None,
            [root_id] if root_id else [],
            self.settings.enabled_text_model,
            self.model_cache,
        )
        worker.result.connect(self._search_complete)
        worker.failed.connect(self._search_failed)
        worker.finished.connect(lambda: self._job_finished(worker))
        self._start_job(worker)
        self.search_count.setText("Searching…")
        self.results_list.clear()

    def _search_complete(self, generation: int, hits: list) -> None:
        if generation != self._search_generation:
            return
        self._current_hits = hits
        self.results_list.clear()
        for index, hit in enumerate(hits):
            snippet = " ".join(hit.snippet.split())
            item = QListWidgetItem(f"{hit.filename}\n{hit.locator} · {hit.kind}\n{snippet[:230]}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(f"{hit.path}\n{hit.locator}\n{', '.join(hit.reasons)}")
            self.results_list.addItem(item)
        self.search_count.setText(
            f"{len(hits)} results shown. Result ordering uses keyword ranking and, when enabled, reciprocal rank fusion."
        ) if hits else self.search_count.setText(
            "No matching indexed content. Try fewer words or another search mode."
        )

    def _search_failed(self, generation: int, message: str) -> None:
        if generation == self._search_generation:
            self.search_count.setText(
                "Search could not complete. Keyword search remains available."
            )
            logger.warning("Search job failed: %s", message)
            self.statusBar().showMessage(message, 8000)

    def _show_result_preview(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None or index >= len(self._current_hits):
            return
        hit = self._current_hits[index]
        self.selected_hit = hit
        self.preview_title.setText(f"{hit.filename} · {hit.locator}")
        root_path = self.repo.file_root_path(hit.file_id)
        try:
            relative_path = hit.path.relative_to(root_path) if root_path else hit.path.name
        except ValueError:
            relative_path = Path(hit.path.name)
        self.preview_path.setText(f"In indexed folder: {relative_path}")
        self.preview_path.setToolTip(str(hit.path))
        rows = self.repo.preview_segments(hit.file_id)
        content = "\n\n".join(f"[{row['locator']}]\n{row['text']}" for row in rows)[:200_000]
        self.preview_text.setPlainText(content or "No text content is available for preview.")
        query = self.search_input.text().strip()
        if query:
            cursor = self.preview_text.textCursor()
            selections = []
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#765b21" if self.settings.theme == "dark" else "#fff0a6"))
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            while True:
                cursor = self.preview_text.document().find(query, cursor)
                if cursor.isNull():
                    break
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format = fmt
                selections.append(selection)
            self.preview_text.setExtraSelections(selections)
        else:
            self.preview_text.setExtraSelections([])

    def _open_result(self) -> None:
        hit = getattr(self, "selected_hit", None)
        if hit:
            self._open_path(hit.path)

    def _reveal_result(self) -> None:
        hit = getattr(self, "selected_hit", None)
        if hit:
            self._reveal_path(hit.path)

    def _copy_result_path(self) -> None:
        hit = getattr(self, "selected_hit", None)
        if hit:
            QApplication.clipboard().setText(str(hit.path))

    def _image_filters(self) -> dict:
        root_id = self.image_root.currentData()
        recent_days = self.image_recent_days.value()
        return {
            "root_ids": [root_id] if root_id else None,
            "extension": self.image_type.currentData() or None,
            "modified_after_ns": (
                time.time_ns() - recent_days * 24 * 60 * 60 * 1_000_000_000 if recent_days else None
            ),
            "min_width": self.image_min_width.value(),
            "min_height": self.image_min_height.value(),
        }

    def _start_image_worker(self, query: str, clip: bool, offset: int) -> None:
        self._image_generation += 1
        generation = self._image_generation
        if getattr(self, "image_worker", None) and self.image_worker.isRunning():
            self._pending_image_request = (query, clip, offset)
            if offset == 0:
                self.image_list.clear()
                self._image_items.clear()
                self.image_load_more.hide()
            self.image_count.setText("Waiting for the current image query to finish…")
            return
        filters = self._image_filters()
        worker = ImageWorker(
            self.db_path,
            query,
            clip,
            self.model_cache,
            filters["root_ids"],
            filters["extension"],
            filters["modified_after_ns"],
            filters["min_width"],
            filters["min_height"],
            offset,
        )
        worker.result.connect(
            lambda result_offset, values, has_more: self._images_loaded(
                generation, result_offset, values, has_more
            )
        )
        worker.failed.connect(lambda message: self._image_failed(generation, message))
        worker.finished.connect(lambda: self._job_finished(worker))
        self.image_worker = worker
        if offset == 0:
            self.image_list.clear()
            self.image_load_more.hide()
        self._start_job(worker)
        self.image_count.setText(
            "Searching images with CLIP…" if clip else "Loading image catalog…"
        )

    def _image_failed(self, generation: int, message: str) -> None:
        if generation == self._image_generation:
            self.image_count.setText(f"Image catalog error: {message}")

    def _load_images(self, append: bool = False) -> None:
        offset = self.image_list.count() if append else 0
        query = "" if self.image_ai.isChecked() else self.image_query.text().strip()
        self._start_image_worker(query, False, offset)

    def _load_more_images(self) -> None:
        if self.image_ai.isChecked():
            self._search_images(append=True)
        else:
            self._load_images(append=True)

    def _search_images(self, *_args, append: bool = False) -> None:
        offset = self.image_list.count() if append else 0
        if self.image_ai.isChecked():
            if not self.settings.enabled_image_model:
                self.image_count.setText(
                    "CLIP is not ready. Use Settings or the model button to explicitly download and index it."
                )
                self.image_ai.blockSignals(True)
                self.image_ai.setChecked(False)
                self.image_ai.blockSignals(False)
                return
            self._start_image_worker(self.image_query.text().strip(), True, offset)
        else:
            self._start_image_worker(self.image_query.text().strip(), False, offset)

    def _images_loaded(self, generation: int, offset: int, values: list, has_more: bool) -> None:
        if generation != self._image_generation:
            return
        if offset == 0:
            self._image_items.clear()
        for record, thumbnail in values:
            item = QListWidgetItem(record.path.name)
            item.setIcon(QIcon(str(thumbnail)))
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setToolTip(f"{record.path}\n{record.width} × {record.height}")
            self.image_list.addItem(item)
            self._image_items.append((record, thumbnail))
        self.image_load_more.setVisible(has_more)
        self.image_count.setText(
            f"{self.image_list.count()} images shown from the filtered catalog."
            + (" More results are available." if has_more else "")
            if values
            else "No images match this view. Index a folder containing JPG, PNG or WebP images."
        )

    def _selected_image(self):
        item = self.image_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _show_image_preview(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if record is None:
            return
        pixmap = QPixmap(str(record.thumbnail))
        self.image_preview.setPixmap(
            pixmap.scaled(
                self.image_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.image_details.setText(
            f"{record.path.name}\n{record.path}\n{record.width} × {record.height} px · {record.size:,} bytes"
        )

    def _open_image(self) -> None:
        record = self._selected_image()
        if record:
            self._open_path(record.path)

    def _reveal_image(self) -> None:
        record = self._selected_image()
        if record:
            self._reveal_path(record.path)

    def _copy_image_path(self) -> None:
        record = self._selected_image()
        if record:
            QApplication.clipboard().setText(str(record.path))

    def _enable_clip(self) -> None:
        answer = QMessageBox.question(
            self,
            "Enable local CLIP image search",
            "This downloads the optional OpenCLIP ViT-B-32 / laion2b_s34b_b79k checkpoint (about 2.42 GB on its model card) and indexes image vectors on this device. It requires the image-ai extra. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_model_job("image")

    def _enable_text_model(self) -> None:
        answer = QMessageBox.question(
            self,
            "Enable local semantic text search",
            "This downloads sentence-transformers/all-MiniLM-L6-v2 and indexes the extracted text on this device. The model card lists Apache-2.0. The model is English-focused; Sinhala and Tamil semantic quality is not guaranteed. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_model_job("text")

    def _load_duplicates(self) -> None:
        worker = DuplicateWorker(self.db_path)
        worker.result.connect(self._duplicates_loaded)
        worker.failed.connect(
            lambda message: self.duplicate_summary.setText(f"Duplicate analysis failed: {message}")
        )
        worker.finished.connect(lambda: self._job_finished(worker))
        self._start_job(worker)
        self.duplicate_summary.setText("Analyzing indexed files…")

    def _duplicates_loaded(self, exact: list, similar: list) -> None:
        self._duplicate_groups = [*exact, *similar]
        self.exact_list.clear()
        self.similar_list.clear()
        reclaimable = 0
        for index, group in enumerate(exact):
            total = sum(item["size"] for item in group.files)
            reclaimable += max(0, total - group.files[0]["size"])
            item = QListWidgetItem(
                f"Exact group {index + 1} · {len(group.files)} copies · up to {max(0, total - group.files[0]['size']):,} bytes reclaimable estimate"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.exact_list.addItem(item)
        for index, group in enumerate(similar):
            group_index = len(exact) + index
            item = QListWidgetItem(
                f"Similar group {index + 1} · {len(group.files)} images · pHash distance ≤ {group.distance}"
            )
            item.setData(Qt.ItemDataRole.UserRole, group_index)
            self.similar_list.addItem(item)
        self.duplicate_summary.setText(
            f"{len(exact)} exact groups · {len(similar)} similar image groups · {reclaimable:,} bytes possible exact-copy savings estimate. Review only; no cleanup action is available."
        )

    def _select_duplicate_list(self, _index: int) -> None:
        view = self.exact_list if self.duplicate_tabs.currentIndex() == 0 else self.similar_list
        if view.currentItem():
            self._show_duplicate_group(view.currentItem())

    def _show_duplicate_group(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None or index >= len(self._duplicate_groups):
            return
        group = self._duplicate_groups[index]
        paths = "\n".join(f"• {file['path']} ({file['size']:,} bytes)" for file in group.files)
        if group.kind == "exact":
            estimate = max(0, sum(file["size"] for file in group.files) - group.files[0]["size"])
            paths += f"\n\nPossible reclaimable space estimate: {estimate:,} bytes"
        else:
            paths += f"\n\nPerceptual hash distance: {group.distance}. Visual suggestion only."
        self.duplicate_details.setPlainText(paths)

    def _export_duplicates(self) -> None:
        if not self._duplicate_groups:
            QMessageBox.information(self, "Nothing to export", "Analyze the indexed files first.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export duplicate metadata", "filesense-duplicates.csv", "CSV files (*.csv)"
        )
        if not filename:
            return
        try:
            with Path(filename).open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    [
                        "group_type",
                        "group_number",
                        "path",
                        "size_bytes",
                        "modified_ns",
                        "similarity_distance",
                    ]
                )
                for index, group in enumerate(self._duplicate_groups, 1):
                    for item in group.files:
                        writer.writerow(
                            [
                                group.kind,
                                index,
                                item["path"],
                                item["size"],
                                item["mtime_ns"],
                                group.distance or "",
                            ]
                        )
            self.statusBar().showMessage("Duplicate metadata exported.", 5000)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def _check_ollama(self) -> None:
        worker = OllamaCheckWorker()
        worker.result.connect(lambda available, models: self._ollama_state(available, models))
        worker.finished.connect(lambda: self._job_finished(worker))
        self._start_job(worker)
        self.chat_state.setText("Checking only the local 127.0.0.1 Ollama endpoint…")

    def _ollama_state(self, available: bool, models: list[str]) -> None:
        if available:
            self.chat_state.setText(
                "Local Ollama is available. Installed models: "
                + (", ".join(models) or "none found")
            )
        else:
            self.chat_state.setText(
                "Ollama is not responding on this device. Install/start Ollama locally; FileSense AI does not use a hosted service."
            )

    def _ask_files(self) -> None:
        question = self.chat_question.text().strip()
        model = self.chat_model.text().strip()
        if not question or not model:
            self.chat_state.setText(
                "Enter a question and an installed local Ollama model name first."
            )
            return
        self.settings.ollama_model = model
        self.settings_store.save(self.settings)
        self._chat_history.extend([("You", question), ("FileSense AI", "")])
        self._render_chat()
        self.chat_question.clear()
        root_id = self.chat_root.currentData()
        worker = ChatWorker(
            self.db_path,
            model,
            question,
            [root_id] if root_id else None,
            self.settings.enabled_text_model,
            self.model_cache,
        )
        worker.token.connect(self._append_chat_token)
        worker.result.connect(self._chat_complete)
        worker.failed.connect(lambda message: self.chat_transcript.appendPlainText(f"\n{message}"))
        worker.finished.connect(lambda: self._chat_finished(worker))
        self._chat_worker = worker
        self._start_job(worker)
        self.chat_send.setEnabled(False)
        self.chat_stop.setEnabled(True)
        self.chat_state.setText("Retrieving relevant excerpts and querying local Ollama…")

    def _append_chat_token(self, value: str) -> None:
        if self._chat_history and self._chat_history[-1][0] == "FileSense AI":
            self._chat_history[-1] = ("FileSense AI", self._chat_history[-1][1] + value)
        self.chat_transcript.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_transcript.insertPlainText(value)
        self.chat_transcript.ensureCursorVisible()

    def _chat_complete(self, response: str, citations: list, invalid: list) -> None:
        if self._chat_history and self._chat_history[-1][0] == "FileSense AI":
            self._chat_history[-1] = ("FileSense AI", response)
        self._render_chat()
        self.sources_list.clear()
        for citation in citations:
            item = QListWidgetItem(
                f"[{citation.source_id}] {Path(citation.path).name} — {citation.locator}"
            )
            item.setData(Qt.ItemDataRole.UserRole, citation)
            item.setToolTip(f"{citation.path}\n{citation.excerpt}")
            self.sources_list.addItem(item)
        self.sources_label.setText(
            (
                "Double-click a verified source to open it."
                if citations
                else "No verified sources for this answer."
            )
            + (f" Removed unverified references: {', '.join(invalid)}" if invalid else "")
        )
        self._chat_citations = {c.source_id: c for c in citations}
        self.sources_label.setToolTip(
            "\n".join(f"{c.source_id}: {c.path} ({c.locator})\n{c.excerpt}" for c in citations)
        )
        self.chat_state.setText(
            "Answers may be inaccurate. Only validated source IDs are shown as sources."
        )

    def _chat_finished(self, worker) -> None:
        self.chat_send.setEnabled(True)
        self.chat_stop.setEnabled(False)
        self._job_finished(worker)

    def _stop_chat(self) -> None:
        if self._chat_worker:
            self._chat_worker.cancel()
            self.chat_state.setText("Stopping after the current local response chunk…")

    def _clear_chat(self) -> None:
        self.chat_transcript.clear()
        self._chat_history.clear()
        self.sources_list.clear()
        self.sources_label.setText("Verified sources appear below after each answer.")
        self._chat_citations.clear()

    def _render_chat(self) -> None:
        self.chat_transcript.setPlainText(
            "\n\n".join(f"{role}: {text}" for role, text in self._chat_history)
        )
        self.chat_transcript.moveCursor(QTextCursor.MoveOperation.End)

    def _open_citation(self, item: QListWidgetItem) -> None:
        citation = item.data(Qt.ItemDataRole.UserRole)
        if citation:
            self._open_path(Path(citation.path))

    def _set_theme(self, theme: str) -> None:
        self.settings.theme = theme
        self.settings_store.save(self.settings)
        apply_theme(QApplication.instance(), theme)

    def _save_preferences(self, _value: int | None = None) -> None:
        self.settings.max_file_size_mb = self.max_size.value()
        self.settings.max_document_chars = self.max_chars.value()
        self.settings.max_indexed_files = self.max_files.value()
        self.settings.excluded_patterns = [
            value.strip() for value in self.exclusions_input.text().split(",") if value.strip()
        ][:100]
        self.repo.update_root_exclusions(self.settings.excluded_patterns)
        self.settings_store.save(self.settings)

    def _choose_model_cache(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose local model storage", str(self.model_cache)
        )
        if not folder:
            return
        self.model_cache = Path(folder)
        self.model_cache.mkdir(parents=True, exist_ok=True)
        self.settings.model_cache_path = str(self.model_cache)
        self.model_cache_label.setText(str(self.model_cache))
        self.settings_store.save(self.settings)

    def _update_model_state(self) -> None:
        semantic_cached = self.repo.has_text_embeddings("sentence-transformers/all-MiniLM-L6-v2")
        clip_cached = self.repo.has_image_embeddings("ViT-B-32/laion2b_s34b_b79k")
        self.text_model_state.setText(
            f"Text: {('enabled' if semantic_cached and self.settings.enabled_text_model else 'download required / not indexed')} · sentence-transformers/all-MiniLM-L6-v2 · English quality only"
        )
        self.clip_model_state.setText(
            f"Images: {('enabled' if clip_cached and self.settings.enabled_image_model else 'download required / not indexed')} · OpenCLIP ViT-B-32, laion2b_s34b_b79k"
        )
        self.search_notice.setText(
            "Semantic search is enabled locally."
            if self.settings.enabled_text_model
            else "No models are loaded. Keyword mode is ready."
        )

    def _run_model_job(self, kind: str) -> None:
        worker = ModelWorker(self.db_path, kind, self.model_cache)
        worker.progress.connect(lambda message: self.statusBar().showMessage(message))
        worker.result.connect(lambda message: self._model_complete(kind, message))
        worker.failed.connect(
            lambda message: QMessageBox.warning(
                self,
                "Model setup failed",
                f"{message}\n\nCheck that the corresponding optional dependencies are installed. No model is downloaded automatically on startup.",
            )
        )
        worker.finished.connect(lambda: self._job_finished(worker))
        if kind == "text":
            self.text_model_worker = worker
        else:
            self.clip_model_worker = worker
        self._start_job(worker)
        if kind == "text":
            self.text_model_button.setEnabled(False)
        else:
            self.clip_model_settings_button.setEnabled(False)
            self.enable_clip_button.setEnabled(False)

    def _model_complete(self, kind: str, message: str) -> None:
        if kind == "text":
            self.settings.enabled_text_model = True
        elif kind == "image":
            self.settings.enabled_image_model = True
            self.image_ai.setChecked(True)
        self.settings_store.save(self.settings)
        self._update_model_state()
        self.statusBar().showMessage(message, 10000)

    def _reset_index(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Clear local index",
            "This removes indexed roots, extracted text, search records and embedding references from FileSense AI's database. It does not delete your original files. This action cannot be undone.",
            QMessageBox.StandardButton.Clear | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Clear:
            self.database.reset_index()
            from filesense_ai.images.catalog import ImageCatalog

            ImageCatalog(self.database.connection).prune_orphans()
            self.settings.enabled_text_model = False
            self.settings.enabled_image_model = False
            self.settings_store.save(self.settings)
            self._refresh_overview()
            self._refresh_root_filters()
            self._update_model_state()
            self.statusBar().showMessage(
                "Local index cleared. Source files were not changed.", 6000
            )

    def _open_path(self, path: Path) -> None:
        if not path.is_file():
            self.statusBar().showMessage("That source file is no longer available.", 5000)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _reveal_path(self, path: Path) -> None:
        if not path.exists():
            self.statusBar().showMessage("That source file is no longer available.", 5000)
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer.exe", "/select,", str(path)], close_fds=True)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _escape(self) -> None:
        if getattr(self, "current_index_worker", None) and self.current_index_worker.isRunning():
            self._cancel_index()
        elif self.search_input.hasFocus() and self.search_input.text():
            self.search_input.clear()

    def _start_job(self, worker) -> None:
        self.jobs.append(worker)
        worker.start()

    def _job_finished(self, worker) -> None:
        if worker in self.jobs:
            self.jobs.remove(worker)
        if worker is getattr(self, "current_index_worker", None):
            self.index_progress.hide()
            self.index_button.setEnabled(True)
            self.cancel_index_button.setEnabled(False)
            self.job_label.setText("Ready")
        if worker is getattr(self, "text_model_worker", None):
            self.text_model_button.setEnabled(True)
        if worker is getattr(self, "clip_model_worker", None):
            self.clip_model_settings_button.setEnabled(True)
            self.enable_clip_button.setEnabled(True)
            if self.settings.enabled_image_model and self.stack.currentIndex() == NAVIGATION.index(
                "Images"
            ):
                QTimer.singleShot(0, self._search_images)
        if worker is getattr(self, "image_worker", None) and self._pending_image_request:
            request = self._pending_image_request
            self._pending_image_request = None
            QTimer.singleShot(0, lambda: self._start_image_worker(*request))
        self._update_model_state()

    def _job_failed(self, message: str) -> None:
        logger.warning("Background operation failed: %s", message)
        QMessageBox.warning(self, "Operation failed", message)
        self.statusBar().showMessage(
            "The operation failed. See local logs for technical details.", 6000
        )


class OllamaCheckWorker(QThread):
    result = Signal(bool, object)

    def run(self) -> None:
        try:
            from filesense_ai.chat.ollama_client import OllamaClient

            client = OllamaClient()
            available = client.available()
            self.result.emit(available, client.models() if available else [])
        except Exception:
            self.result.emit(False, [])
