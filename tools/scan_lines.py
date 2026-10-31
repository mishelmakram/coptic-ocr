"""Cut a two-column scanned book (Coptic left, Arabic right) into line images.

    python tools/scan_lines.py resources/nt.pdf data/real/nt --pages 1-769
    python tools/scan_lines.py resources/nt.pdf scratch --pages 9 --debug

Writes ``coptic/PPPP_LL.png`` and ``arabic/PPPP_LL.png`` plus ``lines.tsv``
(image, page, line, side, x0, y0, x1, y1, marginal label box). Verse numbers
in the margin are cut off the Coptic lines and saved as ``coptic/*_num.png``.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from copticocr.layout.projection import (  # noqa: E402
    binarize, find_lines, skip_header, split_columns, split_margin, text_left_edge)

PAD = 6


def page_gray(doc: pymupdf.Document, index: int) -> np.ndarray:
    page = doc[index]
    images = page.get_images()
    if len(images) == 1:
        pix = pymupdf.Pixmap(doc, images[0][0])
        if pix.n != 1:
            pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
    else:
        pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.stride)[:, :pix.w].copy()


def parse_pages(spec: str, count: int) -> list[int]:
    pages = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        pages.extend(range(int(a), int(b or a) + 1))
    return [p for p in pages if 0 <= p < count]


def crop(gray: np.ndarray, box) -> Image.Image:
    h, w = gray.shape
    return Image.fromarray(gray[max(0, box.y0 - PAD):min(h, box.y1 + PAD),
                                max(0, box.x0 - PAD):min(w, box.x1 + PAD)])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--pages", default="0-99999")
    parser.add_argument("--debug", action="store_true", help="also save pages with boxes drawn")
    args = parser.parse_args()

    doc = pymupdf.open(args.pdf)
    for side in ("coptic", "arabic"):
        (args.out / side).mkdir(parents=True, exist_ok=True)
    rows = []
    for p in parse_pages(args.pages, doc.page_count):
        gray = page_gray(doc, p)
        ink = binarize(gray)
        columns = split_columns(ink)
        if columns is None:
            continue
        left, right = (skip_header(ink, c) for c in columns)
        coptic = find_lines(ink, left)
        text_left = text_left_edge(coptic)
        debug = Image.fromarray(gray).convert("RGB") if args.debug else None
        draw = ImageDraw.Draw(debug) if debug else None
        for i, line in enumerate(coptic):
            label, text = split_margin(ink, line, text_left)
            name = f"coptic/{p:04d}_{i:02d}.png"
            crop(gray, text).save(args.out / name)
            label_box = ""
            if label is not None:
                crop(gray, label).save(args.out / f"coptic/{p:04d}_{i:02d}_num.png")
                label_box = f"{label.x0},{label.y0},{label.x1},{label.y1}"
                if draw:
                    draw.rectangle([label.x0, label.y0, label.x1, label.y1], outline=(0, 160, 0), width=3)
            rows.append(f"{name}\t{p}\t{i}\tcoptic\t{text.x0}\t{text.y0}\t{text.x1}\t{text.y1}\t{label_box}")
            if draw:
                draw.rectangle([text.x0, text.y0, text.x1, text.y1], outline=(220, 0, 0), width=3)
        for i, line in enumerate(find_lines(ink, right)):
            name = f"arabic/{p:04d}_{i:02d}.png"
            crop(gray, line).save(args.out / name)
            rows.append(f"{name}\t{p}\t{i}\tarabic\t{line.x0}\t{line.y0}\t{line.x1}\t{line.y1}\t")
            if draw:
                draw.rectangle([line.x0, line.y0, line.x1, line.y1], outline=(0, 0, 220), width=3)
        if debug:
            debug.resize((debug.width // 3, debug.height // 3)).save(args.out / f"debug_{p:04d}.png")
        if p % 50 == 0:
            print(f"page {p}: {len(coptic)} coptic lines", file=sys.stderr, flush=True)
    with open(args.out / "lines.tsv", "a", encoding="utf-8", newline="\n") as f:
        f.write("".join(r + "\n" for r in rows))
    print(f"{len(rows)} lines")


if __name__ == "__main__":
    main()
