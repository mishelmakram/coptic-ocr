"""Colours and the Qt style sheet, light and dark."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Theme:
    dark: bool
    bg: str          # behind the panels
    surface: str     # panels, header, cards
    sunken: str      # inputs, segmented control, the page's surroundings
    border: str
    text: str
    muted: str
    accent: str      # Coptic burgundy, kept for what matters
    accent_hover: str
    accent_soft: str
    on_accent: str
    good: str
    warn: str
    bad: str
    canvas: str      # around the page


LIGHT = Theme(False, bg="#F4F3F1", surface="#FFFFFF", sunken="#EFEDEA", border="#E5E1DB",
              text="#1C1A17", muted="#7A746C", accent="#8C1D33", accent_hover="#A2263F",
              accent_soft="#F7E8EB", on_accent="#FFFFFF", good="#2E7D52", warn="#B7791F", bad="#C0392B",
              canvas="#E8E6E2")
DARK = Theme(True, bg="#111113", surface="#1A1A1D", sunken="#242428", border="#2C2C31",
             text="#EEECE9", muted="#9C978F", accent="#E0627B", accent_hover="#EC7B92",
             accent_soft="#3B1F27", on_accent="#1A0B10", good="#5CC08A", warn="#E3A84E", bad="#F06B5B",
             canvas="#0C0C0E")


def confidence_color(theme: Theme, confidence: float) -> str:
    if confidence >= 0.9:
        return theme.good
    return theme.warn if confidence >= 0.6 else theme.bad


def ui_family() -> str:
    """Windows 11's variable UI face where present, else Segoe UI."""
    families = set(QFontDatabase.families())
    return next((f for f in ("Segoe UI Variable Text", "Segoe UI") if f in families), "Segoe UI")


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
    app.setFont(QFont(ui_family(), 10))
    app.setStyleSheet(style_sheet(theme))


