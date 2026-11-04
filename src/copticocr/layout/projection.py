"""Column and line finding by ink projection profiles.

Good enough for clean, regularly typeset pages (a Bible with a Coptic and an
Arabic column); a learned layout model replaces it for harder books.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Box:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0


def binarize(gray: np.ndarray, threshold: int = 128) -> np.ndarray:
    """Boolean ink mask of a grayscale page."""
    return gray < threshold


def _long_runs(ink: np.ndarray, length: int) -> np.ndarray:
    """Pixels lying in a vertical run of ink at least ``length`` long."""
    length = max(1, min(length, ink.shape[0]))
    c = np.concatenate([np.zeros((1, ink.shape[1]), np.int32), np.cumsum(ink, 0, dtype=np.int32)])
    start = (c[length:] - c[:-length]) == length  # a full run starts at each such row
    s = np.concatenate([np.zeros((1, ink.shape[1]), np.int32), np.cumsum(start, 0, dtype=np.int32)])
    rows = np.arange(ink.shape[0])
    lo = np.clip(rows - length + 1, 0, len(start))
    hi = np.clip(rows + 1, 0, len(start))
    return (s[hi] - s[lo]) > 0


def remove_rules(ink: np.ndarray, vertical: float = 0.08, horizontal: float = 0.25) -> np.ndarray:
    """The ink without frames and column rules: straight runs longer than any glyph."""
    # Scanned rules are a little slanted and broken: measure on a thickened copy.
    thick = _spread(_spread(ink, 1, 1), 0, 1)
    rules = _long_runs(thick, int(ink.shape[0] * vertical))
    rules |= _long_runs(_spread(thick, 1, 1).T, int(ink.shape[1] * horizontal)).T
    return ink & ~_spread(_spread(rules, 1, 1), 0, 1)


def letter_height(ink: np.ndarray) -> float:
    """The typical height of a page's letters, in pixels."""
    from scipy import ndimage

    labels, count = ndimage.label(ink, structure=np.ones((3, 3)))
    if count == 0:
        return 0.0
    heights = np.array([s[0].stop - s[0].start for s in ndimage.find_objects(labels)])
    areas = np.bincount(labels.ravel())[1:]
    return float(np.median(heights[areas >= np.median(areas)]))


def remove_ornaments(clean: np.ndarray, ink: np.ndarray, letter: float, size: float = 2.5) -> np.ndarray:
    """``clean`` (the ink without rules) without a band of ornament: crosses and tiles around a
    title over the columns. Meant for the page's head only: in the text, large capitals
    would be taken for it.

    Ornaments are drawn as several shapes far taller than the page's letters (``letter``). They
    are found whole in ``ink`` (in ``clean`` their long arms went with the rules, leaving
    pieces), and every mark close to them (the small tiles between the crosses) goes too."""
    from scipy import ndimage

    labels, count = ndimage.label(ink, structure=np.ones((3, 3)))
    if count == 0 or not letter:
        return clean
    shapes = ndimage.find_objects(labels)
    heights = np.array([s[0].stop - s[0].start for s in shapes])
    widths = np.array([s[1].stop - s[1].start for s in shapes])
    big = (heights > size * letter) & (widths > 0.5 * size * letter)
    if big.sum() < 3:
        return clean
    ornament = np.concatenate([[False], big])[labels]
    del labels
    near = ndimage.binary_dilation(ornament[::4, ::4], iterations=max(1, round(1.25 * letter / 4)))
    pieces, count = ndimage.label(clean, structure=np.ones((3, 3)))
    drop = np.zeros(count + 1, bool)
    drop[np.unique(pieces[ornament])] = True  # the pieces of the ornament itself
    for k, (rows, cols) in enumerate(ndimage.find_objects(pieces), 1):
        y, x = (rows.start + rows.stop) // 2 // 4, (cols.start + cols.stop) // 2 // 4
        drop[k] |= near[min(y, near.shape[0] - 1), min(x, near.shape[1] - 1)]
    drop[0] = False
    return clean & ~drop[pieces]


