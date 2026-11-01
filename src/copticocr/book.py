"""Re-set read pages as a bilingual book: a table with Coptic on the left, Arabic on the right
(and the Coptic in Arabic letters between them, where the book prints it).

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

from .export import UNICODE_FONT, arabic_pdf_font, bundled_font, coptic_text, page_size
from .layout.projection import binarize, remove_rules
from .pipeline import Document, PageResult, TextLine, crop
from .structure import Row, line_rows, stanza_rows

FONT_SIZE = 14  # points, for the Coptic text
ARABIC_FONT = "Simplified Arabic"  # on every Windows; Arabic type runs smaller than Coptic at one size

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
ARABIC_INK = 1.09  # height of a line of Arabic, dots and marks included, in the PDF's font, per point


def _line_height(result: PageResult) -> float:
    """Typical height in pixels of a printed Coptic line."""
    heights = [l.box.height for l in result.lines if l.script == "coptic" and l.text.strip()]
    return float(np.median(heights or [l.box.height for l in result.lines] or [40]))


def _points_per_pixel(result: PageResult, font_size: float = FONT_SIZE) -> float:
    """Scale for pictures cut from the scan, so their letters match Coptic type of ``font_size``."""
    return font_size / (TYPE_TO_LINE * _line_height(result))


def _three_columns(result: PageResult) -> bool:
    return any(line.transliterated for line in result.lines)


def _column_shares(result: PageResult) -> list[float]:
    """Share of the text width each column takes on the page: Coptic, (Coptic in Arabic letters,)
    Arabic."""
    def width(lines: list[TextLine]) -> int:
        return max(l.box.x1 for l in lines) - min(l.box.x0 for l in lines) if lines else 0

    coptic = [l for l in result.lines if l.script == "coptic"]
    if _three_columns(result):
        middle = [l for l in result.lines if l.transliterated]
        arabic = [l for l in result.lines if l.script == "arabic" and not l.transliterated
                  and l.column > min(m.column for m in middle)]
        widths = [max(width(part), 1) for part in (coptic, middle, arabic)]
        shares = [max(0.22, w / sum(widths)) for w in widths]
        return [share / sum(shares) for share in shares]

    def column_width(column: int) -> int:
        return width([l for l in result.lines if l.column == column])
    left, right = column_width(0), column_width(1)
    share = min(0.75, max(0.45, left / (left + right))) if left and right else 0.6
    return [share, 1 - share]


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
        shares = _column_shares(result)
        widths = [int(usable * share) for share in shares]
        widths[-1] = usable - sum(widths[:-1])

        table = document.add_table(rows=0, cols=len(widths))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        _set_borders(table, rule)
        for row in page_rows(result, stanzas):
            cells = table.add_row().cells
            for cell, width in zip(cells, widths):
                cell.width = width
            if row.is_title:
                cell = cells[0].merge(cells[-1])
                paragraph = cell.paragraphs[0]
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                paragraph.paragraph_format.space_after = Pt(6)
                if row.title_text:
                    _arabic_run(paragraph, row.title_text, FONT_SIZE * 1.15, bold=True)
                else:
                    _add_picture(paragraph, crop(image, _title_box(row)), scale, usable)
                continue
            if row.coptic:
                paragraph = cells[0].paragraphs[0]
                paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                paragraph.paragraph_format.space_after = Pt(8)
                _coptic_run(paragraph, coptic_text(row.coptic_text, coptic_font), coptic_font)
            parts = [(row.arabic, row.arabic_text, len(cells) - 1)]
            if len(cells) == 3:
                parts.append((row.middle, row.middle_text, 1))
            for lines, text, k in parts:
                if text:
                    paragraph = cells[k].paragraphs[0]
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    paragraph.paragraph_format.right_to_left = True
                    paragraph.paragraph_format.space_after = Pt(8)
                    _arabic_run(paragraph, text, FONT_SIZE)  # Word lays it out; a reading size
                    continue
                for n, line in enumerate(lines):
                    paragraph = cells[k].paragraphs[0] if n == 0 else cells[k].add_paragraph()
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    paragraph.paragraph_format.right_to_left = True
                    _add_picture(paragraph, crop(image, line.box), scale, widths[k])
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


def _arabic_run(paragraph, text: str, size: float, bold: bool = False) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    run = paragraph.add_run(text)
    run.font.rtl = True
    run.font.size = Pt(size)
    run.font.bold = bold
    properties = run._element.get_or_add_rPr()
    fonts = properties.get_or_add_rFonts()
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        fonts.set(qn(attr), ARABIC_FONT)
    for tag in ("w:szCs",) + (("w:bCs",) if bold else ()):  # Word sizes right-to-left text separately
        element = OxmlElement(tag)
        if tag == "w:szCs":
            element.set(qn("w:val"), str(round(size * 2)))
        properties.append(element)


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
    arabic_file = arabic_pdf_font()
    arabic_archive = pymupdf.Archive(str(arabic_file.parent)) if arabic_file else None
    out = pymupdf.open()
    scratch = pymupdf.open()
    ruler = scratch.new_page(width=1000, height=10000)

    def measure(html_text: str, w: float, style: str, fonts: pymupdf.Archive) -> float:
        """Height the HTML takes when laid out ``w`` points wide."""
        ruler.clean_contents()
        spare, _ = ruler.insert_htmlbox(pymupdf.Rect(0, 0, w, 10000), html_text, css=style, archive=fonts)
        return 10000 - spare

    def baseline(html_text: str, w: float, style: str, fonts: pymupdf.Archive) -> float:
        """How far below its box's top the first line of the HTML sits (its baseline)."""
        with pymupdf.open() as fresh:  # the ruler page keeps the text of earlier measurements
            page = fresh.new_page(width=w + 10, height=10000)
            page.insert_htmlbox(pymupdf.Rect(0, 0, w, 10000), html_text, css=style, archive=fonts)
            blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            for line in block.get("lines", []):
                return line["spans"][0]["origin"][1]
        return 0.0
    try:
        for index, result in enumerate(results):
            if result is None:
                continue
            original = doc.page_image(index)
            width, height = page_size(doc, index, original)
            image = clean_page(original)
            margin = min(width, height) * 0.08
            area = pymupdf.Rect(margin, margin, width - margin, height - margin)
            # Column edges: Coptic, (Coptic in Arabic letters,) Arabic.
            edges = [area.x0]
            for share in _column_shares(result):
                edges.append(edges[-1] + area.width * share)
            cells = [(edges[k] + (GUTTER if k else 0), edges[k + 1] - (GUTTER if k < len(edges) - 2 else 0))
                     for k in range(len(edges) - 1)]
            coptic_cell = cells[0]
            # The parts in Arabic letters, right to left in their cells: (lines, text, cell).
            def arabic_parts(row: Row) -> list[tuple[list[TextLine], str | None, tuple[float, float]]]:
                parts = [(row.arabic, row.arabic_text, cells[-1])]
                if len(cells) == 3:
                    parts.append((row.middle, row.middle_text, cells[1]))
                return parts

            # The book's own proportions: pictures at their printed size, type as large as the print.
            scale = width / original.width
            size = TYPE_TO_LINE * _line_height(result) * scale
            css = (f"@font-face {{font-family: coptic; src: url({font.name});}} "
                   f"* {{font-family: coptic; font-size: {size:.1f}pt; line-height: {LINE_SPACING}; "
                   "margin: 0; text-align: justify;}")
            rows = page_rows(result, stanzas)
            arabic_css = None
            if arabic_file is not None:
                def arabic_style(points: float) -> str:
                    return (f"@font-face {{font-family: arabic; src: url({arabic_file.name});}} "
                            f"* {{font-family: arabic; font-size: {points:.1f}pt; line-height: {LINE_SPACING}; "
                            "margin: 0; text-align: justify;} p.title {text-align: center; font-weight: bold;}")

                # As large as the book prints it (from the height of its lines), made smaller only
                # where a stanza would take more lines than the book gave it.
                texts = [(text, len(lines), cell) for row in rows if not row.is_title
                         for lines, text, cell in arabic_parts(row) if text]
                fitted = arabic_size(result, scale, size, texts, arabic_style, measure, arabic_archive)
                arabic_css = arabic_style(fitted)
            page, y = out.new_page(width=width, height=height), area.y0

            def room(needed: float) -> None:
                nonlocal page, y
                if y + needed > area.y1 and y > area.y0:
                    page, y = out.new_page(width=width, height=height), area.y0

            for row in rows:
                if row.is_title and row.title_text and arabic_css:
                    body = f'<p class="title" dir="rtl">{html.escape(row.title_text)}</p>'
                    h = measure(body, area.width, arabic_css, arabic_archive)
                    room(h)
                    page.insert_htmlbox(pymupdf.Rect(area.x0, y, area.x1, y + h + 2), body, css=arabic_css,
                                        archive=arabic_archive)
                    y += h + ROW_GAP / 2
                    continue
                if row.is_title:
                    picture = crop(image, row.box)
                    w, h = _fit(picture, scale, area.width)
                    room(h)
                    left = area.x0 + (area.width - w) / 2
                    page.insert_image(pymupdf.Rect(left, y, left + w, y + h), stream=_png(picture))
                    y += h + ROW_GAP / 2
                    continue
                text = html.escape(row.coptic_text)
                coptic_width = coptic_cell[1] - coptic_cell[0]
                text_height = measure(text, coptic_width, css, archive) if text else 0.0
                coptic_base = None  # measured once, when a part stands on it
                placed = []  # (cell, body or None, pictures and sizes, height, shift)
                for lines, part_text, cell in arabic_parts(row):
                    cell_width = cell[1] - cell[0]
                    if part_text and arabic_css:
                        body = f'<p dir="rtl">{html.escape(part_text)}</p>'
                        part_height = measure(body, cell_width, arabic_css, arabic_archive)
                        # Stand the first line on the first Coptic line's baseline, as the book does:
                        # Arabic fonts leave more room above a line, which would set it lower.
                        shift = 0.0
                        if text:
                            if coptic_base is None:
                                coptic_base = baseline(text, coptic_width, css, archive)
                            shift = coptic_base - baseline(body, cell_width, arabic_css, arabic_archive)
                        placed.append((cell, body, [], part_height, shift))
                    else:
                        pictures = [crop(image, line.box) for line in lines]
                        sizes = [_fit(picture, scale, cell_width) for picture in pictures]
                        placed.append((cell, None, list(zip(pictures, sizes)), sum(h for _, h in sizes), 0.0))
                row_height = max([text_height] + [h + shift for _, _, _, h, shift in placed])
                room(row_height)
                if text:
                    page.insert_htmlbox(pymupdf.Rect(coptic_cell[0], y, coptic_cell[1], y + text_height + 2), text,
                                        css=css, archive=archive)
                for cell, body, pictures, part_height, shift in placed:
                    top = y + shift
                    if body:
                        page.insert_htmlbox(pymupdf.Rect(cell[0], top, cell[1], top + part_height + 2), body,
                                            css=arabic_css, archive=arabic_archive)
                    for picture, (w, h) in pictures:
                        page.insert_image(pymupdf.Rect(cell[1] - w, top, cell[1], top + h), stream=_png(picture))
                        top += h
                if rule:
                    for edge in edges[1:-1]:
                        page.draw_line((edge, y - ROW_GAP / 2), (edge, y + row_height + ROW_GAP / 2), width=0.8)
                y += row_height + ROW_GAP
        if not out.page_count:
            out.new_page()
        out.subset_fonts()  # embed only the letters used, not whole fonts
        out.save(path, garbage=3, deflate=True)
    finally:
        out.close()
        scratch.close()


