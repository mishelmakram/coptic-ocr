import numpy as np
import pymupdf
from PIL import Image, ImageDraw

from copticocr.enhance import clean, outline_ops, to_enhanced_pdf
from copticocr.pipeline import Document


def page():
    """Grey, unevenly lit paper with letters, a small mark above one, and specks."""
    shade = np.linspace(200, 150, 1200)[None, :].repeat(800, 0)
    image = Image.fromarray(shade.astype(np.uint8))
    draw = ImageDraw.Draw(image)
    for x in range(100, 1100, 120):
        draw.rectangle((x, 300, x + 60, 380), fill=30)    # letters
    draw.rectangle((110, 270, 130, 280), fill=30)          # a jinkim-sized mark
    for x, y in [(400, 600), (700, 150), (900, 650)]:
        draw.point((x, y), fill=20)                         # specks
    return image


def test_clean_whitens_paper_keeps_marks_and_drops_specks():
    ink, factor = clean(page())
    assert factor == 2.0  # 1200 px wide: enlarged before tracing
    assert ink[int(340 * factor), int(130 * factor)]          # a letter
    assert ink[int(275 * factor), int(120 * factor)]          # the small mark stays
    assert not ink[int(600 * factor), int(400 * factor)]      # the speck is gone
    assert not ink[int(500 * factor), int(1150 * factor)]     # the dark side of the paper is paper


def test_outlines_fill_the_letters(tmp_path):
    ink = np.zeros((100, 200), dtype=bool)
    ink[20:80, 30:90] = True
    ink[40:60, 50:70] = False  # a counter, which must stay open
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, outline_ops(ink, 1.0, 100))
    page.set_contents(xref)
    pixels = page.get_pixmap(colorspace=pymupdf.csGRAY)
    gray = np.frombuffer(pixels.samples, np.uint8).reshape(pixels.h, pixels.w)
    assert gray[30, 40] < 50 and gray[50, 60] > 200 and gray[50, 150] > 200


def test_enhanced_pdf(tmp_path):
    page().save(tmp_path / "page.png")
    doc = Document.open(tmp_path / "page.png")
    assert to_enhanced_pdf(doc, [], tmp_path / "out.pdf", [0], workers=1)
    with pymupdf.open(tmp_path / "out.pdf") as pdf:
        assert not pdf[0].get_images()           # drawn as curves, no picture
        assert len(pdf[0].get_drawings()) >= 1
