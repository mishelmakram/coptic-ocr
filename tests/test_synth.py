import random
import unicodedata
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from copticocr.data.corpus import clean_word, is_coptic_letter
from copticocr.synth.degrade import degrade
from copticocr.synth.render import LineSampler, discover_fonts, render_line

ROOT = Path(__file__).resolve().parents[1]
JINKIM = "̀"

VERSES = [
    "ϧⲉⲛⲟⲩⲁⲣⲭⲏ ⲁ̀ ⲫⲛⲟⲩϯ ⲑⲁⲙⲓⲟ ⲛ̀ⲧ̀ⲫⲉ ⲛⲉⲙⲡ̀ⲕⲁϩⲓ",
    "ⲟⲩⲟϩ ⲁ̀ ⲫⲛⲟⲩϯ ⲥ̀ⲙⲟⲩ ⲉ̀ⲣⲟⲩ ⲉϥϫⲱ ⲙ̀ⲙⲟⲥ",
]


def test_clean_word():
    assert clean_word("[ⲛ̀ⲧⲉ]") == "ⲛ̀ⲧⲉ"
    assert clean_word(JINKIM + "ⲁ") == "ⲁ"
    assert clean_word("…'") == ""


def test_sampler_lines_come_from_the_corpus():
    sampler = LineSampler(VERSES, random.Random(3))
    words = {w for v in VERSES for w in v.split()}
    for _ in range(200):
        line = sampler.sample()
        assert line and not unicodedata.combining(line[0])
        for word in line.rstrip(" :.").split():
            word = word.rstrip(":.")
            if word.endswith("-"):
                assert any(w.startswith(word[:-1]) for w in words), word
            else:
                assert word.lower() in words or word in words, word


def test_sampler_never_capitalises_a_marked_letter():
    sampler = LineSampler(["ⲁ̀ ⲛ̀ⲧⲉ"], random.Random(0))
    for _ in range(300):
        line = sampler.sample()
        if line[0].isupper():
            assert not unicodedata.combining(line[1])


FONT_DIRS = [ROOT / "fonts", ROOT / "data" / "fonts_unicode"]


@pytest.mark.skipif(not (ROOT / "fonts").exists(), reason="local fonts not available")
def test_every_font_renders_every_letter():
    fonts = discover_fonts(*[d for d in FONT_DIRS if d.exists()])
    assert fonts
    alphabet = "ⲁⲃⲅⲇⲉⲍⲏⲑⲓⲕⲗⲙⲛⲝⲟⲡⲣⲥⲧⲩⲫⲭⲯⲱϣϥϧϩϫϭϯ"
    for font in fonts:
        assert "?" not in font.encode(alphabet + alphabet.upper()), font.family
        img = np.asarray(render_line("ⲛ̀ⲧⲉ ⲫⲛⲟⲩϯ", font, size=40))
        assert (img < 128).sum() > 100, font.family


def test_degrade_returns_a_grayscale_line():
    rng = np.random.default_rng(0)
    clean = Image.new("L", (300, 60), 255)
    clean.paste(0, (40, 20, 260, 40))
    for _ in range(20):
        out = degrade(clean, rng)
        assert out.mode == "L"
        assert out.width >= 300 and out.height >= 60
        assert np.asarray(out).min() < 128  # the ink survives


def test_is_coptic_letter():
    assert is_coptic_letter("ⲁ") and is_coptic_letter("ϯ")
    assert not is_coptic_letter("a") and not is_coptic_letter(JINKIM)
