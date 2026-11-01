"""Make scanned pages crisp: white paper, black ink, no specks, letters drawn as curves.

Nothing is redrawn from guesses. The paper is evened out to white, the ink is
kept exactly as scanned, specks far smaller than any mark of the script are
removed, and each ink shape's outline is traced into smooth curves (Potrace), so
the page stays sharp at any zoom and the file is small.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageFilter

SPECK = 0.004  # of the letter height squared: ink shapes smaller than this are specks
EDGE = 0.03  # of the page size: the margin where thin slivers are taken for the paper's edge
BATCH = 50  # pages held in memory before they are appended to the file
PINHOLE = 0.0012  # of the letter height squared: white holes this small inside ink are scanning faults


@dataclass(frozen=True)
class Strength:
    """How hard a page is worked on. Every level keeps the scan's letter shapes; higher levels
    work at a finer resolution and even out the outline more."""

    work_width: int  # pixels: scans narrower than this are enlarged before tracing
    smooth: float  # of the letter height: blur of the ink before it is cut again, rounding jagged edges
    repair: float  # of the letter height: hairline breaks in strokes closed, pinholes filled
    alphamax: float  # Potrace: how readily corners become curves
    tolerance: float  # Potrace: how freely curves are joined


LEVELS = {
    1: Strength(2400, 0.0, 0.0, 1.0, 0.5),       # clean and trace
    2: Strength(3200, 0.045, 0.0, 1.2, 0.5),     # and smooth the edges, fill pinholes
    3: Strength(4000, 0.065, 0.008, 1.3, 0.6),   # and mend broken strokes: like freshly printed
}


def clean(image: Image.Image, level: int = 1) -> tuple[np.ndarray, float]:
    """(ink mask, enlargement) of a page: True where there is ink, specks removed."""
    from scipy import ndimage

    strength = LEVELS[level]
    gray = image.convert("L")
    factor = min(4.0, max(1.0, strength.work_width / gray.width))
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
    level_map = pixels / np.maximum(paper, 1.0)
    ink = level_map < _otsu(level_map)

    labels, count = ndimage.label(ink, structure=np.ones((3, 3)))
    if count == 0:
        return ink, factor
    areas = np.bincount(labels.ravel())[1:]
    shapes = ndimage.find_objects(labels)
    heights = np.array([s[0].stop - s[0].start for s in shapes])
    letter = float(np.median(heights[areas >= np.median(areas)]))
    drop = areas < max(4.0, SPECK * letter ** 2)
    # Thin slivers right at the page's edges: the shadow of the paper's edge, not print.
    h, w = ink.shape
    for k, (rows, cols) in enumerate(shapes):
        thin = min(rows.stop - rows.start, cols.stop - cols.start) <= 0.25 * letter
        at_edge = (cols.stop <= EDGE * w or cols.start >= (1 - EDGE) * w
                   or rows.stop <= EDGE * h or rows.start >= (1 - EDGE) * h)
        drop[k] |= thin and at_edge
    ink[np.isin(labels, np.flatnonzero(drop) + 1)] = False

    if strength.smooth or strength.repair:
        # The eyes of letters (ϧ, ⲑ, ⲁ): white enclosed by ink and larger than a pinhole.
        # Mending and smoothing may close them; they are put back at the end.
        holes, _ = ndimage.label(~ink)
        background = np.unique(np.concatenate([holes[0], holes[-1], holes[:, 0], holes[:, -1]]))
        enclosed = (holes > 0) & ~np.isin(holes, background)
        hole_areas = np.bincount(holes.ravel())
        small = hole_areas < PINHOLE * letter ** 2
        eyes = enclosed & ~small[holes]
        ink |= enclosed & small[holes]  # pinholes: white specks inside strokes
        if strength.repair:
            radius = max(1, round(strength.repair * letter))
            disk = np.hypot(*np.mgrid[-radius:radius + 1, -radius:radius + 1]) <= radius
            ink = ndimage.binary_closing(ink, structure=disk)  # hairline breaks in a stroke
        if strength.smooth:
            # Blurring the ink and cutting it at half rounds off jags and nicks but keeps any
            # stroke wider than the blur, so thin marks (jinkim, harakat) stay.
            ink = ndimage.gaussian_filter(ink.astype(np.float32), strength.smooth * letter) > 0.5
        ink &= ~eyes
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


def preview(image: Image.Image, level: int = 1) -> Image.Image:
    """The cleaned page as an image at the scan's own size (fast; no tracing)."""
    ink, factor = clean(image, level)
    cleaned = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8))
    return cleaned.resize(image.size, Image.LANCZOS) if factor > 1 else cleaned


