import pymupdf
from PIL import Image, ImageDraw

from copticocr.book import to_docx_book, to_pdf_book
from copticocr.layout.projection import Box
from copticocr.pipeline import Document, PageResult, TextLine
from copticocr.structure import join_lines, line_rows, stanza_rows

NBSP = " "


def test_join_lines_mends_hyphenated_words_and_keeps_colons_with_words():
    assert join_lines(["ⲫⲏⲉⲧⲁϥ-", "ⲧⲁϫⲣⲟⲛ ϧⲉⲛ ⲡⲓⲛⲁϩϯ :", "ⲛ̀ⲟⲣⲑⲟⲇⲟⲝⲟⲥ ."]) == \
        f"ⲫⲏⲉⲧⲁϥⲧⲁϫⲣⲟⲛ ϧⲉⲛ ⲡⲓⲛⲁϩϯ{NBSP}: ⲛ̀ⲟⲣⲑⲟⲇⲟⲝⲟⲥ{NBSP}."


def coptic(y, x0=100, text="ⲡⲉⲛⲓⲱⲧ ⲉⲧϧⲉⲛ"):
    return TextLine(Box(x0, y, 380, y + 30), "coptic", text, [0.99] * 10, column=0)


def arabic(y):
    return TextLine(Box(420, y, 600, y + 30), "arabic", column=1)


def page():
    """A title across both columns, then two stanzas of two lines each."""
    lines = [TextLine(Box(250, 20, 400, 50), "arabic", column=0), TextLine(Box(420, 20, 500, 50), "arabic", column=1)]
    for y, x0 in [(100, 140), (150, 100), (200, 140), (250, 100)]:  # indented stanza starts
        lines += [coptic(y, x0), arabic(y + 4)]
    return PageResult((640, 320), lines)


def test_lines_pair_into_rows_and_rows_into_stanzas():
    rows = line_rows(page())
    assert rows[0].is_title and len(rows[0].title) == 2
    assert [(len(r.coptic), len(r.arabic)) for r in rows[1:]] == [(1, 1)] * 4
    stanzas = stanza_rows(page())
    assert stanzas[0].is_title
    assert [(len(r.coptic), len(r.arabic)) for r in stanzas[1:]] == [(2, 2), (2, 2)]


def test_book_exports(tmp_path):
    image = Image.new("L", (640, 320), 255)
    draw = ImageDraw.Draw(image)
    for line in page().lines:
        b = line.box
        draw.rectangle((b.x0, b.y0 + 8, b.x1, b.y1 - 8), fill=0)
    image.save(tmp_path / "page.png", dpi=(72, 72))
    doc = Document.open(tmp_path / "page.png")

    to_pdf_book(doc, [page()], tmp_path / "book.pdf")
    with pymupdf.open(tmp_path / "book.pdf") as pdf:
        assert pdf[0].get_text().count("ⲡⲉⲛⲓⲱⲧ") == 4
        assert len(pdf[0].get_images()) == 5  # the title and the four Arabic lines, as pictures for now

    to_docx_book(doc, [page()], tmp_path / "book.docx", "CS Avva Shenouda")
    import docx
    table = docx.Document(tmp_path / "book.docx").tables[0]
    assert len(table.rows) == 3
    assert table.rows[1].cells[0].text == "peniwt etqen peniwt etqen"
