"""Pieces of the window's frame, with their small animations.

Segmented switch with a sliding highlight, spinner, toast messages, the guide card
that names the next step, floating page controls (with the enhancement level), and
panel headers.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

FAST, SLOW = 180, 260  # milliseconds


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


def fade(widget: QWidget, show: bool, ms: int = FAST, done=None) -> None:
    """Fade a widget in or out (it is hidden at the end of a fade out)."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(ms)
    animation.setStartValue(effect.opacity() if widget.isVisible() else 0.0)
    animation.setEndValue(1.0 if show else 0.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    if show:
        widget.show()
    animation.finished.connect(lambda: (None if show else widget.hide(), done and done()))
    animation.start(QPropertyAnimation.DeleteWhenStopped)


def slide_in(widget: QWidget, width: int, ms: int = SLOW) -> None:
    """Show a side panel by widening it from nothing."""
    if widget.isVisible():
        return
    widget.setMaximumWidth(0)
    widget.show()
    animation = QPropertyAnimation(widget, b"maximumWidth", widget)
    animation.setDuration(ms)
    animation.setStartValue(0)
    animation.setEndValue(width)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    animation.finished.connect(lambda: widget.setMaximumWidth(16777215))
    animation.start(QPropertyAnimation.DeleteWhenStopped)


class Segmented(QFrame):
    """A row of mutually exclusive choices; the highlight slides to the chosen one."""

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
        self.group.idClicked.connect(self._clicked)
        self.colors = (QColor("#EFEDEA"), QColor("#FFFFFF"), QColor("#E5E1DB"))
        self._highlight = QRectF()
        self._slide = QVariantAnimation(self)
        self._slide.setDuration(SLOW)
        self._slide.setEasingCurve(QEasingCurve.OutCubic)
        self._slide.valueChanged.connect(self._moved)

    def set_colors(self, background: str, highlight: str, border: str) -> None:
        self.colors = (QColor(background), QColor(highlight), QColor(border))
        self.update()

    def _clicked(self, index: int) -> None:
        self._glide()
        self.chosen.emit(index)

    def set_current(self, index: int) -> None:
        if self.group.checkedId() != index:
            self.buttons[index].setChecked(True)
            self._glide()

    def current(self) -> int:
        return self.group.checkedId()

    def _target(self) -> QRectF:
        button = self.buttons[max(0, self.group.checkedId())]
        return QRectF(button.geometry())

    def _glide(self) -> None:
        if self._highlight.isNull() or not self.isVisible():
            self._highlight = self._target()
            self.update()
            return
        self._slide.stop()
        self._slide.setStartValue(self._highlight)
        self._slide.setEndValue(self._target())
        self._slide.start()

    def _moved(self, rect) -> None:
        self._highlight = rect
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._highlight = self._target()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, lambda: (setattr(self, "_highlight", self._target()), self.update()))

    def paintEvent(self, event) -> None:
        background, highlight, border = self.colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(self.rect()), 11, 11)
        if not self._highlight.isNull():
            painter.setBrush(highlight)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(self._highlight.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)


class Spinner(QWidget):
    """A small turning arc: work is in progress."""

    def __init__(self, size: int = 16):
        super().__init__()
        self.setFixedSize(size, size)
        self.color = QColor("#8C1D33")
        self._angle = 0
        self._turn = QVariantAnimation(self)
        self._turn.setStartValue(0)
        self._turn.setEndValue(360)
        self._turn.setDuration(900)
        self._turn.setLoopCount(-1)
        self._turn.valueChanged.connect(lambda v: (setattr(self, "_angle", v), self.update()))

    def start(self) -> None:
        self.show()
        self._turn.start()

    def stop(self) -> None:
        self._turn.stop()
        self.hide()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self.color, 2.2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        painter.drawArc(r, -self._angle * 16, 270 * 16)


class Toast(QFrame):
    """A short message that fades in over the page and fades out by itself."""

    def __init__(self):
        super().__init__()
        self.setObjectName("toast")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 16, 9)
        layout.setSpacing(10)
        self.spinner = Spinner()
        self.spinner.hide()
        self.text = QLabel()
        self.text.setObjectName("toastText")
        layout.addWidget(self.spinner)
        layout.addWidget(self.text)
        self._timer = QTimer(self, singleShot=True, timeout=lambda: fade(self, False, SLOW))
        self.hide()

    def show_message(self, text: str, ms: int = 3500, busy: bool = False) -> None:
        self.text.setText(text)
        self.spinner.start() if busy else self.spinner.stop()
        self.adjustSize()
        if self.parent() is not None:
            self.parent().place()
        fade(self, True)
        self._timer.stop()
        if ms:
            self._timer.start(ms)

    def done(self, text: str | None = None) -> None:
        if text:
            self.show_message(text)
        else:
            self._timer.start(0)