def without_tall_shapes(ink: np.ndarray, box: Box, size: float = 1.8) -> np.ndarray:
    """``ink`` without what in ``box`` stands taller than ``size`` of its lines: a drop cap two or
    three lines high, a vignette. Left in, it would join those lines into one.

    Some are drawn whole, others as an outline of many small pieces, so pieces that all but
    touch are taken together (letters of one line are, but stay a line high)."""
    from scipy import ndimage

    lines = find_lines(ink, box)
    if len(lines) < 3:
        return ink
    line = float(np.median([b.height for b in lines]))
    region = ink[box.y0:box.y1, box.x0:box.x1]
    joined = ndimage.binary_dilation(region, iterations=max(1, round(0.035 * line)))
    labels, count = ndimage.label(joined, structure=np.ones((3, 3)))
    heights = np.array([s[0].stop - s[0].start for s in ndimage.find_objects(labels)])
    tall = np.concatenate([[False], heights > size * line])
    if not tall.any():
        return ink
    out = ink.copy()
    out[box.y0:box.y1, box.x0:box.x1] &= ~tall[labels]
    return out


def _spread(mask: np.ndarray, axis: int, n: int) -> np.ndarray:
    """``mask`` grown by ``n`` pixels both ways along ``axis``."""
    out = mask.copy()
    for k in range(1, n + 1):
        shifted = np.roll(mask, k, axis) | np.roll(mask, -k, axis)
        out |= shifted
    return out


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) of each run of True values."""
    padded = np.concatenate([[False], mask, [False]])
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(edges[::2], edges[1::2]))


def smooth(profile: np.ndarray, size: int) -> np.ndarray:
    return np.convolve(profile, np.ones(size) / size, mode="same")


def widest_gap(profile: np.ndarray, lo: int, hi: int, limit: float) -> tuple[int, int] | None:
    """Widest run in [lo, hi) where the profile stays at or below ``limit``."""
    found = [(s + lo, e + lo) for s, e in runs(profile[lo:hi] <= limit)]
    return max(found, key=lambda r: r[1] - r[0], default=None)


def split_columns(ink: np.ndarray, lo: float = 0.35, hi: float = 0.75) -> tuple[Box, Box] | None:
    """Left and right column of a two-column page, split at the widest blank gutter.

    What runs across the gutter above the columns (an ornament, a heading, titles) is looked
    past: the gutter is sought in the text below it, and the columns then begin there; what is
    above them is the page's head, read across the full width (``page_head``)."""
    height, width = ink.shape
    rows = np.flatnonzero(ink.sum(1) > 0)
    cols = np.flatnonzero(ink.sum(0) > 0)
    if not len(rows):
        return None
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    gap = _gutter(ink, lo, hi)
    if gap is None:
        bands = runs(ink.any(1))
        for start, _ in bands[1:]:
            if start > 0.6 * height:
                break
            below = sum(s >= start for s, _ in bands)
            if below >= 6 and (gap := _gutter(ink[start:], lo, hi)) is not None:
                top = int(start)
                break
    if gap is None:
        return None
    return Box(int(cols[0]), top, int(gap[0]), bottom), Box(int(gap[1]), top, int(cols[-1]) + 1, bottom)


def page_head(ink: np.ndarray, columns: tuple[Box, Box]) -> Box | None:
    """The full-width part of the page above its columns (see ``split_columns``), if any, as far
    as ``ink`` shows it."""
    rows = np.flatnonzero(ink[:columns[0].y0].any(1))
    if not len(rows):
        return None
    return Box(columns[0].x0, int(rows[0]), columns[1].x1, int(rows[-1]) + 1)


def _gutter(ink: np.ndarray, lo: float, hi: float) -> tuple[int, int] | None:
    """[start, end) of the blank strip between two columns, if there is one."""
    height, width = ink.shape
    profile = smooth(ink.sum(0).astype(float), 5)
    gap = widest_gap(profile, int(width * lo), int(width * hi), height * 0.002)
    if gap is not None and gap[1] - gap[0] >= width * 0.005:
        return gap
    # A title or heading may run across the gutter: look instead for a strip that
    # is blank in nearly every line of text, and somewhat wider than a word space.
    bands = runs(ink.any(1))
    if len(bands) < 4:
        return None
    crossed = np.mean([ink[s:e].any(0) for s, e in bands], axis=0)
    gap = widest_gap(smooth(crossed, 5), int(width * lo), int(width * hi), 0.15)
    if gap is None or gap[1] - gap[0] < width * 0.015:
        return None
    return gap


