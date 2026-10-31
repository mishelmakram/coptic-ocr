"""The proofreading panel: each line's image above its editable text."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QTabBar, QVBoxLayout,
                               QWidget)

from ..legacy import get_layout
from ..pipeline import PageResult, TextLine, crop
from .i18n import tr
from .pageview import to_pixmap
from .theme import Theme, confidence_color

REVIEW_BELOW = 0.9  # lines with a less certain letter are flagged for checking


class CopticLineEdit(QLineEdit):
    """A line editor that can turn Latin keys into Coptic, as the CS fonts do."""

    def __init__(self, text: str, coptic_font: QFont):
        super().__init__(text)
        self.setFont(coptic_font)
        self.legacy_keys = True
        self._layout = get_layout("cs")
        self._pending = ""  # prefix marks (jinkim, overline) waiting for their letter

    def keyPressEvent(self, event) -> None:
        typed = event.text()
        if (self.legacy_keys and len(typed) == 1 and self.layoutDirection() == Qt.LeftToRight
                and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            if typed in self._layout.prefix_marks:
                self._pending += self._layout.prefix_marks[typed]
                return
            if typed in self._layout.chars:
                piece = self._layout.chars[typed]
                if piece:
                    self.insert(piece[0] + self._pending + piece[1:])
                self._pending = ""
                return
        self._pending = ""
        super().keyPressEvent(event)


class LineCard(QFrame):
    clicked = Signal(int)
    edited = Signal(int, str)

    def __init__(self, index: int, line: TextLine, image: Image.Image, width: int, theme: Theme,
                 coptic_font: QFont, legacy_keys: bool):
        super().__init__()
        self.setObjectName("lineCard")
        self.index = index
        self.line = line
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        number = QLabel(str(index + 1))
        number.setObjectName("lineNumber")
        header.addWidget(number)
        header.addStretch()
        self.badge = QLabel()
        self.badge.setObjectName("badge")
        header.addWidget(self.badge)
        layout.addLayout(header)

        picture = QLabel()
        picture.setObjectName("lineImage")
        picture.setAlignment(Qt.AlignCenter)
        pixmap = to_pixmap(crop(image, line.box))
        if pixmap.width() > width:
            pixmap = pixmap.scaledToWidth(width, Qt.SmoothTransformation)
        picture.setPixmap(pixmap)
        picture.setLayoutDirection(Qt.LeftToRight)
        layout.addWidget(picture)

        self.edit = CopticLineEdit(line.text, coptic_font)
        self.edit.legacy_keys = legacy_keys
        if line.script == "arabic":
            self.edit.setLayoutDirection(Qt.RightToLeft)
            self.edit.setPlaceholderText(tr("arabic_soon"))
            self.edit.setFont(QFont("Segoe UI", 12))
        else:
            self.edit.setLayoutDirection(Qt.LeftToRight)
        self.edit.textEdited.connect(self._on_edit)
        layout.addWidget(self.edit)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        line = self.line
        if line.edited:
            text, color = tr("edited"), theme.accent
        elif line.text and line.confidence < REVIEW_BELOW:
            text, color = tr("review"), confidence_color(theme, line.confidence)
        else:
            self.badge.hide()
            return
        self.badge.setText(text)
        self.badge.setStyleSheet(f"color: {color}; border: 1px solid {color};")
        self.badge.show()

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def _on_edit(self, text: str) -> None:
        self.line.text = text
        self.line.edited = True
        self.edited.emit(self.index, text)


class ProofreadPanel(QWidget):
    line_selected = Signal(int)
    line_edited = Signal(int)

    def __init__(self, theme: Theme, coptic_font: QFont):
        super().__init__()
        self.setObjectName("panel")
        self.theme = theme
        self.coptic_font = coptic_font
        self.legacy_keys = True
        self._cards: list[LineCard] = []
        self._image: Image.Image | None = None
        self._result: PageResult | None = None
        self._selected = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 6, 0)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel(tr("lines"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        for key in ("coptic", "arabic", "all"):
            self.tabs.addTab(tr(key))
        self.tabs.currentChanged.connect(lambda _: self._rebuild())
        header.addWidget(self.tabs)
        layout.addLayout(header)

        self.message = QLabel()
        self.message.setObjectName("muted")
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.list = QVBoxLayout(self.body)
        self.list.setContentsMargins(0, 0, 8, 14)
        self.list.setSpacing(8)
        self.list.addStretch()
        self.scroll.setWidget(self.body)
        layout.addWidget(self.scroll, 1)
        self.set_page(None, None)

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        for card in self._cards:
            card.set_theme(theme)

    def set_legacy_keys(self, on: bool) -> None:
        self.legacy_keys = on
        for card in self._cards:
            card.edit.legacy_keys = on

    def set_page(self, image: Image.Image | None, result: PageResult | None) -> None:
        self._image, self._result, self._selected = image, result, -1
        self._rebuild()

    def _rebuild(self) -> None:
        for card in self._cards:
            card.deleteLater()
        self._cards = []
        if self._result is None or self._image is None:
            self.message.setText(tr("not_read") if self._image is not None else "")
            self.message.setVisible(self._image is not None)
            return
        self.message.hide()
        wanted = ("coptic", "arabic", None)[self.tabs.currentIndex()]
        width = max(200, self.scroll.viewport().width() - 40)
        for i, line in enumerate(self._result.lines):
            if wanted is not None and line.script != wanted:
                continue
            card = LineCard(i, line, self._image, width, self.theme, self.coptic_font, self.legacy_keys)
            card.clicked.connect(self._on_click)
            card.edited.connect(self._on_edited)
            self.list.insertWidget(self.list.count() - 1, card)
            self._cards.append(card)
        if self._selected >= 0:
            self.select(self._selected)

    def select(self, index: int) -> None:
        self._selected = index
        target = None
        for card in self._cards:
            card.set_selected(card.index == index)
            if card.index == index:
                target = card
        if target is None and self._result is not None and 0 <= index < len(self._result.lines):
            # The line is on another tab: switch to the one showing its script.
            script = self._result.lines[index].script
            self.tabs.setCurrentIndex(0 if script == "coptic" else 1)
            return
        if target is not None:
            QTimer.singleShot(0, lambda: self.scroll.ensureWidgetVisible(target, 0, 40))
            target.edit.setFocus()

    def _on_click(self, index: int) -> None:
        self.select(index)
        self.line_selected.emit(index)

    def _on_edited(self, index: int, _text: str) -> None:
        for card in self._cards:
            if card.index == index:
                card.set_theme(self.theme)
        self.line_edited.emit(index)