def vector_preview(image: Image.Image, level: int = 1) -> tuple[Image.Image, float]:
    """The page exactly as the enhanced PDF draws it, rendered at the tracing resolution.

    Returns the picture and the scale that brings its pixels back to the scan's, so a
    viewer can lay it over the scan's coordinates and still zoom in on fine detail.
    """
    import pymupdf

    ink, _ = clean(image, level)
    width, height = image.size
    with pymupdf.open() as doc:
        page = doc.new_page(width=width, height=height)
        xref = doc.get_new_xref()
        doc.update_object(xref, "<<>>")
        doc.update_stream(xref, outline_ops(ink, width / ink.shape[1], height, level))
        page.set_contents(xref)
        zoom = ink.shape[1] / width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
        picture = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    return picture, width / picture.width


def outline_ops(ink: np.ndarray, scale: float, page_height: float, level: int = 1) -> bytes:
    """PDF drawing operators filling the ink's traced outlines, in points (y up).

    Coordinates are written as whole half-pixels: finer than any zoom shows, and the
    page's drawing compresses far better than with decimals.
    """
    import potrace
    from scipy import ndimage

    strength = LEVELS[level]
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
        for curve in potrace.Bitmap(~shape).trace(turdsize=2, alphamax=strength.alphamax, opticurve=True,
                                                   opttolerance=strength.tolerance):
            out.append(f"{point(curve.start_point)} m")
            for segment in curve:
                if segment.is_corner:
                    out.append(f"{point(segment.c)} l {point(segment.end_point)} l")
                else:
                    out.append(f"{point(segment.c1)} {point(segment.c2)} {point(segment.end_point)} c")
            out.append("h")
    out.append("f* Q")  # even-odd: the counters of letters stay open
    return "\n".join(out).encode()


def _page_outline(paths: list[Path], level: int, index: int) -> tuple[float, float, bytes | None]:
    """(width, height, drawing) of one enhanced page; run in a worker process.

    A page that cannot be enhanced (a damaged image, say) gives no drawing, and is
    copied as it is rather than stopping a long book.
    """
    from .export import page_size
    from .pipeline import Document

    doc = Document(paths)
    try:
        image = doc.page_image(index)
        width, height = page_size(doc, index, image)
        try:
            ink, _ = clean(image, level)
            return width, height, outline_ops(ink, width / ink.shape[1], height, level)
        except Exception:  # noqa: BLE001 - one bad page must not end the whole book
            return width, height, None
    finally:
        doc.close()


def to_enhanced_pdf(doc, results: list, path: Path, pages: list[int],
                    progress: Callable[[int, int], bool] | None = None, workers: int = 0,
                    level: int = 1) -> bool:
    """``pages`` of ``doc`` cleaned and traced into a PDF of curves; False if stopped early.

    Pages are traced in parallel, one per processor core, and appended to the file in
    batches, so a book of thousands of pages needs no more memory than a batch.
    Pages that were read also carry their recognized text, invisible, for searching.
    ``progress(done, total)`` may return False to stop; the unfinished file is removed.
    """
    import os
    from concurrent.futures import ProcessPoolExecutor
    from functools import partial

    import pymupdf

    from .export import _pixmap, add_hidden_text

    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    work = partial(_page_outline, doc.paths, level)
    pool = ProcessPoolExecutor(min(workers, len(pages))) if workers > 1 and len(pages) > 1 else None
    partial_path = path.with_name(path.name + ".part")
    partial_path.unlink(missing_ok=True)
    batch = pymupdf.open()

    def flush() -> None:
        """Append the pages built so far to the file and free them."""
        nonlocal batch
        if not batch.page_count:
            return
        if partial_path.exists():
            batch.subset_fonts()
            with pymupdf.open(partial_path) as written:
                written.insert_pdf(batch)
                written.saveIncr()
        else:
            batch.subset_fonts()
            batch.save(partial_path, garbage=3, deflate=True)
        batch.close()
        batch = pymupdf.open()

    finished = False
    try:
        outlines = pool.map(work, pages, chunksize=1) if pool else map(work, pages)
        for done, (index, (width, height, drawing)) in enumerate(zip(pages, outlines)):
            if progress is not None and progress(done, len(pages)) is False:
                return False
            page = batch.new_page(width=width, height=height)
            if drawing is None:
                page.insert_image(page.rect, pixmap=_pixmap(doc.page_image(index)))
            else:
                xref = batch.get_new_xref()
                batch.update_object(xref, "<<>>")
                batch.update_stream(xref, drawing)
                page.set_contents(xref)
            result = results[index] if index < len(results) else None
            if result is not None:
                add_hidden_text(page, result, doc.page_image(index))
            if batch.page_count == BATCH:
                flush()
        flush()
        if progress is not None and progress(len(pages), len(pages)) is False:
            return False
        finished = True
        return True
    finally:
        batch.close()
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
        if finished:
            partial_path.replace(path)
        else:
            partial_path.unlink(missing_ok=True)
