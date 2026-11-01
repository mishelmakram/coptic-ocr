"""Choose what to export: format, Coptic font and pages."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QRadioButton, QVBoxLayout)

from ..export import UNICODE_FONT
from ..legacy import layouts
from .i18n import tr

FORMATS = [("book_pdf", "fmt_book_pdf", "PDF (*.pdf)"), ("book_docx", "fmt_book_docx", "Word (*.docx)"),
           ("typeset", "fmt_typeset", "PDF (*.pdf)"), ("pdf", "fmt_pdf", "PDF (*.pdf)"),
           ("docx", "fmt_docx", "Word (*.docx)"), ("txt", "fmt_txt", "Text (*.txt)")]
BOOK = ("book_pdf", "book_docx")
WORD = ("book_docx", "docx")


@dataclass
class ExportChoice:
    format: str
    file_filter: str
    coptic_font: str
    current_page_only: bool
    stanzas: bool = True
    rule: bool = False

    @property
    def suffix(self) -> str:
        return "docx" if self.format in WORD else "txt" if self.format == "txt" else "pdf"


def coptic_fonts() -> list[str]:
    """The bundled Unicode font first, then every legacy font family we can convert to."""
    fonts = [UNICODE_FONT]
    for layout in layouts().values():
        fonts += [f for f in layout.fonts if f not in fonts]
    return fonts


class ExportDialog(QDialog):
    def __init__(self, parent, pages_read: int):
        super().__init__(parent)
        self.setWindowTitle(tr("export_title"))
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        group = QGroupBox(tr("format"))
        box = QVBoxLayout(group)
        self.formats = QButtonGroup(self)
        for i, (_, key, _) in enumerate(FORMATS):
            button = QRadioButton(tr(key))
            button.setChecked(i == 0)
            self.formats.addButton(button, i)
            box.addWidget(button)
        hint = QLabel(tr("export_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        box.addWidget(hint)
        layout.addWidget(group)

        group = QGroupBox(tr("arrangement"))
        box = QVBoxLayout(group)
        self.by_stanza = QRadioButton(tr("by_stanza"))
        self.by_stanza.setChecked(True)
        box.addWidget(self.by_stanza)
        box.addWidget(QRadioButton(tr("by_line")))
        self.rule = QCheckBox(tr("column_rule"))
        box.addWidget(self.rule)
        self.arrangement_group = group
        layout.addWidget(group)

        group = QGroupBox(tr("coptic_font"))
        box = QVBoxLayout(group)
        self.font = QComboBox()
        installed = set(QFontDatabase.families())
        for name in coptic_fonts():
            label = name if name in installed or name == UNICODE_FONT else tr("font_missing", name)
            self.font.addItem(label, name)
        box.addWidget(self.font)
        self.font_group = group
        layout.addWidget(group)

        group = QGroupBox(tr("pages"))
        box = QVBoxLayout(group)
        self.all_pages = QRadioButton(tr("pages_read_only", pages_read))
        self.all_pages.setChecked(True)
        box.addWidget(self.all_pages)
        box.addWidget(QRadioButton(tr("pages_current")))
        layout.addWidget(group)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(tr("cancel"))
        cancel.clicked.connect(self.reject)
        save = QPushButton(tr("save"))
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        self.formats.idToggled.connect(self._update)
        self._update()

    def _update(self, *_) -> None:
        fmt = FORMATS[self.formats.checkedId()][0]
        self.arrangement_group.setEnabled(fmt in BOOK)
        self.font_group.setEnabled(fmt in WORD)  # PDFs set the Coptic in the bundled Unicode font

    def choice(self) -> ExportChoice:
        fmt, _, file_filter = FORMATS[self.formats.checkedId()]
        return ExportChoice(fmt, file_filter, self.font.currentData(), not self.all_pages.isChecked(),
                            self.by_stanza.isChecked(), self.rule.isChecked())
