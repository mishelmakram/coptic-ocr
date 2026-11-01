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
# Memory of one page being enhanced: a worker process's own (Python and its libraries) plus
# about this much per pixel at the tracing resolution (measured: 144 MB at 2400 px wide,
# 467 MB at 4800 px wide, a little over 13 bytes a pixel).
WORKER_BASE = 160 * 2 ** 20
BYTES_PER_PIXEL = 15
MEMORY_SHARE = 0.7  # of the memory free at the start; the rest stays for Windows and other programs


@dataclass(frozen=True)
class Strength:
    """How finely a page is worked on. No level changes a letter's shape: higher levels trace at
    a finer resolution and steady the scan's grain before it is cut into ink and paper."""

    work_width: int  # pixels: scans narrower than this are enlarged before tracing
    smooth: float  # blur of the gray scan before it is cut, in the scan's own pixels (0: none)
    mend: bool  # fill pinholes inside strokes
    alphamax: float  # Potrace: how readily corners become curves
    tolerance: float  # Potrace: how freely curves are joined


LEVELS = {
    # Every level traces the scan's own outline; none blurs or rounds it, since on small scans
    # the eyes of letters (ⲃ, ⲁ, ϧ) are a pixel or two wide and any smoothing fills them.
    # Higher levels only trace finer, and the top one fills specks inside strokes.
    1: Strength(2400, 0.0, False, 1.0, 0.4),
    2: Strength(3600, 0.0, False, 1.0, 0.4),
    3: Strength(4800, 0.0, True, 1.0, 0.4),
}


def clean(image: Image.Image, level: int = 1) -> tuple[np.ndarray, float]:
    """(ink mask, enlargement) of a page: True where there is ink, specks removed.

    Memory matters: several pages are cleaned at once, at up to 35 million pixels each. Work
    is done in place where it can be, and shapes are picked out through lookup tables (a
    value per shape) rather than by comparing every pixel with a list of shapes.
    """
    from scipy import ndimage

    strength = LEVELS[level]
    gray = image.convert("L")
    factor = min(6.0, max(1.0, strength.work_width / gray.width))
    if factor > 1.05:
        gray = gray.resize((round(gray.width * factor), round(gray.height * factor)), Image.BICUBIC)
    else:
        factor = 1.0

    # The paper: the page with its text closed over, smoothed. Dividing by it evens out
    # shading, yellowing and uneven lighting in photos.
    paper = gray.reduce(8).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(4))
    paper = np.asarray(paper.resize(gray.size, Image.BILINEAR), dtype=np.float32)
    level_map = np.asarray(gray, dtype=np.float32)
    del gray
    np.maximum(paper, 1.0, out=paper)
    np.divide(level_map, paper, out=level_map)
    del paper
    if strength.smooth:
        # Steadying the gray before it is cut follows the print's own outline; blurring the
        # cut ink instead would round and thicken the letters.
        level_map = ndimage.gaussian_filter(level_map, strength.smooth * factor)
    ink = level_map < _otsu(level_map)
    del level_map

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
    keep = np.concatenate([[False], ~drop])  # per shape, label 0 being the paper
    ink = keep[labels]
    del labels

    if strength.mend:
        # Pinholes (white specks inside strokes) are filled; the eyes of letters (ϧ, ⲑ, ⲁ),
        # larger than any pinhole, are left as they are.
        holes, _ = ndimage.label(~ink)
        pinhole = np.bincount(holes.ravel()) < PINHOLE * letter ** 2
        pinhole[0] = False  # the ink itself
        for edge in (holes[0], holes[-1], holes[:, 0], holes[:, -1]):
            pinhole[edge] = False  # white touching the page's edge is paper, not a hole
        ink |= pinhole[holes]
        del holes
    return ink, factor


def _otsu(values: np.ndarray) -> float:
    """The level splitting ``values`` (paper near 1, ink below) into two classes best.

    Kept between 0.3 and 0.9: paper is near 1 once evened out, so a cut outside that
    range is a failed estimate (it would turn the whole page into ink, or lose faint print).
    """
    hist, edges = np.histogram(values, bins=256, range=(0.0, 1.2))
    hist = hist.astype(np.float64)
    centers = (edges[:-1] + edges[1:]) / 2
    weight = np.cumsum(hist)
    mean = np.cumsum(hist * centers)
    total, total_mean = weight[-1], mean[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (total_mean * weight / total - mean) ** 2 / (weight * (total - weight))
    between[~np.isfinite(between)] = -1
    return float(np.clip(centers[int(np.argmax(between))], 0.3, 0.9))


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


def available_memory() -> int:
    """Physical memory free now, in bytes."""
    import os
    import sys

    if sys.platform == "win32":
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in
                ("total", "available", "page_total", "page_free", "virtual_total", "virtual_free", "extended")]

        status = Status()
        status.length = ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.available)
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return 2 * 2 ** 30


def page_memory(doc, pages: list[int], level: int) -> int:
    """Bytes one page needs while it is enhanced (the largest of a few sample pages)."""
    sample = sorted({pages[0], pages[len(pages) // 2], pages[-1]}) if pages else []
    need = WORKER_BASE
    for index in sample:
        width, height = doc.page_image(index).size
        factor = min(6.0, max(1.0, LEVELS[level].work_width / width))
        need = max(need, WORKER_BASE + int(width * factor * height * factor * BYTES_PER_PIXEL))
    return need


def plan_workers(doc, pages: list[int], level: int) -> int:
    """How many pages to start enhancing at once: one per processor core, as far as the memory
    free now allows. While the work runs, ``to_enhanced_pdf`` keeps checking (see there)."""
    import os

    cores = max(1, (os.cpu_count() or 2) - 1)
    if len(pages) <= 1:
        return 1
    return max(1, min(cores, len(pages), int(available_memory() * MEMORY_SHARE // page_memory(doc, pages, level))))


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

    Pages are traced in parallel, as many at once as the cores and the free memory allow,
    checked again before each page (``workers`` caps it), and appended to the file in
    batches, so a book of thousands of pages needs no more memory than a batch.
    Pages that were read also carry their recognized text, invisible, for searching.
    ``progress(done, total)`` may return False to stop; the unfinished file is removed.
    """
    import os
    import time
    from collections import deque
    from concurrent.futures import ProcessPoolExecutor
    from functools import partial

    import pymupdf

    from .export import _pixmap, add_hidden_text

    cores = max(1, (os.cpu_count() or 2) - 1)
    most = min(workers or cores, len(pages))
    work = partial(_page_outline, doc.paths, level)
    pool = ProcessPoolExecutor(most) if most > 1 else None
    per_page = page_memory(doc, pages, level) if pool else 0
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

    running: deque = deque()  # pages started, in page order
    started: deque = deque()  # when recent pages started; they have not taken their memory yet
    following = 0

    def start_more() -> None:
        """Start further pages while cores are idle and free memory holds another page.

        Checked before every page, so the work slows when other programs take memory and
        speeds up again when they free it. One page always runs, whatever the memory."""
        nonlocal following
        while following < len(pages) and len(running) < most:
            now = time.monotonic()
            while started and now - started[0] > 3:
                started.popleft()
            if running and available_memory() * MEMORY_SHARE < per_page * (1 + len(started)):
                break
            running.append(pool.submit(work, pages[following]))
            started.append(now)
            following += 1

    finished = False
    try:
        for done, index in enumerate(pages):
            if progress is not None and progress(done, len(pages)) is False:
                return False
            if pool is None:
                width, height, drawing = work(index)
            else:
                start_more()
                width, height, drawing = running.popleft().result()
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
