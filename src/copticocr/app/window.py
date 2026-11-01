"""The main window: pages, the page itself and the proofreading panel."""

from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar, QProgressDialog,
                               QPushButton, QSplitter, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import book, enhance, export
from ..pipeline import IMAGE_SUFFIXES, Document, PageResult
from . import chrome, icons, theme as themes
from .export_dialog import ExportDialog
from .i18n import language, tr
from .pageview import PageView, to_pixmap
from .proofread import ProofreadPanel
from .worker import Job, Reader

THUMB = QSize(96, 132)


def typeset_preview(image, result: PageResult):
    """The page as the typeset PDF shows it, at the scan's pixel size."""
    import pymupdf
    from PIL import Image

    with pymupdf.open() as out:
        page = export.typeset_page(out, image, result, (image.width, image.height))
        pix = page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)
        return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def default_checkpoint(script: str = "coptic") -> Path | None:
    """$COPTICOCR_MODEL (or $COPTICOCR_ARABIC_MODEL), else the newest ``models/<script>-*/best.pt``."""
    variable = "COPTICOCR_MODEL" if script == "coptic" else "COPTICOCR_ARABIC_MODEL"
    if os.environ.get(variable):
        return Path(os.environ[variable])
    for root in Path(__file__).resolve().parents:
        found = sorted((root / "models").glob(f"{script}-*/best.pt"), key=lambda p: p.stat().st_mtime)
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
        self._build_frame()
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
        self.converted_action = self._action("converted", lambda _: self._view_mode(self.converted_action), "Ctrl+T",
                                             "type", "converted_tip", checkable=True)
        self.enhanced_action = self._action("enhanced", lambda _: self._view_mode(self.enhanced_action), "Ctrl+H",
                                            "wand", "enhanced_tip", checkable=True)
        self._enhanced: dict[tuple[int, int], object] = {}  # (page, level) -> cleaned page, for the view
        self.dark_action = self._action("dark_mode", self.toggle_dark, "Ctrl+Shift+D", "moon", checkable=True)
        self.dark_action.setChecked(self.theme.dark)
        self.enhance_level = int(self.settings.value("enhance_level", 2))
        self.keys_action = self._action("keyboard", self.toggle_keys, None, "keyboard", "keyboard_tip",
                                        checkable=True)
        self.keys_action.setChecked(self.settings.value("legacy_keys", True, bool))
        self.prev_action = self._action("page", lambda: self.go(self.current - 1), QKeySequence.MoveToPreviousPage)
        self.next_action = self._action("page", lambda: self.go(self.current + 1), QKeySequence.MoveToNextPage)
        self.addActions([self.prev_action, self.next_action])

    def _build_menus(self) -> None:
        """The "more" menu: settings and rarely used commands. Shortcuts live on the window itself."""
        menu = QMenu(self)
        menu.addAction(self.dark_action)
        menu.addAction(self.keys_action)
        levels = menu.addMenu(tr("enhance_level"))
        group = QActionGroup(self)
        self.level_actions = []
        for number in (1, 2, 3):
            action = levels.addAction(tr(f"level_{number}"))
            action.setCheckable(True)
            action.setChecked(number == self.enhance_level)
            action.triggered.connect(lambda _=False, n=number: self._set_level(n))
            group.addAction(action)
            self.level_actions.append(action)
        self.guide_action = menu.addAction(tr("show_guide"))
        self.guide_action.setCheckable(True)
        self.guide_action.setChecked(self.settings.value("guide", True, bool))
        self.guide_action.toggled.connect(self._set_guide)
        menu.addSeparator()
        menu.addAction(tr("choose_model"), self.choose_model)
        self.cpu_action = menu.addAction(tr("use_cpu"))
        self.cpu_action.setCheckable(True)
        self.cpu_action.setChecked(self.settings.value("cpu", False, bool))
        self.cpu_action.toggled.connect(self._set_cpu)
        menu.addSeparator()
        menu.addAction(tr("language"), self.switch_language)
        menu.addAction(tr("about"), lambda: QMessageBox.about(self, tr("about"), tr("about_text")))
        menu.addSeparator()
        menu.addAction(tr("quit"), QKeySequence.Quit, self.close)
        self.more_menu = menu
        self.addActions([self.open_action, self.read_action, self.read_all_action, self.stop_action,
                         self.export_action, self.zoom_in_action, self.zoom_out_action, self.fit_action,
                         self.converted_action, self.enhanced_action, self.dark_action])

    def _button(self, style: str, action: QAction) -> QPushButton:
        """A push button that stands for ``action`` and follows its state."""
        button = QPushButton(action.text())
        button.setObjectName(style)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(action.toolTip())
        button.clicked.connect(action.trigger)
        button.action_icon = action.icon_name
        action.changed.connect(lambda: (button.setEnabled(action.isEnabled()), button.setVisible(action.isVisible())))
        return button

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(64)
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 0, 14, 0)
        row.setSpacing(8)
        self.logo = QLabel()
        row.addWidget(self.logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.setContentsMargins(4, 0, 0, 0)
        brand = QLabel(tr("app_name"))
        brand.setObjectName("brand")
        self.doc_name = QLabel(tr("tagline"))
        self.doc_name.setObjectName("docName")
        self.doc_name.setMaximumWidth(220)  # a long file name must not widen the window
        names.addStretch()
        names.addWidget(brand)
        names.addWidget(self.doc_name)
        names.addStretch()
        row.addLayout(names)
        row.addSpacing(6)
        self.open_button = self._button("ghost", self.open_action)
        row.addWidget(self.open_button)
        row.addWidget(chrome.stretch())

        # The work in order: read, check, export. The step to take next stands out.
        self.stepper = chrome.Stepper([tr("read_page"), tr("review_step"), tr("export")], tr("read_all_short"))
        self.stepper.steps[0].clicked.connect(self.read_current)
        self.stepper.extra.clicked.connect(self.read_all)
        self.stepper.extra.setToolTip(tr("read_all_tip"))
        self.stepper.steps[1].clicked.connect(self._start_review)
        self.stepper.steps[2].clicked.connect(self.export)
        self.stepper.steps[0].setToolTip(tr("read_page_tip"))
        self.stepper.steps[1].setToolTip(tr("review_tip"))
        self.stepper.steps[2].setToolTip(tr("export_tip"))
        row.addWidget(self.stepper)

        self.busy = QFrame()
        self.busy.setObjectName("busy")
        busy_row = QHBoxLayout(self.busy)
        busy_row.setContentsMargins(12, 4, 4, 4)
        busy_row.setSpacing(6)
        self.busy_spinner = chrome.Spinner(14)
        self.busy_text = QLabel()
        self.busy_text.setObjectName("busyText")
        self.stop_button = chrome.tool_button("stopButton", tr("stop"))
        self.stop_button.clicked.connect(self.stop_action.trigger)
        busy_row.addWidget(self.busy_spinner)
        busy_row.addWidget(self.busy_text)
        busy_row.addWidget(self.stop_button)
        self.busy.hide()
        row.addWidget(self.busy)
        row.addWidget(chrome.stretch())

        self.view_switch = chrome.Segmented([tr("original"), tr("converted"), tr("enhanced")])
        self.view_switch.chosen.connect(self._view_chosen)
        self.view_switch.buttons[1].setToolTip(tr("converted_tip"))
        self.view_switch.buttons[2].setToolTip(tr("enhanced_tip"))
        row.addWidget(self.view_switch)
        self.more_button = QPushButton(tr("settings"))
        self.more_button.setObjectName("ghost")
        self.more_button.setCursor(Qt.PointingHandCursor)
        self.more_button.setMenu(self.more_menu)
        row.addWidget(self.more_button)
        self.header_buttons = [self.open_button]
        return header

    def _build_body(self) -> QWidget:
        self.pages = QListWidget()
        self.pages.setObjectName("pages")
        self.pages.setViewMode(QListWidget.IconMode)
        self.pages.setFlow(QListWidget.TopToBottom)
        self.pages.setWrapping(False)
        self.pages.setMovement(QListWidget.Static)
        self.pages.setIconSize(THUMB)
        self.pages.setUniformItemSizes(True)
        self.pages.setGridSize(QSize(THUMB.width() + 28, THUMB.height() + 40))
        self.pages.currentRowChanged.connect(self.go)
        self.pages.verticalScrollBar().valueChanged.connect(lambda _: self._thumb_timer.start(0))
        self._thumb_timer = QTimer(self, singleShot=True, interval=0, timeout=self._load_thumbnails)
        self.pages_panel = QFrame()
        self.pages_panel.setObjectName("sidePanel")
        self.pages_panel.setFixedWidth(THUMB.width() + 72)
        column = QVBoxLayout(self.pages_panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.pages_header = chrome.PanelHeader(tr("pages"))
        column.addWidget(self.pages_header)
        column.addWidget(self.pages)

        self.view = PageView(self.theme)
        self.view.line_clicked.connect(self._line_clicked_on_page)
        self.view.zoomed.connect(lambda percent: self.floating.zoom.setText(f"{percent}%"))
        self.stack = QStackedWidget()
        self.stack.setObjectName("stack")
        self.stack.addWidget(self._welcome())
        self.stack.addWidget(self.view)
        self.floating = chrome.FloatingBar(tr("enhance_short"), tr("enhance_more"))
        self.floating.level.level_chosen.connect(self._set_level)
        self.floating.level.more.connect(self._enhance_more)
        self.toast = chrome.Toast()
        self.coach = chrome.CoachCard()
        self.coach.close.clicked.connect(lambda: self.guide_action.setChecked(False))
        self._reviewed = self._exported = False
        self.floating.previous.clicked.connect(lambda: self.go(self.current - 1))
        self.floating.next.clicked.connect(lambda: self.go(self.current + 1))
        self.floating.zoom_in.clicked.connect(self.zoom_in_action.trigger)
        self.floating.zoom_out.clicked.connect(self.zoom_out_action.trigger)
        self.floating.fit.clicked.connect(self.fit_action.trigger)
        for button, key in ((self.floating.previous, "previous_page"), (self.floating.next, "next_page"),
                            (self.floating.zoom_in, "zoom_in"), (self.floating.zoom_out, "zoom_out"),
                            (self.floating.fit, "fit_width")):
            button.setToolTip(tr(key))
        self.floating.hide()
        canvas = chrome.Canvas(self.stack, self.floating, self.toast)

        self.panel = ProofreadPanel(self.theme, self.coptic_font)
        self.panel.set_legacy_keys(self.keys_action.isChecked())
        self.panel.line_selected.connect(lambda i: self.view.select_line(i))
        self.panel.line_edited.connect(lambda _: self._refresh_timer.start())
        # Re-typeset the page shortly after the user stops typing.
        self._refresh_timer = QTimer(self, singleShot=True, interval=500, timeout=self._show_current)

        splitter = QSplitter()
        splitter.addWidget(self.pages_panel)
        splitter.addWidget(canvas)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([170, 760, 500])
        splitter.setCollapsible(1, False)
        self.pages_panel.hide()  # shown once a book is open
        self.panel.hide()
        return splitter

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("footer")
        footer.setFixedHeight(32)
        row = QHBoxLayout(footer)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(6)
        row.addStretch(1)
        self.page_chip, self.read_chip, self.model_chip = QLabel(), QLabel(), QLabel()
        for chip in (self.page_chip, self.read_chip, self.model_chip):
            chip.setObjectName("chip")
            row.addWidget(chip)

        return footer

    def notify(self, text: str, ms: int = 4500) -> None:
        """An event (a page read, a file saved) as a message fading in and out over the page."""
        self.toast.show_message(text, min(ms, 4500))

    def _build_frame(self) -> None:
        root = QWidget()
        column = QVBoxLayout(root)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header())
        self.line = QProgressBar()
        self.line.setObjectName("line")
        self.line.setTextVisible(False)
        self.line.setFixedHeight(3)
        self.line.hide()
        column.addWidget(self.line)
        body = self._build_body()
        column.addWidget(self.coach)  # the next step, between the header and the work, never over the page
        column.addWidget(body, 1)
        column.addWidget(self._build_footer())
        self.setCentralWidget(root)

    def _welcome(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(56, 48, 56, 48)
        zone = QFrame()
        zone.setObjectName("dropZone")
        inner = QVBoxLayout(zone)
        inner.setAlignment(Qt.AlignCenter)
        inner.setSpacing(12)
        self.welcome_icon = QLabel()
        self.welcome_icon.setAlignment(Qt.AlignCenter)
        inner.addWidget(self.welcome_icon)
        inner.addSpacing(6)
        title = QLabel(tr("welcome_title"))
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        inner.addWidget(title)
        body = QLabel(tr("welcome_body"))
        body.setObjectName("welcomeBody")
        body.setAlignment(Qt.AlignCenter)
        inner.addWidget(body)
        inner.addSpacing(10)
        button = QPushButton(tr("open"))
        button.setObjectName("hero")
        button.setMinimumWidth(180)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.open_dialog)
        self.welcome_button = button
        inner.addWidget(button, alignment=Qt.AlignCenter)
        hint = QLabel(tr("welcome_hint"))
        hint.setObjectName("shortcutHint")
        hint.setAlignment(Qt.AlignCenter)
        inner.addWidget(hint)
        outer.addWidget(zone)
        return page

    # Theme --------------------------------------------------------------
    def _apply_theme(self) -> None:
        themes.apply(QApplication.instance(), self.theme)
        t = self.theme
        for action in self.findChildren(QAction):
            name = getattr(action, "icon_name", None)
            if name:
                action.setIcon(icons.icon(name, t.text))
        for button in self.header_buttons:
            color = t.on_accent if button.objectName() == "primary" else t.text
            button.setIcon(icons.icon(button.action_icon, color, 18))
        self.more_button.setIcon(icons.icon("settings", t.text, 18))
        self.busy_spinner.color = QColor(t.accent)
        self.stepper.setLayoutDirection(self.layoutDirection())
        self.stop_button.setIcon(icons.icon("close", t.accent, 16))
        for button, name in ((self.floating.previous, "next" if self.layoutDirection() == Qt.RightToLeft else "prev"),
                             (self.floating.next, "prev" if self.layoutDirection() == Qt.RightToLeft else "next"),
                             (self.floating.zoom_in, "zoom_in"), (self.floating.zoom_out, "zoom_out"),
                             (self.floating.fit, "fit")):
            button.setIcon(icons.icon(name, t.text, 18))
        for button, name in zip(self.view_switch.buttons, ("page", "type", "wand")):
            button.setIcon(icons.icon(name, t.muted, 16))
        self.setWindowIcon(icons.app_icon(t.accent, self.coptic_family))
        self.logo.setPixmap(icons.app_icon(t.accent, self.coptic_family).pixmap(34, 34))
        self.welcome_icon.setPixmap(icons.app_icon(t.accent, self.coptic_family).pixmap(96, 96))
        self.view_switch.set_colors(t.sunken, t.surface, t.border)
        self.toast.spinner.color = QColor(t.surface)
        self.coach.close.setIcon(icons.icon("close", t.muted, 16))
        self.floating.level.set_level(self.enhance_level)
        self.view.set_theme(t)
        self.panel.set_theme(t)

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
        chrome.slide_in(self.pages_panel, THUMB.width() + 72)
        self._reviewed = self._exported = False
        self.pages_header.set_count(len(self.doc))
        chrome.slide_in(self.panel, 500)
        chrome.fade(self.floating, True)
        name = self.doc.name + (f"  +{len(self.doc.paths) - 1}" if len(self.doc.paths) > 1 else "")
        self.doc_name.setText(self.doc_name.fontMetrics().elidedText(name, Qt.ElideMiddle, 210))
        self.doc_name.setToolTip(str(self.doc.paths[0]))
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
        self.view.clear()
        self._show_current()
        self.panel.set_page(self.page_image, self.results[index])
        self._update_state()

    def _show_current(self) -> None:
        """The page as scanned, or with its Coptic set in type when that view is on and the page is read."""
        if self.current < 0:
            return
        result = self.results[self.current]
        converted = self.converted_action.isChecked() and result is not None
        self.floating.show_level(self.enhanced_action.isChecked())
        if self.enhanced_action.isChecked():
            key = (self.current, self.enhance_level)
            if key in self._enhanced:
                picture, scale = self._enhanced[key]
                self.view.show_page(picture, result, quiet=True, fade=True, scale=scale)
            else:
                self._enhance_in_background(key)
            return
        image = typeset_preview(self.page_image, result) if converted else self.page_image
        self.view.show_page(image, result, quiet=converted, fade=True)

    def _enhance_in_background(self, key: tuple[int, int]) -> None:
        """Clean the page on a thread; the view changes when it is ready (if still wanted)."""
        if getattr(self, "_preview_job", None) is not None and self._preview_job.isRunning():
            self._preview_wanted = key  # computed after the running one
            return
        page, level = key
        image = self.page_image
        self.toast.show_message(tr("enhancing_page", level), 0, busy=True)
        holder = {}
        # The real result (traced curves), rendered finely enough to zoom into.
        job = Job(lambda _report: holder.setdefault("image", enhance.vector_preview(image, level)) is not None)

        def ready(_completed: bool, error: str) -> None:
            self._preview_job = None
            if error:
                self.toast.done(tr("save_failed", error))
                return
            self._enhanced = {key: holder["image"]}  # keep one page
            self.toast.done(tr("level_done", level, tr(f"level_desc_{level}")))
            wanted = getattr(self, "_preview_wanted", None)
            self._preview_wanted = None
            if wanted is not None and wanted != key:
                self._enhance_in_background(wanted)
            elif self.enhanced_action.isChecked() and (self.current, self.enhance_level) == key:
                picture, scale = holder["image"]
                self.view.show_page(picture, self.results[self.current], quiet=True, fade=True, scale=scale)

        job.done.connect(ready)
        self._preview_job = job
        job.start()

    def _enhance_more(self) -> None:
        if self.enhance_level >= 3:
            self.notify(tr("max_level"), 2500)
            return
        self._set_level(self.enhance_level + 1)

    def _set_level(self, level: int) -> None:
        self.enhance_level = level
        self.settings.setValue("enhance_level", level)
        self.floating.level.set_level(level)
        for number, action in enumerate(self.level_actions, 1):
            action.setChecked(number == level)
        if self.enhanced_action.isChecked():
            self._show_current()

    def _view_mode(self, chosen: QAction) -> None:
        """The converted and enhanced views exclude each other; neither shows the scan."""
        for action in (self.converted_action, self.enhanced_action):
            if action is not chosen:
                action.setChecked(False)
        self.view_switch.set_current(1 if self.converted_action.isChecked() else
                                     2 if self.enhanced_action.isChecked() else 0)
        self._show_current()

    def _view_chosen(self, index: int) -> None:
        """The header's view switch: the scan, the page with its text set in type, or the cleaned page.

        Choosing Enhance again while it is on raises the level, as one would expect of the button."""
        if index == 2 and self.enhanced_action.isChecked():
            self._enhance_more()
            return
        self.converted_action.setChecked(index == 1)
        self.enhanced_action.setChecked(index == 2)
        self._show_current()

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
        self.reader = Reader(self.doc.paths, self.checkpoint, device, default_checkpoint("arabic"))
        self.reader.ready.connect(self._reader_ready)
        self.reader.failed_to_start.connect(self._reader_failed)
        self.reader.page_read.connect(self._page_read)
        self.reader.page_failed.connect(
            lambda i, e: self.notify(tr("read_failed", i + 1, e), 8000))
        self.model_chip.setText(tr("model_loading"))
        self.reader.start()
        return True

    def _reader_ready(self, device: str) -> None:
        self.device = "GPU" if device.startswith("cuda") else "CPU"
        self.model_chip.setText(tr("model_ready"))
        self.model_chip.setToolTip(tr("model_info", self.checkpoint.parent.name, self.device))

    def _reader_failed(self, error: str) -> None:
        self.reader = None
        self.pending.clear()
        self.model_chip.setText("")
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
            self.converted_action.setChecked(True)  # show what the reading produced
            self.enhanced_action.setChecked(False)
            self.view_switch.set_current(1)
            self._show_current()
            self.panel.set_page(self.page_image, result)
            coptic = sum(line.script == "coptic" and bool(line.text) for line in result.lines)
            arabic = sum(line.script == "arabic" and bool(line.text) for line in result.lines)
            self.notify(tr("page_done", index + 1, coptic, arabic))
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
        if self.doc is None:
            return
        read = sum(r is not None for r in self.results)
        dialog = ExportDialog(self, read, len(self.doc), "book_pdf" if read else "enhanced", self.enhance_level)
        if dialog.exec() != ExportDialog.Accepted:
            return
        choice = dialog.choice()
        results = list(self.results)
        if choice.current_page_only:
            results = [r if i == self.current else None for i, r in enumerate(results)]
        start = Path(self.settings.value("last_dir", str(Path.home()))) / f"{self.doc.name}.{choice.suffix}"
        path, _ = QFileDialog.getSaveFileName(self, tr("export"), str(start), choice.file_filter)
        if not path:
            return
        if choice.format == "enhanced":
            pages = [self.current] if choice.current_page_only else list(range(len(self.doc)))
            self._set_level(choice.level)
            self._enhance_to(Path(path), pages)
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if choice.format == "book_pdf":
                book.to_pdf_book(self.doc, results, Path(path), choice.stanzas, choice.rule)
            elif choice.format == "book_docx":
                book.to_docx_book(self.doc, results, Path(path), choice.coptic_font, choice.stanzas, choice.rule)
            elif choice.format == "typeset":
                export.to_typeset_pdf(self.doc, results, Path(path))
            elif choice.format == "pdf":
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
        self._exported = True
        self.notify(tr("saved", path), 8000)

    def _enhance_to(self, path: Path, pages: list[int]) -> None:
        """Write the enhanced PDF on a background thread, with progress and a way to cancel."""
        progress = QProgressDialog(tr("enhancing"), tr("cancel"), 0, len(pages), self)
        progress.setWindowTitle(tr("enhanced"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        results = list(self.results)
        level = self.enhance_level
        workers = enhance.plan_workers(self.doc, pages, level)  # as many at once as free memory allows
        job = Job(lambda report: enhance.to_enhanced_pdf(self.doc, results, path, pages, report, workers=workers,
                                                         level=level))
        started = time.monotonic()

        def advanced(done: int, total: int) -> None:
            progress.setValue(done)
            text = (f"{tr('enhancing')}\n{tr('enhancing_of', min(done + 1, total), total)}"
                    f"\n{tr('enhancing_workers', workers)}")
            if done >= 3:  # once the pace is known
                left = (time.monotonic() - started) / done * (total - done)
                when = tr("under_minute") if left < 60 else tr("minutes", round(left / 60))
                text += f"\n{tr('time_left', when)}"
            progress.setLabelText(text)

        def finished(completed: bool, error: str) -> None:
            progress.close()
            self._job = None
            if error:
                QMessageBox.critical(self, tr("app_name"), tr("save_failed", error))
            elif completed:
                self._exported = True
                self.notify(tr("saved", path), 8000)

        job.progressed.connect(advanced)
        job.done.connect(finished)
        progress.canceled.connect(lambda: setattr(job, "cancelled", True))
        self._job = job  # keep the thread alive while it runs
        job.start()

    # State --------------------------------------------------------------
    def _update_state(self) -> None:
        has_doc = self.doc is not None
        busy = bool(self.pending)
        self.read_action.setEnabled(has_doc and self.current not in self.pending)
        self.read_all_action.setEnabled(has_doc and any(r is None for r in self.results))
        self.stop_action.setEnabled(busy)
        self.export_action.setEnabled(has_doc)  # enhancing pages needs no reading
        for action in (self.zoom_in_action, self.zoom_out_action, self.fit_action):
            action.setEnabled(has_doc)
        page_read = has_doc and self.current >= 0 and self.results[self.current] is not None
        self.converted_action.setEnabled(page_read)
        self.enhanced_action.setEnabled(has_doc)
        self.view_switch.setVisible(has_doc)
        self.view_switch.buttons[1].setEnabled(page_read)
        if not page_read and self.view_switch.current() == 1:
            self.view_switch.set_current(0)
        if has_doc:
            read = sum(r is not None for r in self.results)
            self.floating.page.setText(f"{self.current + 1} / {len(self.doc)}")
            self.floating.previous.setEnabled(self.current > 0)
            self.floating.next.setEnabled(self.current < len(self.doc) - 1)
            self.page_chip.setText(tr("page_of", self.current + 1, len(self.doc)))
            self.read_chip.setText(tr("pages_read", read))
        self.page_chip.setVisible(has_doc)
        self.read_chip.setVisible(has_doc)
        if busy:
            done = self.batch_total - len(self.pending)
            self.line.setMaximum(self.batch_total)
            self.line.setValue(done)
            self.busy_text.setText(tr("reading_page") if self.batch_total == 1
                                   else tr("reading", done + 1, self.batch_total))
        if busy and not self.busy.isVisible():
            self.busy_spinner.start()
        elif not busy:
            self.busy_spinner.stop()
        # The reading indicator takes the steps' place: hide one before showing the other, or for
        # a moment the header needs both and widens the window.
        if busy:
            self.stepper.hide()
            self.busy.show()
        else:
            self.busy.hide()
            self.stepper.setVisible(has_doc)
        self.line.setVisible(busy)
        self._update_guide()
        if self.checkpoint is None:
            self.model_chip.setText(tr("no_model_short"))
            self.model_chip.setToolTip(tr("no_model"))
        elif self.reader is None:
            self.model_chip.setText(tr("model_ready"))
            self.model_chip.setToolTip(tr("model_info", self.checkpoint.parent.name,
                                          "CPU" if self.cpu_action.isChecked() else "GPU / CPU"))

    def _update_guide(self) -> None:
        """The steps in the header and the guide strip follow the page on screen."""
        if self.doc is None:
            self.coach.dismiss()
            return
        read = self.results[self.current] is not None
        done = ({0} if read else set()) | ({1} if read and self._reviewed else set()) | ({2} if self._exported else set())
        step = 0 if not read else 1 if not self._reviewed else 2
        self.stepper.set_current(step, done)
        if not self.guide_action.isChecked() or self.pending or self._exported:
            self.coach.dismiss()
        elif step == 0:
            self.coach.show_step("read", tr("step", 1, 3), tr("coach_read"), tr("read_page"), self.read_current)
        elif step == 1:
            self.coach.show_step("review", tr("step", 2, 3), tr("coach_review"), tr("got_it"), self._reviewed_now)
        else:
            self.coach.show_step("export", tr("step", 3, 3), tr("coach_export"), tr("export"), self.export)

    def _start_review(self) -> None:
        """Step 2: open the first line worth a look (else the first line) for correcting."""
        result = self.results[self.current] if self.doc is not None else None
        if result is None:
            self.notify(tr("read_first"))
            return
        lines = [i for i, line in enumerate(result.lines) if line.text]
        unsure = [i for i in lines if result.lines[i].confidence < 0.9]
        if lines:
            target = (unsure or lines)[0]
            self.panel.select(target)
            self.view.select_line(target)
        self._reviewed_now()

    def _reviewed_now(self) -> None:
        self._reviewed = True
        self._update_guide()

    def _set_guide(self, on: bool) -> None:
        self.settings.setValue("guide", on)
        self._update_guide()

    def closeEvent(self, event) -> None:
        if self.pending and QMessageBox.question(self, tr("app_name"), tr("unsaved_quit")) != QMessageBox.Yes:
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self._stop_reader()
        if self.doc is not None:
            self.doc.close()
        super().closeEvent(event)
