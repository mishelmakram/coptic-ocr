"""Save recognized pages as plain text, a Word document or a searchable PDF.

Recognized text is Unicode. For Word, the Coptic can be set in any font: a
Unicode font keeps the text as is, a legacy font (CS Avva Shenouda,
Athanasius, ...) gets the text converted to that font's encoding.
"""

from __future__ import annotations

import html
from importlib import resources
from pathlib import Path

import numpy as np
import pymupdf

from .layout.projection import binarize, word_spans
from .legacy import layout_for_font
from .pipeline import Document, PageResult

UNICODE_FONT = "Noto Sans Coptic"
ARABIC_FONT = "Traditional Arabic"


def bundled_font(name: str = "NotoSansCoptic-Regular.ttf") -> Path:
    return Path(str(resources.files(__package__).joinpath("assets", "fonts", name)))


def coptic_text(text: str, font: str) -> str:
    """``text`` as it must be stored to show correctly in ``font``."""
    layout = layout_for_font(font)
    return layout.from_unicode(text, errors="replace") if layout else text


def page_paragraphs(result: PageResult, script: str) -> list[str]:
    return [line.text for line in result.lines if line.script == script and line.text.strip()]


def to_text(results: list[PageResult | None], path: Path) -> None:
    pages = []
    for result in results:
        if result is not None:
            pages.append("\n".join(page_paragraphs(result, "coptic") + page_paragraphs(result, "arabic")))
    path.write_text("\n\n".join(pages) + "\n", encoding="utf-8")


def to_docx(results: list[PageResult | None], path: Path, coptic_font: str = UNICODE_FONT,
            size: float = 14) -> None:
    import docx
    from docx.enum.text import WD_BREAK
    from docx.oxml.ns import qn
    from docx.shared import Pt

    document = docx.Document()
    style = document.styles["Normal"]
    style.font.name = coptic_font
    style.font.size = Pt(size)
    first = True
    for result in results:
        if result is None:
            continue
        if not first:
            document.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)
        first = False
        for text in page_paragraphs(result, "coptic"):
            run = document.add_paragraph().add_run(coptic_text(text, coptic_font))
            run.font.name = coptic_font
            # Word picks the font per character class; set it for all of them.
            fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
            for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                fonts.set(qn(attr), coptic_font)
        for text in page_paragraphs(result, "arabic"):
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.right_to_left = True
            run = paragraph.add_run(text)
            run.font.rtl = True
            run.font.name = ARABIC_FONT
    if first:
        document.add_paragraph()
    document.save(path)


def to_searchable_pdf(doc: Document, results: list[PageResult | None], path: Path) -> None:
    """The original pages with the recognized text laid invisibly over each line.

    Pages that were not recognized are copied without text.
    """
    out = pymupdf.open()
    sources: dict[Path, pymupdf.Document] = {}
    try:
        for index, result in enumerate(results):
            source, number = doc.source(index)
            if source.suffix.lower() == ".pdf":
                src = sources.get(source) or sources.setdefault(source, pymupdf.open(source))
                out.insert_pdf(src, from_page=number, to_page=number)
                page = out[-1]
            else:
                image = doc.page_image(index)
                dpi = _dpi(source)
                page = out.new_page(width=image.width * 72 / dpi, height=image.height * 72 / dpi)
                if number == 0:
                    page.insert_image(page.rect, filename=str(source))  # keeps the file's own compression
                else:
                    page.insert_image(page.rect, pixmap=_pixmap(image))
            if result is not None:
                add_hidden_text(page, result, doc.page_image(index))
        out.save(path, garbage=3, deflate=True)
    finally:
        out.close()
        for src in sources.values():
            src.close()


