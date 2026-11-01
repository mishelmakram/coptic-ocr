"""Make scanned pages crisp: white paper, black ink, no specks, letters drawn as curves.

Nothing is redrawn from guesses. The paper is evened out to white, the ink is
kept exactly as scanned, specks far smaller than any mark of the script are
removed, and each ink shape's outline is traced into smooth curves (Potrace), so
the page stays sharp at any zoom and the file is small.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageFilter

WORK_WIDTH = 2400  # pixels: small scans are enlarged to about this before tracing
SPECK = 0.004  # of the letter height squared: ink shapes smaller than this are specks
EDGE = 0.03  # of the page size: the margin where thin slivers are taken for the paper's edge


def clean(image: Image.Image) -> tuple[np.ndarray, float]:
    """(ink mask, enlargement) of a page: True where there is ink, specks removed."""
    from scipy import ndimage

    gray = image.convert("L")
    factor = min(4.0, max(1.0, WORK_WIDTH / gray.width))
    if factor > 1.05:
        gray = gray.resize((round(gray.width * factor), round(gray.height * factor)), Image.BICUBIC)
    else:
        factor = 1.0
    pixels = np.asarray(gray, dtype=np.float32)

    # The paper: the page with its text closed over, smoothed. Dividing by it evens out
    # shading, yellowing and uneven lighting in photos.
    small = gray.reduce(8)
    paper = small.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(4))
    paper = np.asarray(paper.resize(gray.size, Image.BILINEAR), dtype=np.float32)
    level = pixels / np.maximum(paper, 1.0)
    ink = level < _otsu(level)

    labels, count = ndimage.label(ink, structure=np.ones((3, 3)))
    if count == 0:
        return ink, factor
    areas = np.bincount(labels.ravel())[1:]
    heights = np.array([s[0].stop - s[0].start for s in ndimage.find_objects(labels)])
    letter = float(np.median(heights[areas >= np.median(areas)]))
    drop = areas < max(4.0, SPECK * letter ** 2)
    # Thin slivers right at the page's edges: the shadow of the paper's edge, not print.
    h, w = ink.shape
    for k, (rows, cols) in enumerate(ndimage.find_objects(labels)):
        thin = min(rows.stop - rows.start, cols.stop - cols.start) <= 0.25 * letter
        at_edge = cols.stop <= EDGE * w or cols.start >= (1 - EDGE) * w or             rows.stop <= EDGE * h or rows.start >= (1 - EDGE) * h
        drop[k] |= thin and at_edge
    ink[np.isin(labels, np.flatnonzero(drop) + 1)] = False
    return ink, factor


def _otsu(values: np.ndarray) -> float:
    """The level splitting ``values`` (paper near 1, ink below) into two classes best."""
    hist, edges = np.histogram(np.clip(values, 0, 1.2), bins=240)
    centers = (edges[:-1] + edges[1:]) / 2
    weight = np.cumsum(hist)
    mean = np.cumsum(hist * centers)
    total, total_mean = weight[-1], mean[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (total_mean * weight / total - mean) ** 2 / (weight * (total - weight))
    return float(centers[np.nanargmax(between)])


def preview(image: Image.Image) -> Image.Image:
    """The cleaned page as an image at the scan's own size (fast; no tracing)."""
    ink, factor = clean(image)
    cleaned = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8))
    return cleaned.resize(image.size, Image.LANCZOS) if factor > 1 else cleaned


def outline_ops(ink: np.ndarray, scale: float, page_height: float) -> bytes:
    """PDF drawing operators filling the ink's traced outlines, in points (y up).

    Coordinates are written as whole half-pixels: finer than any zoom shows, and the
    page's drawing compresses far better than with decimals.
    """
    import potrace
    from scipy import ndimage

    half = scale / 2
    out = [f"q 0 g {half:.6f} 0 0 {-half:.6f} 0 {page_height:.3f} cm"]
    labels, _ = ndimage.label(ink, structure=np.ones((3, 3)))
    # Traced one shape at a time in its own small box: the tracer scans every pixel it is
    # given, so this is many times faster than tracing the whole page at once.
    for k, (rows, cols) in enumerate(ndimage.find_objects(labels), 1):
        shape = np.pad(labels[rows, cols] == k, 1)
        dx, dy = cols.start - 1, rows.start - 1

        def point(p) -> str:
            return f"{round((p.x + dx) * 2)} {round((p.y + dy) * 2)}"

        # potracer reads dark (0) as ink, like a grayscale image.
        for curve in potrace.Bitmap(~shape).trace(turdsize=2, alphamax=1.0, opticurve=True, opttolerance=0.5):
            out.append(f"{point(curve.start_point)} m")
            for segment in curve:
                if segment.is_corner:
                    out.append(f"{point(segment.c)} l {point(segment.end_point)} l")
                else:
                    out.append(f"{point(segment.c1)} {point(segment.c2)} {point(segment.end_point)} c")
            out.append("h")
    out.append("f* Q")  # even-odd: the counters of letters stay open
    return "\n".join(out).encode()


def _page_outline(paths: list[Path], index: int) -> tuple[float, float, bytes]:
    """(width, height, drawing) of one enhanced page; run in a worker process."""
    from .export import page_size
    from .pipeline import Document

    doc = Document(paths)
    try:
        image = doc.page_image(index)
        ink, _ = clean(image)
        width, height = page_size(doc, index, image)
        return width, height, outline_ops(ink, width / ink.shape[1], height)
    finally:
        doc.close()


def to_enhanced_pdf(doc, results: list, path: Path, pages: list[int],
                    progress: Callable[[int, int], bool] | None = None, workers: int = 0) -> bool:
    """``pages`` of ``doc`` cleaned and traced into a PDF of curves; False if stopped early.

    Pages are traced in parallel, one per processor core. Pages that were read also
    carry their recognized text, invisible, for searching. ``progress(done, total)``
    may return False to stop; nothing is saved then.
    """
    import os
    from concurrent.futures import ProcessPoolExecutor
    from functools import partial

    import pymupdf

    from .export import add_hidden_text

    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    work = partial(_page_outline, doc.paths)
    pool = ProcessPoolExecutor(min(workers, len(pages))) if workers > 1 and len(pages) > 1 else None
    out = pymupdf.open()
    try:
        outlines = pool.map(work, pages) if pool else map(work, pages)
        for done, (index, (width, height, drawing)) in enumerate(zip(pages, outlines)):
            if progress is not None and progress(done, len(pages)) is False:
                return False
            page = out.new_page(width=width, height=height)
            xref = out.get_new_xref()
            out.update_object(xref, "<<>>")
            out.update_stream(xref, drawing)
            page.set_contents(xref)
            result = results[index] if index < len(results) else None
            if result is not None:
                add_hidden_text(page, result, doc.page_image(index))
        if progress is not None and progress(len(pages), len(pages)) is False:
            return False
        out.save(path, garbage=3, deflate=True)
        return True
    finally:
        out.close()
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
