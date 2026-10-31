"""Render Coptic text lines with legacy (ANSI) and Unicode fonts.

The label of every rendered line is always Unicode Coptic. For a legacy font
the text is first converted to that font's encoding, so the image shows the
same glyphs a church book printed with that font would show.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from ..data import abbreviations
from ..data.corpus import is_coptic_letter
from ..legacy import Layout, layout_for_font


@dataclass(frozen=True)
class LineFont:
    path: Path
    family: str
    layout: Layout | None  # None for a Unicode font

    def encode(self, text: str) -> str:
        return self.layout.from_unicode(text, errors="replace") if self.layout else text


def discover_fonts(*dirs: str | Path) -> list[LineFont]:
    """Every .ttf/.otf in ``dirs``; legacy fonts are recognised by family name."""
    fonts = []
    for directory in dirs:
        for path in sorted(Path(directory).glob("*.[ot]tf")):
            family = TTFont(path)["name"].getDebugName(1) or path.stem
            layout = layout_for_font(family)
            if layout is None and not _has_unicode_coptic(path):
                continue
            fonts.append(LineFont(path, family, layout))
    return fonts


def _has_unicode_coptic(path: Path) -> bool:
    return 0x2C81 in TTFont(path).getBestCmap()


@cache
def _pil_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def render_line(text: str, font: LineFont, size: int = 48, pad: int = 8,
                word_gap: float = 0.35) -> Image.Image:
    """Black text on white, grayscale, cropped to the ink plus ``pad`` pixels.

    Words are placed one by one ``word_gap`` em apart: some legacy fonts have
    an almost zero-width space, and justified columns stretch the gaps anyway.
    """
    pil_font = _pil_font(font.path, size)
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    gap = round(word_gap * size)

    words = [font.encode(w) for w in text.split()]
    boxes = [measure.textbbox((0, 0), w, font=pil_font) for w in words]
    top = min(b[1] for b in boxes)
    bottom = max(b[3] for b in boxes)
    width = sum(b[2] - b[0] for b in boxes) + gap * (len(words) - 1)

    img = Image.new("L", (width + 2 * pad, bottom - top + 2 * pad), 255)
    draw = ImageDraw.Draw(img)
    x = pad
    for word, (left, _, right, _) in zip(words, boxes):
        draw.text((x - left, pad - top), word, font=pil_font, fill=0)
        x += right - left + gap
    return img


class LineSampler:
    """Draw line-sized snippets of running text from a list of verses."""

    def __init__(self, verses: list[str], rng: random.Random):
        self.verses = verses
        self.rng = rng

    def sample(self, min_chars: int = 6, max_chars: int = 40) -> str:
        rng = self.rng
        target = rng.randint(min_chars, max_chars)
        words = rng.choice(self.verses).split()
        start = rng.randrange(len(words))
        line: list[str] = []
        for word in words[start:]:
            if line and len(" ".join(line + [word])) > target:
                break
            line.append(word)
        text = " ".join(line)

        # Typography seen in printed books.
        if rng.random() < 0.35:
            text = abbreviations.abbreviate(text, rng, rate=0.7)
        if rng.random() < 0.05:
            words = text.split(" ")
            words.insert(rng.randint(0, len(words)), abbreviations.sample(rng))
            text = " ".join(words)
        roll = rng.random()
        if roll < 0.15:
            text += rng.choice([" :", ":", "."])
        elif roll < 0.30 and len(line) > 1:
            text = _hyphenate_last_word(text, rng)
        # Not when the first letter carries a mark: several fonts draw a jinkim
        # inside a capital, and the label would then disagree with the image.
        if rng.random() < 0.15 and not (len(text) > 1 and unicodedata.combining(text[1])):
            text = text[0].upper() + text[1:]
        return text


def _hyphenate_last_word(text: str, rng: random.Random) -> str:
    """Break the last word like a justified column does: ``ⲉϥ-``."""
    head, _, last = text.rpartition(" ")
    cuts = [i for i in range(2, len(last) - 1) if is_coptic_letter(last[i])]
    if not cuts:
        return text
    return f"{head} {last[:rng.choice(cuts)]}-"
