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
FAINTEST = 0.06  # the palest print taken for ink: this much darker than the paper
GRAINY = 0.01  # spread of the paper's brightness above which a scan counts as grainy
GRAIN_DEPTH = 2.5  # how far below the ink, in the grain's spread, its darkest pixel lies
PALE = 0.3  # of the page's darkest print (its contrast): marks paler than this are frames and shading
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
    if factor <= 1.05:
        factor = 1.0

    # The paper: the page with its text closed over, smoothed. Dividing by it evens out
    # shading, yellowing and uneven lighting in photos. Measured on the scan as it is, before
    # any enlarging: measured on an enlarged page, its reach would shrink with the level, until
    # thick strokes and bold titles were taken for paper and hollowed out.
    paper = gray.reduce(8).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(4))
    paper = np.asarray(paper.resize(gray.size, Image.BILINEAR), dtype=np.float32)
    level_map = np.asarray(gray, dtype=np.float32)
    del gray
    np.maximum(paper, 1.0, out=paper)
    np.divide(level_map, paper, out=level_map)
    del paper
    level_map = _cut_each_mark(level_map)
    if factor > 1:
        size = (round(level_map.shape[1] * factor), round(level_map.shape[0] * factor))
        level_map = np.asarray(Image.fromarray(level_map, "F").resize(size, Image.BICUBIC))
    if strength.smooth:
        # Steadying the gray before it is cut follows the print's own outline; blurring the
        # cut ink instead would round and thicken the letters.
        level_map = ndimage.gaussian_filter(level_map, strength.smooth * factor)
    ink = level_map < 0  # see _cut_each_mark
    del level_map

    labels, count = ndimage.label(ink, structure=np.ones((3, 3)))
    if count == 0:
        return ink, factor
    areas = np.bincount(labels.ravel())[1:]
    shapes = ndimage.find_objects(labels)
    heights = np.array([s[0].stop - s[0].start for s in shapes])
    letter = float(np.median(heights[areas >= np.median(areas)]))
    drop = areas < max(4.0, SPECK * letter ** 2)
    # A speck-sized mark right by a letter is a dot of the script (on a small or clean scan,
    # a pixel or two wide); only those well away from the print are specks.
    h, w = ink.shape
    block = 8
    near = np.concatenate([[False], ~drop])[labels][:h // block * block, :w // block * block]
    near = near.reshape(h // block, block, w // block, block).any(axis=(1, 3))
    near = ndimage.binary_dilation(near, iterations=max(1, round(0.5 * letter / block)))
    for k in np.flatnonzero(drop):
        rows, cols = shapes[k]
        y, x = (rows.start + rows.stop) // 2 // block, (cols.start + cols.stop) // 2 // block
        drop[k] = not near[min(y, near.shape[0] - 1), min(x, near.shape[1] - 1)]
    # Thin slivers right at the page's edges: the shadow of the paper's edge, not print.
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


def _cut_each_mark(level_map: np.ndarray) -> np.ndarray:
    """``level_map`` (paper evened out to 1) less where each pixel is cut: below 0 is ink.

    Each mark (a letter, a word joined up, a dot) is cut halfway between its own darkest point
    and the paper, which is where its edge is. One cut for the whole page cannot do this: the
    ink's darkness varies (worn or faded print, a lighter colour, uneven lighting), and so does
    a mark's own, since a dot or a hairline smaller than the scan's pixels never comes out as
    dark as a full stroke. A cut set for the dark letters loses the faint ones and the dots, or
    keeps only their cores; a cut set for the faint ones makes the dark letters bolder.
    Marks far paler than the page's darkest print (PALE) are print only where they have a
    letter's size and shape; long thin or large ones are the light frames, boxes and shading of
    web pages and modern books, and stay paper, as does the grain.
    """
    from scipy import ndimage

    # A mark's darkness is read on a lightly steadied copy, so that one dark grain does not
    # stand for the whole mark; what grain is left is allowed for, measured on the paper.
    sample = level_map[::4, ::4]
    paper = sample[sample > 0.8]
    grain = 1.4826 * float(np.median(np.abs(paper - np.median(paper)))) if paper.size else 0.0
    # Only a grainy scan is steadied: on a clean one (a screenshot) it would pale hairlines and
    # dots, which would then come out bolder.
    steady = ndimage.gaussian_filter(level_map, 0.7) if grain > GRAINY else level_map
    sample = steady[::4, ::4]
    paper = sample[sample > 0.8]
    grain = 1.4826 * float(np.median(np.abs(paper - np.median(paper)))) if paper.size else 0.0
    dark = 1.0 - float(np.percentile(sample, 0.5))  # the page's darkest print
    faintest = max(FAINTEST, PALE * dark)
    marks, count = ndimage.label(level_map < 1.0 - faintest / 2)
    if count == 0:
        return level_map
    peak = np.asarray(ndimage.minimum(steady, marks, np.arange(1, count + 1)), np.float32)
    del steady
    peak = np.minimum(peak + GRAIN_DEPTH * grain, 1.0)
    # A pale mark is still print where it has a letter's size and shape (faded print fades
    # unevenly); frames, rules, bands and shading are long and thin, or large.
    boxes = ndimage.find_objects(marks)
    heights = np.array([b[0].stop - b[0].start for b in boxes])
    widths = np.array([b[1].stop - b[1].start for b in boxes])
    strong = peak <= 1.0 - faintest
    letter = float(np.median(heights[strong & (heights > 2)])) if np.any(strong & (heights > 2)) else 20.0
    long_side, short_side = np.maximum(heights, widths), np.minimum(heights, widths)
    frame = ((long_side > 2 * letter) & (short_side < 0.25 * letter)) | (heights > 3 * letter) | (widths > 15 * letter)
    printed = strong | ((peak <= 1.0 - FAINTEST) & ~frame)
    cut = np.where(printed, (peak + 1.0) / 2, 0.0).astype(np.float32)  # not print: paper
    return level_map - np.concatenate([np.zeros(1, np.float32), cut])[marks]


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
