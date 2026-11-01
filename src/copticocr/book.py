"""Re-set read pages as a bilingual book: a table with Coptic on the left, Arabic on the right.

Each row of the table holds a stanza (or a printed line, see ``structure``);
titles span both columns. The table itself is invisible, unless a rule between
the columns is asked for. Arabic is not read yet, so its lines are placed as
pictures cut from the scan; they become text once Arabic can be recognized.
"""

from __future__ import annotations

import html
import io
from pathlib import Path

import numpy as np
import pymupdf

from .export import UNICODE_FONT, bundled_font, coptic_text, page_size
from .layout.projection import binarize, remove_rules
from .pipeline import Document, PageResult, TextLine, crop
from .structure import Row, line_rows, stanza_rows

FONT_SIZE = 14  # points, for the Coptic text
LINE_SPACING = 1.35


def page_rows(result: PageResult, stanzas: bool) -> list[Row]:
    return stanza_rows(result) if stanzas else line_rows(result)


def clean_page(image):
    """The scan with frames and column rules removed and the paper made white, for cutting pictures."""
    from PIL import Image

    gray = np.asarray(image.convert("L"), dtype=np.float32)
    ink = binarize(gray.astype(np.uint8))
    gray[ink & ~remove_rules(ink)] = 255
    paper = max(float(np.percentile(gray, 90)), 1.0)
    dark = float(np.percentile(gray, 1))
    level = np.clip((gray - dark) / max(paper - dark, 1.0), 0, 1) * 255
    return Image.fromarray(level.astype(np.uint8))


def _png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


TYPE_TO_LINE = 0.7  # type size for a printed line of this height (the line's box includes its marks)


def _line_height(result: PageResult) -> float:
    """Typical height in pixels of a printed Coptic line."""
    heights = [l.box.height for l in result.lines if l.script == "coptic" and l.text.strip()]
    return float(np.median(heights or [l.box.height for l in result.lines] or [40]))


def _points_per_pixel(result: PageResult, font_size: float = FONT_SIZE) -> float:
    """Scale for pictures cut from the scan, so their letters match Coptic type of ``font_size``."""
    return font_size / (TYPE_TO_LINE * _line_height(result))


def _column_share(result: PageResult) -> float:
    """Share of the text width the Coptic column takes on the page."""
    def width(column: int) -> int:
        boxes = [l.box for l in result.lines if l.column == column]
        return max(b.x1 for b in boxes) - min(b.x0 for b in boxes) if boxes else 0
    left, right = width(0), width(1)
    return min(0.75, max(0.45, left / (left + right))) if left and right else 0.6


def _title_box(row: Row):
    return row.box


# Word -----------------------------------------------------------------------

def to_docx_book(doc: Document, results: list[PageResult | None], path: Path,
                 coptic_font: str = UNICODE_FONT, stanzas: bool = True, rule: bool = False) -> None:
    import docx
    from docx.enum.section import WD_SECTION
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    document = docx.Document()
    section = document.sections[0]
    section.left_margin = section.right_margin = Cm(2)
    section.top_margin = section.bottom_margin = Cm(2)
    usable = section.page_width - section.left_margin - section.right_margin
    normal = document.styles["Normal"]
    normal.font.size = Pt(FONT_SIZE)
    normal.paragraph_format.space_after = Pt(0)

    first = True
    for index, result in enumerate(results):
        if result is None:
            continue
        if not first:
            document.add_section(WD_SECTION.NEW_PAGE)
        first = False
        image = clean_page(doc.page_image(index))
        scale = _points_per_pixel(result)
        share = _column_share(result)
        widths = (int(usable * share), usable - int(usable * share))

        table = document.add_table(rows=0, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        _set_borders(table, rule)
        for row in page_rows(result, stanzas):
            cells = table.add_row().cells
            for cell, width in zip(cells, widths):
                cell.width = width
            if row.is_title:
                cell = cells[0].merge(cells[1])
                paragraph = cell.paragraphs[0]
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                paragraph.paragraph_format.space_after = Pt(6)
                _add_picture(paragraph, crop(image, _title_box(row)), scale, usable)
                continue
            if row.coptic:
                paragraph = cells[0].paragraphs[0]
                paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                paragraph.paragraph_format.space_after = Pt(8)
                _coptic_run(paragraph, coptic_text(row.coptic_text, coptic_font), coptic_font)
            for k, line in enumerate(row.arabic):
                paragraph = cells[1].paragraphs[0] if k == 0 else cells[1].add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                paragraph.paragraph_format.right_to_left = True
                _add_picture(paragraph, crop(image, line.box), scale, widths[1])
    if first:
        document.add_paragraph()
    document.save(path)


def _coptic_run(paragraph, text: str, font: str) -> None:
    from docx.oxml.ns import qn

    run = paragraph.add_run(text)
    run.font.name = font
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):  # Word picks a font per character class
        fonts.set(qn(attr), font)


