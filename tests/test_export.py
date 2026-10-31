import numpy as np
import pymupdf
from PIL import Image, ImageDraw

from copticocr.export import coptic_text, to_docx, to_searchable_pdf, to_text
from copticocr.layout.projection import Box, remove_rules, split_columns
from copticocr.pipeline import Document, PageResult, TextLine

JINKIM = "̀"


def test_legacy_font_gets_converted_text():
    assert coptic_text(f"ⲛ{JINKIM}ⲧⲉ", "CS Avva Shenouda") == "`nte"
    assert coptic_text(f"ⲛ{JINKIM}ⲧⲉ", "Noto Sans Coptic") == f"ⲛ{JINKIM}ⲧⲉ"


def test_rules_between_columns_are_removed():
    ink = np.zeros((400, 600), dtype=bool)
    for x in range(40, 280, 40):       # words of the left column
        ink[50:350:20, x:x + 30] = True
    for x in range(320, 560, 40):      # and of the right column
        ink[50:350:20, x:x + 30] = True
    ink[20:380, 299:301] = True        # column rule
    ink[20:22, 20:580] = True          # frame
    assert split_columns(ink) is None
    left, right = split_columns(remove_rules(ink))
    assert left.x1 <= 300 <= right.x0


def page_result():
    lines = [TextLine(Box(20, 20, 380, 60), "coptic", f"ⲡⲉⲛⲓⲱⲧ ⲉⲧϧⲉⲛ ⲛⲓⲫⲏⲟⲩⲓ", [0.99]),
             TextLine(Box(20, 80, 380, 120), "arabic", "")]
    return PageResult((400, 200), lines)


def test_exports(tmp_path):
    image = Image.new("L", (400, 200), 255)
    ImageDraw.Draw(image).rectangle((20, 20, 380, 60), fill=0)
    image.save(tmp_path / "page.png", dpi=(300, 300))
    doc = Document.open(tmp_path / "page.png")
    results = [page_result()]

    to_text(results, tmp_path / "out.txt")
    assert (tmp_path / "out.txt").read_text(encoding="utf-8").strip() == "ⲡⲉⲛⲓⲱⲧ ⲉⲧϧⲉⲛ ⲛⲓⲫⲏⲟⲩⲓ"

    to_docx(results, tmp_path / "out.docx", "CS Avva Shenouda")
    import docx
    assert docx.Document(tmp_path / "out.docx").paragraphs[0].text == "peniwt etqen nivyoui"

    to_searchable_pdf(doc, results, tmp_path / "out.pdf")
    with pymupdf.open(tmp_path / "out.pdf") as pdf:
        assert pdf[0].search_for("ⲛⲓⲫⲏⲟⲩⲓ")
