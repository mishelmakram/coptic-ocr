"""Pieces of the window's frame: segmented switch, floating page controls, panel headers."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)


def shadow(widget: QWidget, blur: int = 24, alpha: int = 40, dy: int = 6) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


def tool_button(name: str, tip: str = "", checkable: bool = False) -> QToolButton:
    button = QToolButton()
    button.setObjectName(name)
    button.setToolTip(tip)
    button.setCheckable(checkable)
    button.setCursor(Qt.PointingHandCursor)
    button.setAutoRaise(True)
    return button


class Segmented(QFrame):
    """A row of mutually exclusive choices drawn as one control."""

    chosen = Signal(int)

    def __init__(self, labels: list[str]):
        super().__init__()
        self.setObjectName("segmented")
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QToolButton] = []
        for i, label in enumerate(labels):
            button = tool_button("segment", checkable=True)
            button.setText(label)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.group.addButton(button, i)
            layout.addWidget(button)
            self.buttons.append(button)
        self.buttons[0].setChecked(True)
        self.group.idClicked.connect(self.chosen)

    def set_current(self, index: int) -> None:
        self.buttons[index].setChecked(True)

    def current(self) -> int:
        return self.group.checkedId()


class FloatingBar(QFrame):
    """Page and zoom controls floating over the bottom of the page."""

    def __init__(self):
        super().__init__()
        self.setObjectName("pill")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        self.previous = tool_button("pillButton")
        self.page = QLabel()
        self.page.setObjectName("pillLabel")
        self.page.setAlignment(Qt.AlignCenter)
        self.page.setMinimumWidth(84)
        self.next = tool_button("pillButton")
        divider = QFrame()
        divider.setObjectName("pillDivider")
        divider.setFixedSize(1, 20)
        self.zoom_out = tool_button("pillButton")
        self.zoom_in = tool_button("pillButton")
        self.fit = tool_button("pillButton")
        for widget in (self.previous, self.page, self.next, divider, self.zoom_out, self.zoom_in, self.fit):
            layout.addWidget(widget)
        shadow(self, 28, 55, 8)


class Canvas(QWidget):
    """Holds the page (or the welcome screen) with the floating bar over its bottom edge."""

    def __init__(self, content: QWidget, bar: FloatingBar):
        super().__init__()
        self.setObjectName("canvasArea")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content)
        self.bar = bar
        bar.setParent(self)
        bar.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.bar.adjustSize()
        self.bar.move(QPoint((self.width() - self.bar.width()) // 2, self.height() - self.bar.height() - 22))


class PanelHeader(QWidget):
    """A side panel's title, an optional count, and room for controls."""

    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("panelHeader")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(8)
        self.title = QLabel(title)
        self.title.setObjectName("panelTitle")
        self.count = QLabel()
        self.count.setObjectName("countChip")
        layout.addWidget(self.title)
        layout.addWidget(self.count)
        layout.addStretch()
        self.controls = layout

    def set_count(self, n: int | None) -> None:
        self.count.setVisible(n is not None)
        if n is not None:
            self.count.setText(str(n))


def stretch() -> QWidget:
    spacer = QWidget()
    spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    return spacer