class CoachCard(QFrame):
    """The next step, in a sentence, with a button that takes it."""

    def __init__(self):
        super().__init__()
        self.setObjectName("coach")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(12)
        self.step = QLabel()
        self.step.setObjectName("stepChip")
        self.step.setAlignment(Qt.AlignCenter)
        self.text = QLabel()
        self.text.setObjectName("coachText")
        self.text.setWordWrap(True)
        self.action = QPushButton()
        self.action.setObjectName("primarySmall")
        self.action.setCursor(Qt.PointingHandCursor)
        self.close = tool_button("iconButton")
        layout.addWidget(self.step)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.action)
        layout.addWidget(self.close)
        self._callback = None
        self.action.clicked.connect(lambda: self._callback and self._callback())
        shadow(self, 30, 45, 8)
        self.hide()
        self.current = None

    def show_step(self, key: str, step: str, text: str, button: str | None, callback) -> None:
        if self.current == key and self.isVisible():
            return
        self.current = key
        self.step.setText(step)
        self.text.setText(text)
        self.action.setVisible(bool(button))
        self.action.setText(button or "")
        self._callback = callback
        self.adjustSize()
        if self.parent() is not None:
            self.parent().place()
        self.setGraphicsEffect(None)  # the fade's opacity effect replaces the shadow while it runs
        fade(self, True, SLOW, done=lambda: shadow(self, 30, 45, 8))

    def dismiss(self) -> None:
        self.current = None
        if self.isVisible():
            fade(self, False)


class LevelControl(QWidget):
    """The enhancement level as three dots, and a button to go one level higher."""

    level_chosen = Signal(int)
    more = Signal()

    def __init__(self, label: str, more_text: str):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(4)
        title = QLabel(label)
        title.setObjectName("pillLabel")
        layout.addWidget(title)
        self.dots = []
        group = QButtonGroup(self)
        group.setExclusive(False)  # the dots fill up to the level
        for level in (1, 2, 3):
            dot = tool_button("dot", checkable=True)
            dot.setFixedSize(18, 18)
            group.addButton(dot, level)
            layout.addWidget(dot)
            self.dots.append(dot)
        group.idClicked.connect(self.level_chosen)
        self._level = 1
        self.more_button = QPushButton(more_text)
        self.more_button.setObjectName("pillAction")
        self.more_button.setCursor(Qt.PointingHandCursor)
        self.more_button.clicked.connect(self.more)
        layout.addSpacing(4)
        layout.addWidget(self.more_button)

    def set_level(self, level: int) -> None:
        self._level = level
        for i, dot in enumerate(self.dots, 1):
            dot.setChecked(i <= level)  # filled up to the level
        self.more_button.setEnabled(level < 3)


class FloatingBar(QFrame):
    """Page and zoom controls floating over the bottom of the page."""

    def __init__(self, level_label: str, more_text: str):
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
        self.zoom_out = tool_button("pillButton")
        self.zoom_in = tool_button("pillButton")
        self.fit = tool_button("pillButton")
        self.level = LevelControl(level_label, more_text)
        self.level_divider = self._divider()
        for widget in (self.previous, self.page, self.next, self._divider(), self.zoom_out, self.zoom_in, self.fit,
                       self.level_divider, self.level):
            layout.addWidget(widget)
        self.show_level(False)
        shadow(self, 28, 55, 8)

    @staticmethod
    def _divider() -> QFrame:
        divider = QFrame()
        divider.setObjectName("pillDivider")
        divider.setFixedSize(1, 20)
        return divider

    def show_level(self, on: bool) -> None:
        self.level.setVisible(on)
        self.level_divider.setVisible(on)
        self.adjustSize()
        if self.parent() is not None:
            self.parent().place()


class Canvas(QWidget):
    """Holds the page (or the welcome screen), with the guide card above it and the
    floating bar and messages over its bottom edge."""

    def __init__(self, content: QWidget, bar: FloatingBar, toast: Toast, coach: CoachCard):
        super().__init__()
        self.setObjectName("canvasArea")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content)
        self.bar, self.toast, self.coach = bar, toast, coach
        for widget in (coach, toast, bar):
            widget.setParent(self)
            widget.raise_()

    def place(self) -> None:
        self.bar.adjustSize()
        self.bar.move(QPoint((self.width() - self.bar.width()) // 2, self.height() - self.bar.height() - 22))
        self.toast.adjustSize()
        self.toast.move(QPoint((self.width() - self.toast.width()) // 2,
                               self.bar.y() - self.toast.height() - 12 if self.bar.isVisible()
                               else self.height() - self.toast.height() - 28))
        width = min(620, self.width() - 48)
        self.coach.setFixedWidth(width)
        self.coach.adjustSize()
        self.coach.move(QPoint((self.width() - width) // 2, 18))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place()


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
