"""The main window: pages, the page itself and the proofreading panel."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QSplitter,
                               QStackedWidget, QToolBar, QVBoxLayout, QWidget)

from .. import export
from ..pipeline import IMAGE_SUFFIXES, Document, PageResult
from . import icons, theme as themes
from .export_dialog import ExportDialog
from .i18n import language, tr
from .pageview import PageView, to_pixmap
from .proofread import ProofreadPanel
from .worker import Reader

THUMB = QSize(96, 132)


def default_checkpoint() -> Path | None:
    """$COPTICOCR_MODEL, else the newest ``models/*/best.pt`` next to the program."""
    if os.environ.get("COPTICOCR_MODEL"):
        return Path(os.environ["COPTICOCR_MODEL"])
    for root in Path(__file__).resolve().parents:
        found = sorted((root / "models").glob("*/best.pt"), key=lambda p: p.stat().st_mtime)
        if found:
            return found[-1]
    return None


class MainWindow(QMainWindow):
    def __init__(self, coptic_family: str):
        super().__init__()
        self.settings = QSettings()
        self.theme = themes.DARK if self.settings.value("dark", False, bool) else themes.LIGHT
        self.coptic_font = QFont(coptic_family, 16)
        self.coptic_family = coptic_family
        self.doc: Document | None = None
        self.results: list[PageResult | None] = []
        self.current = -1
        self.reader: Reader | None = None
        self.pending: set[int] = set()
        self.batch_total = 0
        self.device = ""
        self.checkpoint = Path(self.settings.value("model", "")) if self.settings.value("model") else None
        if self.checkpoint is None or not self.checkpoint.exists():
            self.checkpoint = default_checkpoint()

        self.setWindowTitle(f"{tr('app_name')} — {tr('tagline')}")
        self.setAcceptDrops(True)
        self.resize(1440, 900)
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_body()
        self._build_status()
        self._apply_theme()
        self._update_state()
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    # Construction -------------------------------------------------------
    def _action(self, key: str, slot, shortcut=None, icon_name: str | None = None, tip: str | None = None,
                checkable: bool = False) -> QAction:
        action = QAction(tr(key), self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if tip:
            action.setToolTip(tr(tip))
        action.setCheckable(checkable)
        action.icon_name = icon_name
        return action

    def _build_actions(self) -> None:
        self.open_action = self._action("open", self.open_dialog, QKeySequence.Open, "open", "open_tip")
        self.read_action = self._action("read_page", self.read_current, "Ctrl+R", "read", "read_page_tip")
        self.read_all_action = self._action("read_all", self.read_all, "Ctrl+Shift+R", "read_all", "read_all_tip")
        self.stop_action = self._action("stop", self.stop_reading, "Esc", "stop")
        self.export_action = self._action("export", self.export, "Ctrl+E", "export", "export_tip")
        self.zoom_in_action = self._action("zoom_in", lambda: self.view.zoom(1.2), QKeySequence.ZoomIn, "zoom_in")
        self.zoom_out_action = self._action("zoom_out", lambda: self.view.zoom(1 / 1.2), QKeySequence.ZoomOut,
                                            "zoom_out")
        self.fit_action = self._action("fit_width", lambda: self.view.fit_width(), "Ctrl+0", "fit")
        self.dark_action = self._action("dark_mode", self.toggle_dark, "Ctrl+Shift+D", "moon", checkable=True)
        self.dark_action.setChecked(self.theme.dark)
        self.keys_action = self._action("keyboard", self.toggle_keys, None, "keyboard", "keyboard_tip",
                                        checkable=True)
        self.keys_action.setChecked(self.settings.value("legacy_keys", True, bool))
        self.prev_action = self._action("page", lambda: self.go(self.current - 1), QKeySequence.MoveToPreviousPage)
        self.next_action = self._action("page", lambda: self.go(self.current + 1), QKeySequence.MoveToNextPage)
        self.addActions([self.prev_action, self.next_action])

    def _build_menus(self) -> None:
        menu = self.menuBar().addMenu(tr("file"))
        menu.addActions([self.open_action, self.export_action])
        menu.addSeparator()
        menu.addAction(tr("quit"), QKeySequence.Quit, self.close)
        menu = self.menuBar().addMenu(tr("view"))
        menu.addActions([self.zoom_in_action, self.zoom_out_action, self.fit_action])
        menu.addSeparator()
        menu.addAction(self.dark_action)
        menu = self.menuBar().addMenu(tr("tools"))
        menu.addActions([self.read_action, self.read_all_action, self.stop_action])
        menu.addSeparator()
        menu.addAction(self.keys_action)
        menu.addAction(tr("choose_model"), self.choose_model)
        self.cpu_action = menu.addAction(tr("use_cpu"))
        self.cpu_action.setCheckable(True)
        self.cpu_action.setChecked(self.settings.value("cpu", False, bool))
        self.cpu_action.toggled.connect(self._set_cpu)
        menu.addSeparator()
        menu.addAction(tr("language"), self.switch_language)
        menu = self.menuBar().addMenu(tr("help"))
        menu.addAction(tr("about"), lambda: QMessageBox.about(self, tr("about"), tr("about_text")))

    def _build_toolbar(self) -> None:
        bar = QToolBar()
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setIconSize(QSize(20, 20))
        bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        bar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(bar)
        bar.addAction(self.open_action)
        bar.addSeparator()
        bar.addAction(self.read_action)
        bar.widgetForAction(self.read_action).setObjectName("primary")
        bar.addAction(self.read_all_action)
        bar.addAction(self.stop_action)
        bar.addSeparator()
        bar.addAction(self.export_action)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)
        for action in (self.zoom_out_action, self.zoom_in_action, self.fit_action, self.keys_action,
                       self.dark_action):
            bar.addAction(action)
            bar.widgetForAction(action).setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.toolbar = bar

    def _build_body(self) -> None:
        self.pages = QListWidget()
        self.pages.setObjectName("pages")
        self.pages.setViewMode(QListWidget.IconMode)
        self.pages.setFlow(QListWidget.TopToBottom)
        self.pages.setWrapping(False)
        self.pages.setMovement(QListWidget.Static)
        self.pages.setIconSize(THUMB)
        self.pages.setUniformItemSizes(True)
        self.pages.setGridSize(QSize(THUMB.width() + 28, THUMB.height() + 40))
        self.pages.setMinimumWidth(THUMB.width() + 44)
        self.pages.setMaximumWidth(THUMB.width() + 60)
        self.pages.currentRowChanged.connect(self.go)
        self.pages.verticalScrollBar().valueChanged.connect(lambda _: self._thumb_timer.start(0))
        self._thumb_timer = QTimer(self, singleShot=True, interval=0, timeout=self._load_thumbnails)

        self.view = PageView(self.theme)
        self.view.line_clicked.connect(self._line_clicked_on_page)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._welcome())
        self.stack.addWidget(self.view)

        self.panel = ProofreadPanel(self.theme, self.coptic_font)
        self.panel.set_legacy_keys(self.keys_action.isChecked())
        self.panel.line_selected.connect(lambda i: self.view.select_line(i))
        self.panel.line_edited.connect(lambda _: self.view.set_result(self.results[self.current]))

        splitter = QSplitter()
        splitter.addWidget(self.pages)
        splitter.addWidget(self.stack)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([150, 760, 520])
        splitter.setCollapsible(1, False)
        self.setCentralWidget(splitter)
        self.pages.hide()  # shown once a book is open
        self.panel.hide()

    def _welcome(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(48, 48, 48, 48)
        zone = QFrame()
        zone.setObjectName("dropZone")
        inner = QVBoxLayout(zone)
        inner.setAlignment(Qt.AlignCenter)
        inner.setSpacing(14)
        self.welcome_icon = QLabel()
        self.welcome_icon.setAlignment(Qt.AlignCenter)
        inner.addWidget(self.welcome_icon)
        title = QLabel(tr("welcome_title"))
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        inner.addWidget(title)
        body = QLabel(tr("welcome_body"))
        body.setObjectName("welcomeBody")
        body.setAlignment(Qt.AlignCenter)
        inner.addWidget(body)
        button = QPushButton(tr("open"))
        button.setObjectName("primary")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.open_dialog)
        inner.addWidget(button, alignment=Qt.AlignCenter)
        outer.addWidget(zone)
        return page

    def _build_status(self) -> None:
        status = self.statusBar()
        status.setSizeGripEnabled(False)
        status.setContentsMargins(10, 0, 10, 0)
        self.page_label = QLabel()
        self.model_label = QLabel()
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.progress_label = QLabel()
        status.addWidget(self.page_label)
        status.addWidget(self.progress_label)
        status.addWidget(self.progress)
        status.addPermanentWidget(self.model_label)

    # Theme --------------------------------------------------------------
    def _apply_theme(self) -> None:
        themes.apply(QApplication.instance(), self.theme)
        for action in self.findChildren(QAction):
            name = getattr(action, "icon_name", None)
            if name:
                action.setIcon(icons.icon(name, self.theme.text))
        primary = self.toolbar.widgetForAction(self.read_action)
        primary.setIcon(icons.icon("read", self.theme.on_accent))
        self.setWindowIcon(icons.app_icon(self.theme.accent, self.coptic_family))
        self.welcome_icon.setPixmap(icons.app_icon(self.theme.accent, self.coptic_family).pixmap(88, 88))
        self.view.set_theme(self.theme)
        self.panel.set_theme(self.theme)

    def toggle_dark(self, on: bool) -> None:
        self.theme = themes.DARK if on else themes.LIGHT
        self.dark_action.setChecked(on)
        self.settings.setValue("dark", on)
        self._apply_theme()

    def toggle_keys(self, on: bool) -> None:
        self.settings.setValue("legacy_keys", on)
        self.panel.set_legacy_keys(on)

    def switch_language(self) -> None:
        self.settings.setValue("language", "en" if language() == "ar" else "ar")
        QMessageBox.information(self, tr("app_name"), tr("language_restart"))

    # Opening ------------------------------------------------------------
    def open_dialog(self) -> None:
        start = self.settings.value("last_dir", str(Path.home()))
        paths, _ = QFileDialog.getOpenFileNames(self, tr("open"), start, tr("open_filter"))
        if paths:
            self.open_paths([Path(p) for p in paths])

    def open_paths(self, paths: list[Path]) -> None:
        paths = [p for p in paths if p.suffix.lower() == ".pdf" or p.suffix.lower() in IMAGE_SUFFIXES]
        if not paths:
            return
        self.settings.setValue("last_dir", str(paths[0].parent))
        self._stop_reader()
        if self.doc is not None:
            self.doc.close()
        self.doc = Document(sorted(paths) if len(paths) > 1 else paths)
        self.results = [None] * len(self.doc)
        self.pending.clear()
        self.batch_total = 0
        self.pages.clear()
        blank = QPixmap(THUMB)
        blank.fill(Qt.white)
        for i in range(len(self.doc)):
            item = QListWidgetItem(QIcon(blank), str(i + 1))
            item.setData(Qt.UserRole, False)  # thumbnail loaded?
            item.setTextAlignment(Qt.AlignHCenter)
            self.pages.addItem(item)
        self.stack.setCurrentWidget(self.view)
        self.pages.show()
        self.panel.show()
        self.current = -1
        self.pages.setCurrentRow(0)
        self._thumb_timer.start(0)
        self._update_state()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        self.open_paths([Path(url.toLocalFile()) for url in event.mimeData().urls()])

    def _load_thumbnails(self) -> None:
        """Render thumbnails of the visible pages, a few at a time."""
        if self.doc is None:
            return
        viewport = self.pages.viewport().rect()
        loaded = 0
        for row in range(self.pages.count()):
            item = self.pages.item(row)
            if item.data(Qt.UserRole) or not self.pages.visualItemRect(item).intersects(viewport):
                continue
            image = self.doc.page_image(row)
            image.thumbnail((THUMB.width() * 2, THUMB.height() * 2))
            item.setIcon(QIcon(to_pixmap(image)))
            item.setData(Qt.UserRole, True)
            loaded += 1
            if loaded == 3:
                self._thumb_timer.start(0)  # keep the window responsive between batches
                return

    # Navigation ---------------------------------------------------------
    def go(self, index: int) -> None:
        if self.doc is None or not 0 <= index < len(self.doc) or index == self.current:
            return
        self.current = index
        if self.pages.currentRow() != index:
            self.pages.setCurrentRow(index)
        self.page_image = self.doc.page_image(index)
        self.view.show_page(self.page_image, self.results[index])
        self.panel.set_page(self.page_image, self.results[index])
        self._update_state()

    def _line_clicked_on_page(self, index: int) -> None:
        self.view.select_line(index, scroll=False)
        self.panel.select(index)

    # Reading ------------------------------------------------------------
    def _ensure_reader(self) -> bool:
        if self.reader is not None:
            return True
        if self.checkpoint is None or not self.checkpoint.exists():
            QMessageBox.warning(self, tr("app_name"), tr("no_model"))
            return False
        device = "cpu" if self.cpu_action.isChecked() else os.environ.get("COPTICOCR_DEVICE")
        self.reader = Reader(self.doc.paths, self.checkpoint, device)
        self.reader.ready.connect(self._reader_ready)
        self.reader.failed_to_start.connect(self._reader_failed)
        self.reader.page_read.connect(self._page_read)
        self.reader.page_failed.connect(
            lambda i, e: self.statusBar().showMessage(tr("read_failed", i + 1, e), 8000))
        self.model_label.setText(tr("loading_model"))
        self.reader.start()
        return True

    def _reader_ready(self, device: str) -> None:
        self.device = "GPU" if device.startswith("cuda") else "CPU"
        self.model_label.setText(tr("model_info", self.checkpoint.parent.name, self.device))

    def _reader_failed(self, error: str) -> None:
        self.reader = None
        self.pending.clear()
        self.model_label.setText("")
        QMessageBox.critical(self, tr("app_name"), tr("model_failed", error))
        self._update_state()

    def _queue(self, indices: list[int]) -> None:
        indices = [i for i in indices if i not in self.pending]
        if not indices or not self._ensure_reader():
            return
        if not self.pending:
            self.batch_total = 0
        self.pending.update(indices)
        self.batch_total += len(indices)
        self.reader.submit(indices)
        self._update_state()

    def read_current(self) -> None:
        if self.current >= 0:
            self._queue([self.current])

    def read_all(self) -> None:
        if self.doc is not None:
            todo = [i for i, r in enumerate(self.results) if r is None]
            # Start with the page on screen, then go on from there.
            todo.sort(key=lambda i: (i < self.current, i))
            self._queue(todo)

    def stop_reading(self) -> None:
        if self.reader is not None and self.pending:
            self.reader.cancel()
            self.pending.clear()
            self._update_state()

    def _page_read(self, index: int, result: PageResult) -> None:
        if index not in self.pending:
            return  # cancelled while it was being read
        self.pending.discard(index)
        self.results[index] = result
        item = self.pages.item(index)
        if item is not None:
            item.setText(f"✓ {index + 1}")
        if index == self.current:
            self.view.set_result(result)
            self.panel.set_page(self.page_image, result)
        self._update_state()

    def _stop_reader(self) -> None:
        if self.reader is not None:
            self.reader.stop()
            self.reader = None
            self.pending.clear()

    def _set_cpu(self, on: bool) -> None:
        self.settings.setValue("cpu", on)
        self._stop_reader()  # the next read starts the model on the chosen device
        self._update_state()

    def choose_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("choose_model"), str(self.checkpoint or Path.home()),
                                              "Model (*.pt)")
        if path:
            self.checkpoint = Path(path)
            self.settings.setValue("model", path)
            self._stop_reader()
            self._update_state()

    # Export -------------------------------------------------------------
    def export(self) -> None:
        read = sum(r is not None for r in self.results)
        if not read:
            QMessageBox.information(self, tr("app_name"), tr("nothing_to_export"))
            return
        dialog = ExportDialog(self, read)
        if dialog.exec() != ExportDialog.Accepted:
            return
        choice = dialog.choice()
        results = list(self.results)
        if choice.current_page_only:
            results = [r if i == self.current else None for i, r in enumerate(results)]
        start = Path(self.settings.value("last_dir", str(Path.home()))) / f"{self.doc.name}.{choice.format}"
        path, _ = QFileDialog.getSaveFileName(self, tr("export"), str(start), choice.file_filter)
        if not path:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if choice.format == "pdf":
                export.to_searchable_pdf(self.doc, results, Path(path))
            elif choice.format == "docx":
                export.to_docx(results, Path(path), choice.coptic_font)
            else:
                export.to_text(results, Path(path))
        except Exception as error:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("app_name"), tr("save_failed", error))
            return
        QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(tr("saved", path), 8000)

    # State --------------------------------------------------------------
    def _update_state(self) -> None:
        has_doc = self.doc is not None
        busy = bool(self.pending)
        self.read_action.setEnabled(has_doc and self.current not in self.pending)
        self.read_all_action.setEnabled(has_doc and any(r is None for r in self.results))
        self.stop_action.setVisible(busy)
        self.export_action.setEnabled(any(r is not None for r in self.results))
        for action in (self.zoom_in_action, self.zoom_out_action, self.fit_action):
            action.setEnabled(has_doc)
        if has_doc:
            read = sum(r is not None for r in self.results)
            self.page_label.setText(f"{tr('page_of', self.current + 1, len(self.doc))}  ·  "
                                    f"{tr('pages_read', read)}")
        else:
            self.page_label.setText("")
        if busy:
            done = self.batch_total - len(self.pending)
            self.progress.setMaximum(self.batch_total)
            self.progress.setValue(done)
            self.progress_label.setText(tr("reading", done + 1, self.batch_total))
        self.progress.setVisible(busy)
        self.progress_label.setVisible(busy)
        if self.reader is None and self.checkpoint is not None:
            self.model_label.setText(tr("model_info", self.checkpoint.parent.name,
                                        "CPU" if self.cpu_action.isChecked() else "auto"))
        elif self.checkpoint is None:
            self.model_label.setText(tr("no_model"))

    def closeEvent(self, event) -> None:
        if self.pending and QMessageBox.question(self, tr("app_name"), tr("unsaved_quit")) != QMessageBox.Yes:
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self._stop_reader()
        if self.doc is not None:
            self.doc.close()
        super().closeEvent(event)
