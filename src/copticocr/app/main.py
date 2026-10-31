"""Start the desktop application: ``copticocr [book.pdf ...]``."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from ..export import bundled_font
from .i18n import language, set_language


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setOrganizationName("CopticOCR")
    app.setApplicationName("Coptic OCR")
    app.setStyle("Fusion")  # the style sheet assumes Fusion's metrics

    set_language(QSettings().value("language", "ar"))
    if language() == "ar":
        app.setLayoutDirection(Qt.RightToLeft)

    font_id = QFontDatabase.addApplicationFont(str(bundled_font()))
    families = QFontDatabase.applicationFontFamilies(font_id)
    coptic_family = families[0] if families else "Noto Sans Coptic"

    from .window import MainWindow  # after the language is set: the window reads its strings

    window = MainWindow(coptic_family)
    window.show()
    paths = [Path(a) for a in argv[1:] if Path(a).exists()]
    if paths:
        window.open_paths(paths)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