def arabic_size(result: PageResult, scale: float, coptic_size: float, texts, style, measure, fonts) -> float:
    """Type size for the Arabic of a page: its printed size, or less where a stanza's text,
    ``(text, printed lines, cell)``, would not fit in its printed lines."""
    heights = [l.box.height for l in result.lines if l.script == "arabic" and l.text.strip()]
    printed = float(np.median(heights)) * scale / ARABIC_INK if heights else coptic_size
    points = float(np.clip(printed, coptic_size * 0.6, coptic_size * 1.3))
    while points > coptic_size * 0.6:
        css = style(points)
        # A paragraph of one line, with the room the engine leaves around it; each further
        # line adds a line's height.
        one = measure('<p dir="rtl">ا</p>', 1000, css, fonts)
        if all(measure(f'<p dir="rtl">{html.escape(text)}</p>', cell[1] - cell[0], css, fonts)
               <= one + (count - 0.8) * points * LINE_SPACING for text, count, cell in texts):
            break
        points -= coptic_size * 0.05
    return points


def _fit(picture, scale: float, room: float) -> tuple[float, float]:
    """Size in points of a picture cut from the scan, shrunk if it is wider than ``room``."""
    w, h = picture.width * scale, picture.height * scale
    return (room, h * room / w) if w > room else (w, h)