def split_further(ink: np.ndarray, box: Box, page_width: int, depth: int = 3) -> list[Box]:
    """A column cut again wherever a blank strip runs its full height: the third column of a
    three-column page (Coptic, Coptic in Arabic letters, Arabic). Within one column of text no
    strip is blank in every line, however the words fall."""
    region = ink[box.y0:box.y1, box.x0:box.x1]
    width = region.shape[1]
    if depth == 0 or width < page_width * 0.15:
        return [box]
    profile = region.sum(0)
    gap = widest_gap(profile.astype(float), int(width * 0.15), int(width * 0.85), 0)
    if gap is None or gap[1] - gap[0] < page_width * 0.02:
        return [box]
    left, right = profile[:gap[0]].sum(), profile[gap[1]:].sum()
    if min(left, right) < 0.1 * (left + right):  # a stray mark beside the text, not a column
        return [box]
    a = Box(box.x0, box.y0, box.x0 + gap[0], box.y1)
    b = Box(box.x0 + gap[1], box.y0, box.x1, box.y1)
    return split_further(ink, a, page_width, depth - 1) + split_further(ink, b, page_width, depth - 1)


def skip_header(ink: np.ndarray, box: Box, search: float = 0.12) -> Box:
    """Drop the running head: everything down to a horizontal rule near the top, if any."""
    region = ink[box.y0:box.y0 + int(ink.shape[0] * search), box.x0:box.x1]
    # A rule runs in long strokes (a scanned one is broken here and there, still 40% of the
    # width or more at a stretch); an Arabic line's baseline covers as much, but is broken
    # between words and letters into pieces of 15% at most.
    full = [y for y in np.flatnonzero(region.mean(1) > 0.6)
            if max((e - s for s, e in runs(region[y])), default=0) > 0.25 * region.shape[1]]
    if not len(full):
        return box
    return Box(box.x0, box.y0 + int(full[-1]) + 1, box.x1, box.y1)


def find_lines(ink: np.ndarray, box: Box, min_gap: int = 2) -> list[Box]:
    """Text lines in a single-column region, tight to their ink.

    Thin bands (jinkim and overlines printed above a line, stray dots) are
    merged into the nearest full line.
    """
    region = ink[box.y0:box.y1, box.x0:box.x1]
    filled = region.sum(1) > max(2, region.shape[1] * 0.002)
    bands = [list(r) for r in runs(filled)]
    # Close tiny gaps inside a line (broken glyphs).
    merged: list[list[int]] = []
    for s, e in bands:
        if merged and s - merged[-1][1] < min_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    if not merged:
        return []
    heights = np.array([e - s for s, e in merged])
    typical = float(np.median(heights[heights >= np.percentile(heights, 50)]))
    lines: list[list[int]] = []
    pending: list[int] | None = None
    for s, e in merged:
        if e - s < typical * 0.45:
            # Marks above a line belong to the line below; a trailing band joins the previous one.
            if pending is not None and s - pending[1] >= typical * 0.6:
                # Far from the marks before (a descender's tail, then the next line's accents):
                # those were the previous line's.
                if lines and pending[0] - lines[-1][1] < typical * 0.3:
                    lines[-1][1] = pending[1]
                pending = None
            if pending is None:
                pending = [s, e]
            else:
                pending[1] = e
            continue
        if pending is not None and s - pending[1] < typical * 0.6:
            s = pending[0]
        elif pending is not None and lines and pending[0] - lines[-1][1] < typical * 0.3:
            lines[-1][1] = pending[1]
        pending = None
        lines.append([s, e])
    if pending is not None and lines and pending[0] - lines[-1][1] < typical * 0.3:
        lines[-1][1] = pending[1]
    lines = _split_tall(lines, region.sum(1))

    out = []
    for s, e in lines:
        pieces = runs(region[s:e].any(0))
        # A faint rule or the page edge leaves a thin sliver far right of the text.
        while len(pieces) > 1 and pieces[-1][1] - pieces[-1][0] <= max(3, (e - s) * 0.15) \
                and pieces[-1][0] - pieces[-2][1] >= e - s:
            pieces.pop()
        out.append(Box(box.x0 + int(pieces[0][0]), box.y0 + int(s), box.x0 + int(pieces[-1][1]), box.y0 + int(e)))
    return out


