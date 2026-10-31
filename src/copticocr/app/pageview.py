"""The scanned page, zoomable, with the recognized lines outlined."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from ..pipeline import PageResult
from .theme import Theme, confidence_color


def to_pixmap(image: Image.Image) -> QPixmap:
    gray = image.convert("L")
    qimage = QImage(gray.tobytes(), gray.width, gray.height, gray.width, QImage.Format_Grayscale8)
    return QPixmap.fromImage(qimage.copy())


class LineItem(QGraphicsRectItem):
    def __init__(self, index: int, rect: QRectF):
        super().__init__(rect)
        self.index = index
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)


class PageView(QGraphicsView):
    line_clicked = Signal(int)

    def __init__(self, theme: Theme):
        super().__init__()
        self.setObjectName("canvas")
        self.setLayoutDirection(Qt.LeftToRight)  # pages are not mirrored in Arabic mode
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.theme = theme
        self._page: QGraphicsPixmapItem | None = None
        self._lines: list[LineItem] = []
        self._result: PageResult | None = None
        self._selected = -1
        self._fit = True
        self.quiet = False  # outline only the selected line (over typeset text the boxes are clutter)

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self._style_lines()

    def clear(self) -> None:
        self.scene().clear()
        self._page, self._lines, self._result, self._selected = None, [], None, -1

    def show_page(self, image: Image.Image, result: PageResult | None, quiet: bool = False) -> None:
        selected = self._selected
        self.quiet = quiet
        self.clear()
        self._page = self.scene().addPixmap(to_pixmap(image))
        self._page.setTransformationMode(Qt.SmoothTransformation)
        self.scene().setSceneRect(QRectF(self._page.pixmap().rect()).adjusted(-40, -40, 40, 40))
        self.set_result(result)
        if 0 <= selected < len(self._lines):
            self.select_line(selected, scroll=False)
        if self._fit:
            self.fit_width()

    def set_result(self, result: PageResult | None) -> None:
        for item in self._lines:
            self.scene().removeItem(item)
        self._lines, self._result, self._selected = [], result, -1
        if result is None:
            return
        for i, line in enumerate(result.lines):
            b = line.box
            item = LineItem(i, QRectF(b.x0 - 4, b.y0 - 3, b.x1 - b.x0 + 8, b.y1 - b.y0 + 6))
            self.scene().addItem(item)
            self._lines.append(item)
        self._style_lines()

    def select_line(self, index: int, scroll: bool = True) -> None:
        self._selected = index
        self._style_lines()
        if scroll and 0 <= index < len(self._lines):
            self.ensureVisible(self._lines[index], 60, 120)

    def _style_lines(self) -> None:
        if self._result is None:
            return
        for item, line in zip(self._lines, self._result.lines):
            if line.script == "arabic" and not line.text:
                color = QColor(self.theme.muted)
                pen = QPen(color, 1.5, Qt.DashLine)
            else:
                color = QColor(confidence_color(self.theme, 1.0 if line.edited else line.confidence))
                pen = QPen(color, 2)
            pen.setCosmetic(True)
            fill = QColor(color)
            fill.setAlpha(60 if item.index == self._selected else 14)
            if self.quiet and item.index != self._selected:
                pen, fill = QPen(Qt.NoPen), QColor(Qt.transparent)
            if item.index == self._selected:
                pen = QPen(QColor(self.theme.accent), 3)
                pen.setCosmetic(True)
            item.setPen(pen)
            item.setBrush(QBrush(fill))

    # Zoom ---------------------------------------------------------------
    def fit_width(self) -> None:
        if self._page is None:
            return
        self._fit = True
        self.resetTransform()
        width = self._page.pixmap().width() + 80
        scale = (self.viewport().width() - 4) / width
        self.scale(scale, scale)

    def zoom(self, factor: float) -> None:
        current = self.transform().m11()
        if 0.05 < current * factor < 8:
            self._fit = False
            self.scale(factor, factor)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit:
            self.fit_width()

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, LineItem):
            self.line_clicked.emit(item.index)
            return
        super().mousePressEvent(event)
