"""Colours and the Qt style sheet, light and dark."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Theme:
    dark: bool
    bg: str          # window background
    surface: str     # panels and cards
    sunken: str      # page canvas, inputs
    border: str
    text: str
    muted: str
    accent: str      # Coptic burgundy
    accent_hover: str
    accent_soft: str
    on_accent: str
    good: str
    warn: str
    bad: str


LIGHT = Theme(False, bg="#F4F2EE", surface="#FFFFFF", sunken="#E9E6E0", border="#DDD8CF",
              text="#1F1C19", muted="#6E675E", accent="#8A1C30", accent_hover="#A4263D",
              accent_soft="#F4E4E6", on_accent="#FFFFFF", good="#2F7D50", warn="#B7791F", bad="#C0392B")
DARK = Theme(True, bg="#161518", surface="#1F1E22", sunken="#121114", border="#322F36",
             text="#ECE9E4", muted="#A39D95", accent="#D45C70", accent_hover="#E27286",
             accent_soft="#3A2329", on_accent="#1A0E11", good="#5BBE84", warn="#E0A64A", bad="#EE6B5B")


def confidence_color(theme: Theme, confidence: float) -> str:
    if confidence >= 0.9:
        return theme.good
    return theme.warn if confidence >= 0.6 else theme.bad


def apply(app: QApplication, theme: Theme) -> None:
    palette = QPalette()
    for role, value in [
        (QPalette.Window, theme.bg), (QPalette.Base, theme.surface), (QPalette.AlternateBase, theme.sunken),
        (QPalette.Text, theme.text), (QPalette.WindowText, theme.text), (QPalette.ButtonText, theme.text),
        (QPalette.Button, theme.surface), (QPalette.Highlight, theme.accent),
        (QPalette.HighlightedText, theme.on_accent), (QPalette.PlaceholderText, theme.muted),
        (QPalette.ToolTipBase, theme.surface), (QPalette.ToolTipText, theme.text),
    ]:
        palette.setColor(role, QColor(value))
    app.setPalette(palette)
    # The UI font is set here, not in the style sheet, which would override the Coptic font of editors.
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(style_sheet(theme))


def style_sheet(t: Theme) -> str:
    return f"""
    QMainWindow, QDialog {{ background: {t.bg}; }}
    QWidget {{ color: {t.text}; }}
    QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border}; padding: 6px; }}

    QMenuBar {{ background: {t.surface}; border-bottom: 1px solid {t.border}; padding: 2px 6px; }}
    QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; background: transparent; }}
    QMenuBar::item:selected {{ background: {t.sunken}; }}
    QMenu {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px; padding: 6px; }}
    QMenu::item {{ padding: 7px 26px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}
    QMenu::separator {{ height: 1px; background: {t.border}; margin: 5px 8px; }}

    QToolBar {{ background: {t.surface}; border: none; border-bottom: 1px solid {t.border};
                padding: 8px 12px; spacing: 6px; }}
    QToolBar::separator {{ width: 1px; background: {t.border}; margin: 6px 8px; }}
    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px;
                   padding: 6px 12px; }}
    QToolButton:hover {{ background: {t.sunken}; }}
    QToolButton:pressed, QToolButton:checked {{ background: {t.accent_soft}; border-color: {t.accent_soft}; }}
    QToolButton:disabled {{ color: {t.muted}; }}
    QToolButton#primary {{ background: {t.accent}; color: {t.on_accent}; font-weight: 600; }}
    QToolButton#primary:hover {{ background: {t.accent_hover}; }}
    QToolButton#primary:disabled {{ background: {t.sunken}; color: {t.muted}; }}

    QPushButton {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px;
                   padding: 7px 18px; }}
    QPushButton:hover {{ border-color: {t.muted}; }}
    QPushButton#primary {{ background: {t.accent}; border-color: {t.accent}; color: {t.on_accent};
                           font-weight: 600; }}
    QPushButton#primary:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}

    QSplitter::handle {{ background: {t.border}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}

    QListWidget#pages {{ background: {t.surface}; border: none; padding: 8px 4px; outline: none; }}
    QListWidget#pages::item {{ border: 2px solid transparent; border-radius: 8px; padding: 6px;
                               margin: 2px; color: {t.muted}; }}
    QListWidget#pages::item:hover {{ background: {t.sunken}; }}
    QListWidget#pages::item:selected {{ border-color: {t.accent}; background: {t.accent_soft};
                                        color: {t.text}; }}

    QGraphicsView#canvas {{ background: {t.sunken}; border: none; }}
    QWidget#panel {{ background: {t.surface}; }}
    QLabel#panelTitle {{ font-size: 11pt; font-weight: 600; }}
    QLabel#muted {{ color: {t.muted}; }}
    QLabel#welcomeTitle {{ font-size: 18pt; font-weight: 600; }}
    QLabel#welcomeBody {{ color: {t.muted}; font-size: 11pt; }}
    QFrame#dropZone {{ border: 2px dashed {t.border}; border-radius: 16px; background: {t.surface}; }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QFrame#lineCard {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px; }}
    QFrame#lineCard[selected="true"] {{ border: 2px solid {t.accent}; background: {t.accent_soft}; }}
    QLabel#lineNumber {{ color: {t.muted}; font-size: 9pt; }}
    QLabel#badge {{ border-radius: 8px; padding: 1px 8px; font-size: 8pt; font-weight: 600; }}
    QLabel#lineImage {{ background: #FFFFFF; border-radius: 6px; }}
    QLineEdit {{ background: {t.sunken}; border: 1px solid {t.border}; border-radius: 6px;
                 padding: 5px 8px; selection-background-color: {t.accent}; }}
    QLineEdit:focus {{ border-color: {t.accent}; }}

    QTabBar::tab {{ background: transparent; padding: 6px 14px; border-radius: 6px; color: {t.muted}; }}
    QTabBar::tab:selected {{ background: {t.accent_soft}; color: {t.text}; font-weight: 600; }}
    QTabBar::tab:hover:!selected {{ background: {t.sunken}; }}

    QStatusBar {{ background: {t.surface}; border-top: 1px solid {t.border}; color: {t.muted}; }}
    QStatusBar QLabel {{ color: {t.muted}; padding: 0 8px; }}
    QProgressBar {{ background: {t.sunken}; border: none; border-radius: 4px; height: 8px;
                    max-height: 8px; text-align: center; }}
    QProgressBar::chunk {{ background: {t.accent}; border-radius: 4px; }}

    QComboBox {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px; padding: 6px 10px; }}
    QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border};
                                   selection-background-color: {t.accent_soft}; selection-color: {t.text}; }}
    QRadioButton {{ spacing: 8px; padding: 4px 0; }}
    QGroupBox {{ border: 1px solid {t.border}; border-radius: 10px; margin-top: 14px; padding: 12px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; right: 12px; padding: 0 4px; color: {t.muted}; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t.muted}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """
