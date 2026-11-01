"""Start the desktop application: ``copticocr [book.pdf ...]``."""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from ..export import bundled_font
from .i18n import language, set_language


def use_portable_settings() -> None:
    """The portable copy (a ``portable`` file beside the program) keeps its settings in a folder
    beside it, so it runs from a USB stick and leaves nothing in the registry."""
    home = Path(sys.executable).parent
    if getattr(sys, "frozen", False) and (home / "portable").exists():
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(home / "settings"))


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()  # enhancing uses worker processes, also in a frozen build
    argv = sys.argv if argv is None else argv
    if sys.platform == "win32":  # the taskbar shows the program's own icon, not Python's
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CopticOCR.CopticOCR")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setOrganizationName("CopticOCR")
    app.setApplicationName("Coptic OCR")
    app.setStyle("Fusion")  # the style sheet assumes Fusion's metrics
    use_portable_settings()

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