def _split_tall(lines: list[list[int]], profile: np.ndarray, size: float = 1.7) -> list[list[int]]:
    """Lines far taller than the rest cut in two where they hold least ink: two lines that a
    stray mark (a flourish, a smudge) bridges leave no row blank between them."""
    if len(lines) < 3:
        return lines
    heights = np.array([e - s for s, e in lines])
    typical = float(np.median(heights[heights >= np.median(heights)]))  # rows of overlines alone do not count
    out: list[list[int]] = []
    pending = list(lines)
    while pending:
        s, e = pending.pop(0)
        if e - s <= size * typical:
            out.append([s, e])
            continue
        lo, hi = s + int(0.6 * typical), e - int(0.6 * typical)  # each part a line high
        if hi <= lo:
            out.append([s, e])
            continue
        cut = lo + int(np.argmin(profile[lo:hi]))
        if profile[cut] > 0.1 * profile[s:e].max():
            out.append([s, e])  # no clear valley: one line (a tall title, marks above and below)
            continue
        pending[:0] = [[s, cut], [cut, e]]
    return out


def word_spans(ink: np.ndarray, line: Box, words: int) -> list[tuple[int, int]] | None:
    """x ranges of the ``words`` printed words of a line, or None if they cannot be told apart.

    Words are runs of ink split at the widest gaps; justified lines have wide spaces,
    letters within a word nearly touch.
    """
    cols = ink[line.y0:line.y1, line.x0:line.x1].any(0)
    pieces = runs(cols)
    if len(pieces) < words or words < 1:
        return None
    gaps = sorted(range(len(pieces) - 1), key=lambda i: pieces[i + 1][0] - pieces[i][1], reverse=True)
    cuts = sorted(gaps[:words - 1])
    if words > 1:
        narrowest = min(pieces[i + 1][0] - pieces[i][1] for i in cuts)
        widest_inside = max((pieces[i + 1][0] - pieces[i][1] for i in gaps[words - 1:]), default=0)
        if narrowest <= widest_inside * 1.2:
            return None  # no clear difference between word spaces and letter spacing
    spans, start = [], 0
    for cut in cuts + [len(pieces) - 1]:
        spans.append((line.x0 + int(pieces[start][0]), line.x0 + int(pieces[cut][1])))
        start = cut + 1
    return spans


def text_left_edge(lines: list[Box]) -> int:
    """Left edge of the text block when some lines carry marginal labels (verse numbers).

    Continuation lines start at the text edge; labelled lines start further left.
    """
    starts = np.array(sorted(line.x0 for line in lines))
    if len(starts) < 3:
        return int(starts[0]) if len(starts) else 0
    jumps = np.diff(starts)
    # The text edge is where a good share of lines start; a lone indented line
    # (a centred title) must not be taken for it.
    enough = max(2, 0.25 * len(starts))
    candidates = [k for k in range(len(jumps)) if len(starts) - (k + 1) >= enough]
    if not candidates:
        return int(starts[0])
    k = max(candidates, key=lambda i: jumps[i])
    span = np.median(starts) - starts[0]  # indented titles and paragraph starts do not count
    if jumps[k] < max(20, span * 0.5):
        return int(starts[0])
    return int(starts[k + 1])


def split_margin(ink: np.ndarray, line: Box, text_left: int, slack: int = 15) -> tuple[Box | None, Box]:
    """(marginal label or None, text) of a line, cut where the text block begins."""
    if line.x0 >= text_left - slack:
        return None, line
    region = ink[line.y0:line.y1, line.x0:line.x1]
    blank = ~region.any(0)
    cut = text_left - slack - line.x0
    # Back off to the blank gap before the text edge, so no glyph is cut.
    gaps = [(s, e) for s, e in runs(blank[:cut + slack]) if s > 0]
    if not gaps:
        return None, line
    s, e = gaps[-1]
    rest = np.flatnonzero(region[:, e:].any(0))
    if not len(rest):
        return None, line
    # A verse number is short and set apart; a word space is narrow (the ragged left end of a
    # right-aligned Arabic line is text, not a label).
    if e - s < 0.6 * line.height or s > 3 * line.height:
        return None, line
    return (Box(line.x0, line.y0, line.x0 + int(s), line.y1),
            Box(line.x0 + int(e) + int(rest[0]), line.y0, line.x1, line.y1))