def _add_picture(paragraph, image, points_per_pixel: float, max_width) -> None:
    from docx.shared import Emu, Pt

    height = Pt(image.height * points_per_pixel)
    width = Pt(image.width * points_per_pixel)
    run = paragraph.add_run()
    if width > max_width * 0.96:
        run.add_picture(io.BytesIO(_png(image)), width=Emu(int(max_width * 0.96)))
    else:
        run.add_picture(io.BytesIO(_png(image)), height=height)


def _set_borders(table, rule: bool) -> None:
    """No borders, or only the rule between the columns as many books print it."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    properties = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        if edge == "insideV" and rule:
            element.set(qn("w:val"), "single")
            element.set(qn("w:sz"), "8")
            element.set(qn("w:color"), "000000")
        else:
            element.set(qn("w:val"), "nil")
        borders.append(element)
    properties.append(borders)


# PDF ------------------------------------------------------------------------

GUTTER = 10  # points between a column's text and the rule
ROW_GAP = 8  # points between stanzas


def to_pdf_book(doc: Document, results: list[PageResult | None], path: Path, stanzas: bool = True,
                rule: bool = False) -> None:
    """The same layout as a PDF: Coptic set in type on the left, Arabic on the right.

    Each row is placed by hand, so the two columns of a stanza always start level;
    a row that does not fit goes to the next page.
    """
    font = bundled_font()
    archive = pymupdf.Archive(str(font.parent))
    out = pymupdf.open()
    scratch = pymupdf.open()
    ruler = scratch.new_page(width=1000, height=10000)
    try:
        for index, result in enumerate(results):
            if result is None:
                continue
            original = doc.page_image(index)
            width, height = page_size(doc, index, original)
            image = clean_page(original)
            margin = min(width, height) * 0.08
            area = pymupdf.Rect(margin, margin, width - margin, height - margin)
            divider = area.x0 + area.width * _column_share(result)
            # The book's own proportions: pictures at their printed size, type as large as the print.
            scale = width / original.width
            size = TYPE_TO_LINE * _line_height(result) * scale
            css = (f"@font-face {{font-family: coptic; src: url({font.name});}} "
                   f"* {{font-family: coptic; font-size: {size:.1f}pt; line-height: {LINE_SPACING}; "
                   "margin: 0; text-align: justify;}")
            page, y = out.new_page(width=width, height=height), area.y0

            def room(needed: float) -> None:
                nonlocal page, y
                if y + needed > area.y1 and y > area.y0:
                    page, y = out.new_page(width=width, height=height), area.y0

            for row in page_rows(result, stanzas):
                if row.is_title:
                    picture = crop(image, row.box)
                    w, h = _fit(picture, scale, area.width)
                    room(h)
                    left = area.x0 + (area.width - w) / 2
                    page.insert_image(pymupdf.Rect(left, y, left + w, y + h), stream=_png(picture))
                    y += h + ROW_GAP / 2
                    continue
                text = html.escape(row.coptic_text)
                coptic_width = divider - GUTTER - area.x0
                text_height = 0.0
                if text:
                    ruler.clean_contents()
                    spare, _ = ruler.insert_htmlbox(pymupdf.Rect(0, 0, coptic_width, 10000), text, css=css,
                                                    archive=archive)
                    text_height = 10000 - spare
                pictures = [crop(image, line.box) for line in row.arabic]
                sizes = [_fit(p, scale, area.x1 - divider - GUTTER) for p in pictures]
                row_height = max(text_height, sum(h for _, h in sizes))
                room(row_height)
                if text:
                    page.insert_htmlbox(pymupdf.Rect(area.x0, y, divider - GUTTER, y + text_height + 2), text,
                                        css=css, archive=archive)
                top = y
                for picture, (w, h) in zip(pictures, sizes):
                    page.insert_image(pymupdf.Rect(area.x1 - w, top, area.x1, top + h), stream=_png(picture))
                    top += h
                if rule:
                    page.draw_line((divider, y - ROW_GAP / 2), (divider, y + row_height + ROW_GAP / 2), width=0.8)
                y += row_height + ROW_GAP
        if not out.page_count:
            out.new_page()
        out.save(path, garbage=3, deflate=True)
    finally:
        out.close()
        scratch.close()


def _fit(picture, scale: float, room: float) -> tuple[float, float]:
    """Size in points of a picture cut from the scan, shrunk if it is wider than ``room``."""
    w, h = picture.width * scale, picture.height * scale
    return (room, h * room / w) if w > room else (w, h)