def add_hidden_text(page: pymupdf.Page, result: PageResult, image) -> None:
    """Lay the recognized Coptic invisibly over its print, word by word where the words can be told apart."""
    font_file = bundled_font()
    font = pymupdf.Font(fontfile=str(font_file))
    page.insert_font(fontname="coptic", fontfile=str(font_file))
    scale = page.rect.width / result.size[0]
    ink = binarize(np.asarray(image.convert("L")))
    for line in result.lines:
        if line.script != "coptic" or not line.text.strip():
            continue
        height = line.box.height * scale
        words = line.text.split()
        # Each word over its printed word, so selecting a word in the scan copies that word.
        spans = word_spans(ink, line.box, len(words))
        if spans is None:
            words, spans = [line.text], [(line.box.x0, line.box.x1)]
        for word, (x0, x1) in zip(words, spans):
            width = (x1 - x0) * scale
            size = min(width / max(font.text_length(word, 1), 1e-3), height)
            baseline = pymupdf.Point(x0 * scale, line.box.y1 * scale - 0.15 * height)
            page.insert_text(baseline, word, fontname="coptic", fontsize=size, render_mode=3)


def page_size(doc: Document, index: int, image) -> tuple[float, float]:
    """Size in points of page ``index``: the original PDF page, or the image at its resolution."""
    source, number = doc.source(index)
    if source.suffix.lower() == ".pdf":
        with pymupdf.open(source) as src:
            rect = src[number].rect
        return rect.width, rect.height
    dpi = _dpi(source)
    return image.width * 72 / dpi, image.height * 72 / dpi


def typeset_page(out: pymupdf.Document, image, result: PageResult, size: tuple[float, float]) -> pymupdf.Page:
    """Add a page where every recognized Coptic line is set in type where it was printed.

    Everything else on the page (Arabic, verse numbers, running heads) is kept from
    the scan, as an image, until it can be recognized too.
    """
    from PIL import ImageDraw

    background = image.convert("L").copy()
    paper = int(np.percentile(np.asarray(background), 90))  # photos and old scans are not white
    draw = ImageDraw.Draw(background)
    lines = [line for line in result.lines if line.script == "coptic" and line.text.strip()]
    for line in lines:
        b = line.box
        draw.rectangle((b.x0 - 3, b.y0 - 3, b.x1 + 3, b.y1 + 3), fill=paper)
    page = out.new_page(width=size[0], height=size[1])
    page.insert_image(page.rect, pixmap=_pixmap(background))
    if not lines:
        return page
    scale = page.rect.width / result.size[0]
    archive = pymupdf.Archive(str(bundled_font().parent))
    # One size for the page, from a typical line; a line's box height varies with its marks.
    size = sorted(line.box.height for line in lines)[len(lines) // 2] * scale * 0.7
    css = (f"@font-face {{font-family: coptic; src: url({bundled_font().name});}} "
           f"* {{font-family: coptic; font-size: {size:.2f}px; white-space: nowrap; margin: 0; "
           f"line-height: 1.3;}}")
    for line in lines:
        b = line.box
        # The box bottom is close to the baseline; hang the type from there.
        bottom = b.y1 * scale + size * 0.3
        rect = pymupdf.Rect(b.x0 * scale, bottom - size * 1.3, max(b.x1 * scale, b.x0 * scale + size), bottom)
        page.insert_htmlbox(rect, html.escape(line.text), css=css, archive=archive, scale_low=0)
    return page


def to_typeset_pdf(doc: Document, results: list[PageResult | None], path: Path) -> None:
    """A new PDF of the pages read, with their Coptic set in type (see ``typeset_page``)."""
    out = pymupdf.open()
    try:
        for index, result in enumerate(results):
            if result is not None:
                image = doc.page_image(index)
                typeset_page(out, image, result, page_size(doc, index, image))
        out.save(path, garbage=3, deflate=True)
    finally:
        out.close()


def _dpi(path: Path) -> float:
    from PIL import Image

    with Image.open(path) as img:
        dpi = img.info.get("dpi", (300, 300))[0]
    return float(dpi) if dpi and dpi > 30 else 300.0


def _pixmap(image) -> pymupdf.Pixmap:
    import io

    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return pymupdf.Pixmap(buffer.getvalue())
