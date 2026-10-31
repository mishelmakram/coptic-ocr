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


def remove_rules(ink: np.ndarray, vertical: float = 0.15, horizontal: float = 0.25) -> np.ndarray:
    """The ink without frames and column rules: straight runs longer than any glyph."""
    # Scanned rules are a little slanted and broken: measure on a thickened copy.
    thick = _spread(_spread(ink, 1, 1), 0, 1)
    rules = _long_runs(thick, int(ink.shape[0] * vertical))
    rules |= _long_runs(_spread(thick, 1, 1).T, int(ink.shape[1] * horizontal)).T
    return ink & ~_spread(_spread(rules, 1, 1), 0, 1)


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
    """Left and right column of a two-column page, split at the widest blank gutter."""
    height, width = ink.shape
    rows = np.flatnonzero(ink.sum(1) > 0)
    cols = np.flatnonzero(ink.sum(0) > 0)
    if not len(rows):
        return None
    profile = smooth(ink.sum(0).astype(float), 5)
    gap = widest_gap(profile, int(width * lo), int(width * hi), height * 0.002)
    if gap is None or gap[1] - gap[0] < width * 0.005:
        return None
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    return Box(int(cols[0]), top, int(gap[0]), bottom), Box(int(gap[1]), top, int(cols[-1]) + 1, bottom)


def skip_header(ink: np.ndarray, box: Box, search: float = 0.12) -> Box:
    """Drop the running head: everything down to a horizontal rule near the top, if any."""
    region = ink[box.y0:box.y0 + int(ink.shape[0] * search), box.x0:box.x1]
    full = np.flatnonzero(region.mean(1) > 0.6)
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

    out = []
    for s, e in lines:
        cols = np.flatnonzero(region[s:e].any(0))
        out.append(Box(box.x0 + int(cols[0]), box.y0 + int(s), box.x0 + int(cols[-1]) + 1, box.y0 + int(e)))
    return out


def text_left_edge(lines: list[Box]) -> int:
    """Left edge of the text block when some lines carry marginal labels (verse numbers).

    Continuation lines start at the text edge; labelled lines start further left.
    """
    starts = np.array(sorted(line.x0 for line in lines))
    if len(starts) < 3:
        return int(starts[0]) if len(starts) else 0
    jumps = np.diff(starts)
    k = int(np.argmax(jumps))
    span = starts[-1] - starts[0]
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
    return (Box(line.x0, line.y0, line.x0 + int(s), line.y1),
            Box(line.x0 + int(e) + int(rest[0]), line.y0, line.x1, line.y1))
