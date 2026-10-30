"""Read text from PDFs that were typed (not scanned) with legacy Coptic fonts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ..normalize import normalize_arabic
from .converter import layout_for_font


@dataclass
class Span:
    text: str
    font: str
    coptic: bool


def page_lines(page: pymupdf.Page) -> list[list[Span]]:
    """Return the page's lines, with legacy Coptic spans converted to Unicode."""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = []
            for span in line["spans"]:
                layout = layout_for_font(span["font"])
                if layout is not None:
                    spans.append(Span(layout.to_unicode(span["text"]), span["font"], True))
                else:
                    spans.append(Span(normalize_arabic(span["text"]), span["font"], False))
            if any(s.text.strip() for s in spans):
                lines.append(spans)
    return lines


def extract_text(path: str | Path, pages: range | None = None) -> list[str]:
    """Plain text of each page, Coptic in Unicode."""
    with pymupdf.open(path) as doc:
        numbers = pages if pages is not None else range(len(doc))
        return [
            "\n".join("".join(s.text for s in line) for line in page_lines(doc[n]))
            for n in numbers
        ]
