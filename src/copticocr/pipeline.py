"""From a scanned page to recognized text lines.

    doc = Document.open("book.pdf")
    engine = Engine("models/coptic-crnn-v2/best.pt")
    page = engine.read(doc.page_image(0))

The layout is found by projection profiles (one or two columns, running head,
verse numbers in the margin). Each line is labelled with its script; Coptic
lines are read by the line recognizer. Arabic lines are located but not read
yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

from .layout.projection import (Box, binarize, find_lines, remove_rules, skip_header,
                                split_columns, split_margin, text_left_edge)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
PDF_DPI = 300
PAD = 6  # pixels kept around a line's ink when it is cut out
COPTIC_MIN_CONFIDENCE = 0.6  # a column whose typical line reads worse is not Coptic
COPTIC_LINE_CONFIDENCE = 0.85  # mean letter confidence below which a line in a Coptic column is not Coptic
ARABIC_MIN_CONFIDENCE = 0.5  # an Arabic reading less certain than this is left empty (an ornament, a stain)


@dataclass
class TextLine:
    box: Box
    script: str  # "coptic" or "arabic"
    text: str = ""
    confidences: list[float] = field(default_factory=list)  # one per letter
    label: Box | None = None  # verse number in the margin
    edited: bool = False
    column: int = 0  # text column it was found in, left to right

    @property
    def confidence(self) -> float:
        return min(self.confidences, default=1.0)


@dataclass
class PageResult:
    size: tuple[int, int]  # width, height in pixels
    lines: list[TextLine]

    def text(self, script: str | None = None) -> str:
        return "\n".join(line.text for line in self.lines if script in (None, line.script))


class Document:
    """Pages of a PDF, a multi-page TIFF or a list of images, loaded on demand."""

    def __init__(self, paths: list[Path]):
        self.paths = paths
        self._pages: list[tuple[Path, int]] = []
        for path in paths:
            if path.suffix.lower() == ".pdf":
                with pymupdf.open(path) as doc:
                    self._pages += [(path, i) for i in range(doc.page_count)]
            else:
                with Image.open(path) as img:
                    self._pages += [(path, i) for i in range(getattr(img, "n_frames", 1))]
        self._open: dict[Path, pymupdf.Document] = {}

    @classmethod
    def open(cls, *paths: str | Path) -> Document:
        return cls([Path(p) for p in paths])

    @property
    def name(self) -> str:
        return self.paths[0].stem if self.paths else ""

    def __len__(self) -> int:
        return len(self._pages)

    def source(self, index: int) -> tuple[Path, int]:
        return self._pages[index]

    def page_image(self, index: int) -> Image.Image:
        """The page as a grayscale image (PDF pages at their scan resolution, else 300 dpi)."""
        path, number = self._pages[index]
        if path.suffix.lower() != ".pdf":
            with Image.open(path) as img:
                img.seek(number)
                return img.convert("L")
        doc = self._open.get(path) or self._open.setdefault(path, pymupdf.open(path))
        page = doc[number]
        images = page.get_image_info(xrefs=True)
        if len(images) == 1 and not page.get_text().strip():
            info = images[0]
            bbox = pymupdf.Rect(info["bbox"])
            if _fills(bbox, page.rect) and info["transform"][0] > 0 and info["transform"][3] > 0:
                pix = pymupdf.Pixmap(doc, info["xref"])  # a scan filling the page: take it as stored
                if pix.n - pix.alpha != 1:
                    pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
            else:
                # Part of a larger scan (say one page of a two-page spread), rotated or
                # shifted: render what the page shows, at the scan's own resolution.
                dpi = min(400, max(150, 72 * info["width"] / max(bbox.width, 1)))
                pix = page.get_pixmap(dpi=round(dpi), colorspace=pymupdf.csGRAY)
        else:
            pix = page.get_pixmap(dpi=PDF_DPI, colorspace=pymupdf.csGRAY)
        gray = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.stride)[:, :pix.w]
        return Image.fromarray(gray.copy())

    def close(self) -> None:
        for doc in self._open.values():
            doc.close()
        self._open.clear()


def _fills(bbox: pymupdf.Rect, page: pymupdf.Rect, tolerance: float = 0.02) -> bool:
    """Whether an image placed at ``bbox`` covers the page, give or take a small margin."""
    dx, dy = page.width * tolerance, page.height * tolerance
    return (abs(bbox.x0 - page.x0) <= dx and abs(bbox.x1 - page.x1) <= dx
            and abs(bbox.y0 - page.y0) <= dy and abs(bbox.y1 - page.y1) <= dy)


def find_text_lines(gray: np.ndarray) -> list[list[TextLine]]:
    """Lines of each text column, top to bottom; scripts are not decided yet."""
    ink = binarize(gray)
    clean = remove_rules(ink)
    columns = split_columns(clean)
    if columns is None:
        rows, cols = np.flatnonzero(clean.any(1)), np.flatnonzero(clean.any(0))
        if not len(rows):
            return []
        columns = (Box(int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1),)
    result = []
    for number, column in enumerate(columns):
        column = skip_header(ink, column)  # the rule under a running head is in ``ink`` only
        boxes = find_lines(clean, column)
        if not boxes:
            continue
        left = text_left_edge(boxes)
        lines = []
        for box in boxes:
            label, text = split_margin(clean, box, left)
            lines.append(TextLine(text, "coptic", label=label, column=number))
        result.append(lines)
    return result


def _join_split_titles(lines: list[TextLine]) -> list[TextLine]:
    """Rejoin a non-Coptic line that the column split cut in two (a title across both columns)."""
    out: list[TextLine] = []
    for line in lines:
        partner = next((
            other for other in out
            if other.script == line.script == "arabic" and other.column != line.column
            and min(other.box.y1, line.box.y1) - max(other.box.y0, line.box.y0) >= 0.5 * min(other.box.height,
                                                                                             line.box.height)
            and max(other.box.x0, line.box.x0) - min(other.box.x1, line.box.x1) < 3 * line.box.height
        ), None)
        if partner is None:
            out.append(line)
            continue
        a, b = partner.box, line.box
        partner.box = Box(min(a.x0, b.x0), min(a.y0, b.y0), max(a.x1, b.x1), max(a.y1, b.y1))
        partner.column = min(partner.column, line.column)
    return out


def crop(gray: Image.Image, box: Box) -> Image.Image:
    return gray.crop((max(0, box.x0 - PAD), max(0, box.y0 - PAD),
                      min(gray.width, box.x1 + PAD), min(gray.height, box.y1 + PAD)))


class Engine:
    """Layout analysis plus line recognition, for one page at a time."""

    def __init__(self, checkpoint: str | Path, device: str | None = None, batch: int = 32,
                 arabic_checkpoint: str | Path | None = None):
        from .recog.reader import open_recognizer  # slow to import; only load it when reading

        self.recognizer = open_recognizer(checkpoint, device)
        self.arabic = open_recognizer(arabic_checkpoint, device) if arabic_checkpoint else None
        self.batch = batch

    @property
    def device(self) -> str:
        return str(self.recognizer.device)

    def read(self, image: Image.Image) -> PageResult:
        gray = image.convert("L")
        columns = find_text_lines(np.asarray(gray))
        lines: list[TextLine] = []
        for column in columns:
            self._read_lines(gray, column)
            # The weakest letter of a Coptic line is still read well; Arabic lines are guesswork.
            coptic_column = np.median([line.confidence if line.text else 0.0 for line in column]) \
                >= COPTIC_MIN_CONFIDENCE
            for line in column:
                # Within a Coptic column a line read as guesswork is something else: an Arabic
                # title running across both columns, an ornament.
                if not coptic_column or not line.text or np.mean(line.confidences) < COPTIC_LINE_CONFIDENCE:
                    line.script, line.text, line.confidences = "arabic", "", []
            lines += column
        lines = _join_split_titles(lines)
        if self.arabic is not None:
            arabic = [line for line in lines if line.script == "arabic"]
            self._read_lines(gray, arabic, self.arabic)
            for line in arabic:
                if not line.confidences or np.mean(line.confidences) < ARABIC_MIN_CONFIDENCE:
                    line.text, line.confidences = "", []
        return PageResult(gray.size, lines)

    def _read_lines(self, gray: Image.Image, lines: list[TextLine], recognizer=None) -> None:
        recognizer = recognizer or self.recognizer
        for i in range(0, len(lines), self.batch):
            chunk = lines[i:i + self.batch]
            for line, (text, conf) in zip(chunk, recognizer.recognize_batch([crop(gray, l.box) for l in chunk])):
                line.text, line.confidences = text, conf
