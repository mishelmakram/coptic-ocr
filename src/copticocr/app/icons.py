"""Line icons drawn as SVG, tinted to the current theme."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 24x24 outlines, 2px strokes.
PATHS = {
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "read": '<path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5'
            'a1 1 0 0 1-1-1v-2"/><path d="M8 9h8M8 12h8M8 15h5"/>',
    "read_all": '<path d="M8 4h11a1 1 0 0 1 1 1v11"/><rect x="4" y="8" width="12" height="12" rx="1"/>'
                '<path d="M7 12h6M7 15h6"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "export": '<path d="M12 4v11M7 10l5 5 5-5"/><path d="M5 19h14"/>',
    "zoom_in": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5M11 8.5v5M8.5 11h5"/>',
    "zoom_out": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5M8.5 11h5"/>',
    "fit": '<path d="M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "keyboard": '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h.01M11 10h.01M15 10h.01'
                'M7 14h10"/>',
    "type": '<path d="M5 6V4h14v2M12 4v16M9 20h6"/>',
    "wand": '<path d="M12 3l1.8 4.6L18.5 9.5l-4.7 1.9L12 16l-1.8-4.6L5.5 9.5l4.7-1.9z"/>'
            '<path d="M19 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
    "more": '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
    "close": '<path d="M7 7l10 10M17 7L7 17"/>',
    "page": '<path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5"/>',
    "prev": '<path d="M15 6l-6 6 6 6"/>',
    "next": '<path d="M9 6l6 6-6 6"/>',
}


def icon(name: str, color: str, size: int = 20) -> QIcon:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    result = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        result.addPixmap(pixmap)
    return result


def app_icon(accent: str, coptic_family: str) -> QIcon:
    """A burgundy tile with the Coptic letter ti (Ϯ), shaped like a cross."""
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        tile = QPainterPath()
        tile.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        painter.fillPath(tile, QColor(accent))
        font = QFont(coptic_family)
        font.setPixelSize(int(size * 0.62))
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRectF(0, -size * 0.04, size, size), Qt.AlignCenter, "Ϯ")
        painter.end()
        result.addPixmap(pixmap)
    return result
