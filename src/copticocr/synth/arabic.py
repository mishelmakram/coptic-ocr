"""Synthetic Arabic text lines, shaped by HarfBuzz (through PyMuPDF), for training the Arabic reader.

    python -m copticocr.synth.arabic --corpus data/corpus/arabic_ot.txt --count 150000 --out data/synth/ar-v1

Lines look like the Arabic columns of church books: words often carry only some
of their vowel marks, words are stretched with kashida (البابـــا), and Bible
lines start with a small verse number. The label is what the line shows, in the
normalized spelling of ``copticocr.arabic`` (kashida is never part of a label).
"""

from __future__ import annotations

import argparse
import html
import multiprocessing
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from ..arabic import DIGITS, MARKS, normalize
from ..data.corpus import load_corpus
from .degrade import degrade

WINDOWS_FONTS = Path("C:/Windows/Fonts")
# Book faces (Naskh and plain); decorative ones (Thuluth, Kufi, script) would only confuse.
FONTS = [
    "simpo.ttf", "simpbdo.ttf", "trado.ttf", "tradbdo.ttf", "arabtype.ttf", "majalla.ttf", "majallab.ttf",
    "andlso.ttf", "arial.ttf", "arialbd.ttf", "times.ttf", "timesbd.ttf", "tahoma.ttf", "tahomabd.ttf",
    "segoeui.ttf", "segoeuib.ttf", "ArbFONTS-GE-Aridi-NaskhBold.otf", "ArbFONTS-GE-Aridi-NaskhBlack.otf",
    "ArbFONTS-GE-Heritage-One-Medium.otf", "ArbFONTS-GE-Heritage-One-Bold.otf", "ArbFONTS-GE-Elegant-Medium.otf",
    "ArbFONTS-GE-SS-Text-Medium.otf", "ArbFONTS-GE-SS-Text-Bold.otf", "ArbFONTS-GE-Serif-Medium.otf",
]
NON_JOINING = set("اأإآدذرزوؤةىء")  # letters that do not join the next one: no kashida after them

_state: dict = {}


def available_fonts(directory: Path = WINDOWS_FONTS) -> list[Path]:
    return [directory / name for name in FONTS if (directory / name).exists()]


def vowels(text: str, rng: random.Random) -> str:
    """Keep all, some or none of the vowel marks, as different books print them."""
    mode = rng.random()
    if mode < 0.3:
        return text
    if mode < 0.65:
        return "".join(ch for ch in text if ch not in MARKS)
    keep = rng.uniform(0.15, 0.6)
    return "".join(ch for ch in text if ch not in MARKS or rng.random() < (0.8 if ch == "ّ" else keep))


def stretch(word: str, rng: random.Random) -> str:
    """Insert kashida after a joining letter, as justified church books do."""
    spots = [i for i in range(1, len(word)) if word[i - 1] not in NON_JOINING and word[i - 1] not in MARKS
             and word[i] not in MARKS and i < len(word) - 1]
    if not spots:
        return word
    i = rng.choice(spots)
    return word[:i] + "ـ" * rng.randint(2, 7) + word[i:]


def sample_line(corpus: list[str], rng: random.Random) -> tuple[str, str]:
    """(rendered text with kashida, label)."""
    words = rng.choice(corpus).split()
    start = rng.randrange(len(words))
    words = vowels(" ".join(words[start:start + rng.randint(1, 7)]), rng).split()
    shown = [stretch(w, rng) if rng.random() < 0.12 else w for w in words]
    label_words = list(words)
    if rng.random() < 0.12:  # a verse number before the first word
        number = "".join(rng.choice(DIGITS) for _ in range(rng.randint(1, 2)))
        shown[0] = f"\x00{number}\x01{shown[0]}"
        label_words[0] = number + label_words[0]
    return " ".join(shown), normalize(" ".join(label_words))


def render(text: str, font: Path, size: float) -> Image.Image:
    import pymupdf

    body = html.escape(text).replace("\x00", '<span style="font-size: 60%">').replace("\x01", "</span>")
    css = (f"@font-face {{font-family: f; src: url({font.name});}} "
           f"* {{font-family: f; font-size: {size:.1f}px; margin: 0; white-space: nowrap;}}")
    archive = _state.setdefault("archives", {}).get(font.parent) or \
        _state["archives"].setdefault(font.parent, pymupdf.Archive(str(font.parent)))
    with pymupdf.open() as doc:
        page = doc.new_page(width=size * 40, height=size * 3)
        page.insert_htmlbox(page.rect, f'<p dir="rtl">{body}</p>', css=css, archive=archive)
        pix = page.get_pixmap(colorspace=pymupdf.csGRAY)
    gray = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w)
    rows, cols = np.flatnonzero((gray < 128).any(1)), np.flatnonzero((gray < 128).any(0))
    if not len(rows):
        return Image.new("L", (8, 8), 255)
    pad = round(size * 0.15)
    return Image.fromarray(gray[max(0, rows[0] - pad):rows[-1] + pad + 1, max(0, cols[0] - pad):cols[-1] + pad + 1])


def _init(corpus, fonts, out, height, seed):
    _state.update(corpus=corpus, fonts=fonts, out=out, height=height, seed=seed)


def make_sample(index: int) -> tuple[str, str, str]:
    s = _state
    rng = random.Random(f"{s['seed']}-{index}")
    np_rng = np.random.default_rng([s["seed"], index])
    while True:
        shown, label = sample_line(s["corpus"], rng)
        if label:
            break
    font = rng.choice(s["fonts"])
    img = degrade(render(shown, font, rng.uniform(30, 52)), np_rng)
    img = img.resize((max(1, round(img.width * s["height"] / img.height)), s["height"]), Image.LANCZOS)
    name = f"images/{index:07d}.png"
    img.save(s["out"] / name)
    return name, label, font.stem


def generate(corpus: list[str], fonts: list[Path], out: Path, count: int, start: int = 0,
             height: int = 64, seed: int = 0, workers: int = 0) -> None:
    (out / "images").mkdir(parents=True, exist_ok=True)
    workers = workers or max(1, multiprocessing.cpu_count() - 1)
    args = (corpus, fonts, out, height, seed)
    indices = range(start, start + count)
    with open(out / "labels.tsv", "a", encoding="utf-8") as labels:
        if workers == 1:
            _init(*args)
            results = map(make_sample, indices)
        else:
            pool = multiprocessing.Pool(workers, _init, args)
            results = pool.imap(make_sample, indices, chunksize=64)
        for done, (name, text, font) in enumerate(results, 1):
            labels.write(f"{name}\t{text}\t{font}\n")
            if done % 5000 == 0:
                print(f"{done}/{count}", file=sys.stderr, flush=True)
        if workers != 1:
            pool.close()
            pool.join()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", nargs="+", type=Path, required=True)
    parser.add_argument("--fonts", type=Path, default=WINDOWS_FONTS)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args(argv)
    fonts = available_fonts(args.fonts)
    print(f"{len(fonts)} fonts", file=sys.stderr)
    generate(load_corpus(*args.corpus), fonts, args.out, args.count, args.start, args.height, args.seed,
             args.workers)


if __name__ == "__main__":
    main()
