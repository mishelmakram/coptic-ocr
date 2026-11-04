import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFilter

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


def strokes(ink_levels):
    """White paper with a row of 6 px strokes 40 px tall, each printed at its own darkness."""
    image = Image.new("L", (900, 300), 235)
    draw = ImageDraw.Draw(image)
    for k, level in enumerate(ink_levels):
        for x in range(60 + 200 * k, 200 + 200 * k, 20):
            draw.rectangle((x, 130, x + 5, 169), fill=level)
    return image


def test_faded_print_comes_out_whole_and_no_bolder():
    image = strokes([20, 110, 160])  # dark, faded, very faded (a third as dark)
    for level in (1, 2, 3):
        ink, factor = clean(image, level)
        for k in range(3):
            x = 60 + 200 * k
            row = ink[int(150 * factor), int((x - 7) * factor):int((x + 13) * factor)]
            assert abs(row.sum() / factor - 6) <= 1.5, (level, k)   # each stroke 6 px, as printed
            assert ink[int(131 * factor):int(168 * factor), int((x + 3) * factor)].all()  # unbroken


def test_levels_keep_thick_strokes_solid():
    image = Image.new("L", (1000, 600), 240)
    ImageDraw.Draw(image).rectangle((100, 200, 900, 260), fill=20)  # a heavy rule or bold stroke
    for level in (1, 2, 3):
        ink, factor = clean(image, level)
        assert ink[int(230 * factor), int(150 * factor):int(850 * factor)].all(), level  # not hollowed


def test_pale_frames_stay_paper():
    """The light grey boxes of a web page or a modern book are not faded print."""
    image = Image.new("L", (900, 400), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 860, 360), outline=228, width=2)   # a pale frame
    draw.rectangle((880, 0, 899, 399), fill=230)                # a pale band at the edge
    for x in range(100, 800, 20):
        draw.rectangle((x, 180, x + 5, 219), fill=40)            # the print
    ink, factor = clean(image, 1)
    assert ink[int(200 * factor), int(103 * factor)]
    assert not ink[int(41 * factor), int(400 * factor)] and not ink[int(200 * factor), int(890 * factor)]


def test_the_eye_of_a_small_blurred_letter_stays_open():
    """On a small scan the eye of ق or و is a pixel or two wide and never comes out as white as
    the paper; it must not be filled in."""
    image = Image.new("L", (300, 120), 245)
    draw = ImageDraw.Draw(image)
    for x in range(40, 260, 40):
        draw.ellipse((x, 50, x + 9, 59), fill=20)         # a small round letter
        draw.rectangle((x + 4, 54, x + 5, 55), fill=245)  # its eye, 2 px
    for x in range(20, 280, 9):
        draw.rectangle((x, 90, x + 5, 100), fill=20)      # more print, so the page has a letter size
    image = image.filter(ImageFilter.GaussianBlur(1.0))
    ink, factor = clean(image, 1)
    for x in range(40, 260, 40):
        assert ink[int(51 * factor), int((x + 4.5) * factor)]          # the ring
        assert not ink[round(55 * factor), round((x + 5) * factor)], x  # its eye
