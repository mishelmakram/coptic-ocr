"""Labelled line images from a PDF typed in a legacy Coptic font (exact labels).

    python tools/typed_lines.py resources/kiahk.pdf data/real/kiahk --variants 2
    python tools/typed_lines.py resources/kiahk.pdf scratch --pages 300 --debug

Pages are rendered and every visual line made only of Coptic text is cut out;
its label is the font text converted to Unicode. Lines are set tighter than
their marks reach, so each crop keeps only the pixels under its own glyphs:
the line is drawn again with ``--font`` (the same legacy font) as a mask. Lines mixed with other
scripts, or with symbols the recognizer does not know, are skipped. Each line
is saved ``--variants`` times with different scan degradation (the first
variant is left clean).
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from copticocr.legacy.converter import layout_for_font  # noqa: E402
from copticocr.recog.charset import Charset  # noqa: E402
from copticocr.synth.degrade import degrade  # noqa: E402

DPI = 300
PAD = 0.15  # of the font size
IGNORED = set("✠ ")  # crosses before stanzas are cut off, not labelled


def visual_lines(page: pymupdf.Page) -> list[list[dict]]:
    """Spans grouped into visual lines: same baseline and script, no wide horizontal gap."""
    spans = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                span["text"] = "".join(c["c"] for c in span["chars"])
                if span["text"].strip():
                    spans.append(span)
    spans.sort(key=lambda s: (round(s["origin"][1]), s["bbox"][0]))
    lines: list[list[dict]] = []
    for span in spans:
        for line in lines:
            last = line[-1]
            same_row = abs(last["origin"][1] - span["origin"][1]) < 0.3 * span["size"]
            near = -span["size"] < span["bbox"][0] - last["bbox"][2] < 2 * span["size"]
            # Side-by-side Coptic and Arabic columns can be closer than a wide justified space.
            same_script = (layout_for_font(last["font"]) is None) == (layout_for_font(span["font"]) is None)
            if same_row and near and same_script:
                line.append(span)
                break
        else:
            lines.append([span])
    return lines


def label_of(line: list[dict], known: set[str]) -> tuple[str, list[dict]] | None:
    """(Unicode label, the spans it covers) or None when the line is not pure Coptic."""
    parts, kept = [], []
    for span in line:
        layout = layout_for_font(span["font"])
        if layout is None:
            return None
        text = layout.to_unicode(span["text"])
        if set(text) <= IGNORED:
            if kept:
                return None  # a cross inside the line
            continue
        if parts and span["bbox"][0] - kept[-1]["bbox"][2] > 0.2 * span["size"]:
            parts.append(" ")
        parts.append(text)
        kept.append(span)
    if not kept:
        return None
    label = re.sub(r"\s+", " ", "".join(parts)).strip()
    if not label or not set(label) <= known:
        return None
    return label, kept


def own_pixels(image: Image.Image, box: list[int], spans: list[dict], font_path: Path) -> Image.Image:
    """The crop at ``box`` with everything not under this line's glyphs whitened."""
    scale = DPI / 72
    mask = Image.new("L", (box[2] - box[0], box[3] - box[1]), 255)
    draw = ImageDraw.Draw(mask)
    for span in spans:
        font = ImageFont.truetype(str(font_path), round(span["size"] * scale))
        for ch in span["chars"]:
            x, y = ch["origin"]
            draw.text((x * scale - box[0], y * scale - box[1]), ch["c"], font=font, fill=0, anchor="ls")
    keep = np.asarray(mask.filter(ImageFilter.MinFilter(7))) < 128
    pixels = np.where(keep, np.asarray(image.crop(box)), 255).astype(np.uint8)
    return Image.fromarray(pixels)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--pages", default="0-99999")
    parser.add_argument("--font", type=Path, default=Path("fonts/Athanasius.ttf"),
                        help="the legacy font the book is typed in")
    parser.add_argument("--variants", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    known = set(Charset.coptic().symbols)
    rng = np.random.default_rng(args.seed)
    doc = pymupdf.open(args.pdf)
    a, _, b = args.pages.partition("-")
    pages = range(int(a), min(int(b or a) + 1, doc.page_count))
    (args.out / "images").mkdir(parents=True, exist_ok=True)
    scale = DPI / 72
    rows, skipped = [], 0
    for p in pages:
        page = doc[p]
        pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
        image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        debug = ImageDraw.Draw(image.convert("RGB")) if args.debug else None
        for i, line in enumerate(visual_lines(page)):
            found = label_of(line, known)
            if found is None:
                skipped += 1
                continue
            label, spans = found
            size = max(s["size"] for s in spans)
            x0 = min(s["bbox"][0] for s in spans) - PAD * size
            x1 = max(s["bbox"][2] for s in spans) + PAD * size
            base = max(s["origin"][1] for s in spans)
            y0, y1 = base - 1.1 * size, base + 0.45 * size
            box = [round(v * scale) for v in (x0, y0, x1, y1)]
            crop = own_pixels(image, box, spans, args.font)
            ink = np.flatnonzero((np.asarray(crop) < 128).any(1))
            if not len(ink):
                skipped += 1
                continue
            pad = round(PAD * size * scale)
            crop = crop.crop((0, max(0, ink[0] - pad), crop.width, min(crop.height, ink[-1] + 1 + pad)))
            for v in range(args.variants):
                name = f"images/{p:04d}_{i:02d}_{v}.png"
                (crop if v == 0 else degrade(crop, rng)).save(args.out / name)
                rows.append(f"{name}\t{label}\ttyped:{args.pdf.stem[:20]}")
            if debug:
                debug.rectangle(box, outline=(220, 0, 0), width=3)
        if debug:
            debug._image.resize((pix.width // 3, pix.height // 3)).save(args.out / f"debug_{p:04d}.png")
        if p % 100 == 0:
            print(f"page {p}: {len(rows)} images", file=sys.stderr, flush=True)
    with open(args.out / "labels.tsv", "a", encoding="utf-8", newline="\n") as f:
        f.write("".join(r + "\n" for r in rows))
    print(f"{len(rows)} images, {skipped} lines skipped")


if __name__ == "__main__":
    main()