def style_sheet(t: Theme) -> str:
    return f"""
    QMainWindow, QDialog {{ background: {t.bg}; }}
    QWidget {{ color: {t.text}; }}
    QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border}; border-radius: 6px;
                padding: 6px 8px; }}

    /* Header */
    QFrame#header {{ background: {t.surface}; border: none; border-bottom: 1px solid {t.border}; }}
    QLabel#brand {{ font-size: 12pt; font-weight: 700; }}
    QLabel#docName {{ color: {t.muted}; font-size: 10pt; }}
    QProgressBar#line {{ background: transparent; border: none; max-height: 3px; min-height: 3px; }}
    QProgressBar#line::chunk {{ background: {t.accent}; }}
    QFrame#busy {{ background: {t.accent_soft}; border-radius: 15px; }}
    QLabel#busyText {{ color: {t.accent}; font-weight: 600; padding: 0 2px; }}

    QPushButton {{ border-radius: 9px; padding: 7px 14px; font-weight: 600; }}
    QPushButton#primary {{ background: {t.accent}; color: {t.on_accent}; border: 1px solid {t.accent}; }}
    QPushButton#primary:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
    QPushButton#primary:disabled {{ background: {t.sunken}; color: {t.muted}; border-color: {t.sunken}; }}
    QPushButton#secondary {{ background: {t.surface}; border: 1px solid {t.border}; }}
    QPushButton#secondary:hover {{ background: {t.sunken}; }}
    QPushButton#secondary:disabled {{ color: {t.muted}; }}
    QPushButton#hero {{ background: {t.accent}; color: {t.on_accent}; border: none; border-radius: 12px;
                        padding: 11px 26px; font-size: 11pt; }}
    QPushButton#hero:hover {{ background: {t.accent_hover}; }}
    QPushButton#ghost {{ background: transparent; border: 1px solid transparent; }}
    QPushButton#ghost:hover {{ background: {t.sunken}; }}
    QPushButton#ghost:disabled {{ color: {t.muted}; }}
    QPushButton {{ background: {t.surface}; border: 1px solid {t.border}; }}

    QToolButton#iconButton {{ border: none; border-radius: 9px; padding: 7px; }}
    QToolButton#iconButton:hover {{ background: {t.sunken}; }}
    QToolButton#iconButton::menu-indicator {{ image: none; width: 0; }}
    QToolButton#stopButton {{ border: none; border-radius: 11px; padding: 3px; }}
    QToolButton#stopButton:hover {{ background: {t.surface}; }}

    QFrame#segmented {{ background: transparent; }}
    QToolButton#segment {{ border: none; border-radius: 8px; padding: 6px 14px; color: {t.muted};
                           font-weight: 600; }}
    QToolButton#segment:hover {{ color: {t.text}; }}
    QToolButton#segment:checked {{ background: transparent; color: {t.text}; }}
    QToolButton#segment:disabled {{ color: {t.border}; }}

    QMenu {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px; padding: 6px; }}
    QMenu::item {{ padding: 8px 28px 8px 14px; border-radius: 7px; }}
    QMenu::item:selected {{ background: {t.sunken}; color: {t.text}; }}
    QMenu::item:disabled {{ color: {t.muted}; }}
    QMenu::separator {{ height: 1px; background: {t.border}; margin: 6px 8px; }}
    QMenu::indicator {{ width: 14px; height: 14px; }}

    /* Body */
    QSplitter::handle {{ background: {t.bg}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QFrame#sidePanel {{ background: {t.surface}; border: none; }}
    QWidget#panelHeader {{ background: transparent; }}
    QLabel#panelTitle {{ font-size: 11pt; font-weight: 700; }}
    QLabel#countChip {{ background: {t.sunken}; color: {t.muted}; border-radius: 9px; padding: 1px 8px;
                        font-size: 9pt; font-weight: 600; }}
    QListWidget#pages {{ background: transparent; border: none; padding: 0 8px 8px 8px; outline: none; }}
    QListWidget#pages::item {{ border: 2px solid transparent; border-radius: 10px; padding: 6px; margin: 2px;
                               color: {t.muted}; }}
    QListWidget#pages::item:hover {{ background: {t.sunken}; }}
    QListWidget#pages::item:selected {{ border-color: {t.accent}; background: {t.accent_soft}; color: {t.text}; }}

    QWidget#canvasArea, QStackedWidget#stack {{ background: {t.canvas}; }}
    QGraphicsView#canvas {{ background: {t.canvas}; border: none; }}
    QFrame#pill {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 20px; }}
    QToolButton#pillButton {{ border: none; border-radius: 15px; padding: 6px; }}
    QToolButton#pillButton:hover {{ background: {t.sunken}; }}
    QToolButton#pillButton:disabled {{ background: transparent; }}
    QLabel#pillLabel {{ font-weight: 600; color: {t.text}; padding: 0 4px; }}
    QFrame#pillDivider {{ background: {t.border}; }}

    QFrame#toast {{ background: {t.text}; border-radius: 12px; }}
    QLabel#toastText {{ color: {t.surface}; font-weight: 600; }}
    QFrame#coach {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 14px; }}
    QLabel#coachText {{ color: {t.text}; }}
    QLabel#stepChip {{ background: {t.accent_soft}; color: {t.accent}; border-radius: 12px; padding: 4px 10px;
                       font-weight: 700; min-width: 38px; }}
    QPushButton#primarySmall {{ background: {t.accent}; color: {t.on_accent}; border: none; border-radius: 9px;
                                padding: 6px 14px; }}
    QPushButton#primarySmall:hover {{ background: {t.accent_hover}; }}
    QToolButton#dot {{ border: 2px solid {t.border}; border-radius: 9px; background: {t.surface}; }}
    QToolButton#dot:hover {{ border-color: {t.accent}; }}
    QToolButton#dot:checked {{ border-color: {t.accent}; background: {t.accent}; }}
    QPushButton#pillAction {{ background: {t.accent_soft}; color: {t.accent}; border: none; border-radius: 14px;
                              padding: 5px 14px; }}
    QPushButton#pillAction:hover {{ background: {t.accent}; color: {t.on_accent}; }}
    QPushButton#pillAction:disabled {{ background: {t.sunken}; color: {t.muted}; }}
    QLabel#welcomeTitle {{ font-size: 20pt; font-weight: 700; }}
    QLabel#welcomeBody {{ color: {t.muted}; font-size: 11pt; }}
    QFrame#dropZone {{ border: 2px dashed {t.border}; border-radius: 22px; background: {t.surface}; }}
    QLabel#shortcutHint {{ color: {t.muted}; font-size: 9pt; }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QWidget#panel {{ background: {t.surface}; }}
    QLabel#muted {{ color: {t.muted}; }}
    QFrame#lineCard {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px; }}
    QFrame#lineCard:hover {{ border-color: {t.muted}; }}
    QFrame#lineCard[selected="true"] {{ border: 2px solid {t.accent}; background: {t.accent_soft}; }}
    QLabel#lineNumber {{ color: {t.muted}; font-size: 9pt; font-weight: 600; }}
    QLabel#badge {{ border-radius: 9px; padding: 1px 9px; font-size: 8pt; font-weight: 700; }}
    QLabel#lineImage {{ background: #FFFFFF; border-radius: 8px; padding: 2px; }}
    QLineEdit {{ background: {t.sunken}; border: 1px solid transparent; border-radius: 8px; padding: 6px 10px; }}
    QLineEdit:focus {{ border-color: {t.accent}; background: {t.surface}; }}

    QTabBar::tab {{ background: transparent; padding: 5px 12px; border-radius: 8px; color: {t.muted};
                    font-weight: 600; }}
    QTabBar::tab:selected {{ background: {t.sunken}; color: {t.text}; }}
    QTabBar::tab:hover:!selected {{ color: {t.text}; }}

    /* Footer */
    QFrame#footer {{ background: {t.surface}; border-top: 1px solid {t.border}; }}
    QLabel#footerText {{ color: {t.muted}; font-size: 9pt; }}
    QLabel#chip {{ background: {t.sunken}; color: {t.muted}; border-radius: 9px; padding: 2px 9px;
                   font-size: 9pt; }}

    /* Dialogs and controls */
    QComboBox {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 9px; padding: 6px 10px; }}
    QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border};
                                   selection-background-color: {t.sunken}; selection-color: {t.text}; }}
    QRadioButton, QCheckBox {{ spacing: 8px; padding: 4px 0; }}
    QGroupBox {{ border: 1px solid {t.border}; border-radius: 12px; margin-top: 16px; padding: 14px 12px 10px 12px;
                 background: {t.surface}; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 14px; right: 14px; padding: 0 6px; color: {t.muted};
                        font-weight: 600; }}
    QProgressDialog QProgressBar, QProgressBar {{ background: {t.sunken}; border: none; border-radius: 4px;
                                                  height: 8px; text-align: center; }}
    QProgressBar::chunk {{ background: {t.accent}; border-radius: 4px; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t.muted}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """
