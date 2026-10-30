"""Render every mapped glyph of a font into a labelled chart image.

Used to build and review the legacy (ANSI) font -> Unicode mapping tables:
each cell shows the glyph drawn by the font and the codepoint it sits on.

    python tools/glyph_chart.py fonts/ABRAAM_0.ttf out_dir/
"""

import argparse
import math
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

CELL_W, CELL_H = 110, 120
COLS = 12


def chart(font_path: Path, out_dir: Path, per_page: int = 96) -> list[Path]:
    cmap = TTFont(font_path).getBestCmap()
    codepoints = sorted(cp for cp in cmap if cp > 0x20)
    glyph_font = ImageFont.truetype(str(font_path), 64)
    label_font = ImageFont.truetype("arial.ttf", 13)

    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for page_no in range(math.ceil(len(codepoints) / per_page)):
        chunk = codepoints[page_no * per_page:(page_no + 1) * per_page]
        rows = math.ceil(len(chunk) / COLS)
        img = Image.new("RGB", (COLS * CELL_W, rows * CELL_H), "white")
        draw = ImageDraw.Draw(img)
        for i, cp in enumerate(chunk):
            x, y = (i % COLS) * CELL_W, (i // COLS) * CELL_H
            draw.rectangle([x, y, x + CELL_W - 1, y + CELL_H - 1], outline="#bbb")
            draw.text((x + CELL_W / 2, y + 55), chr(cp), font=glyph_font, fill="black", anchor="mm")
            shown = chr(cp) if 0x21 <= cp < 0x7F else ""
            draw.text((x + 4, y + CELL_H - 17), f"{cp:04X} {shown}", font=label_font, fill="#c00")
        path = out_dir / f"{font_path.stem}_{page_no + 1}.png"
        img.save(path)
        pages.append(path)
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font", type=Path)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    for path in chart(args.font, args.out_dir):
        print(path)


if __name__ == "__main__":
    main()
