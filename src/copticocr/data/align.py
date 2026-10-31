"""Turn recognized lines of a known text (a scanned Bible) into training labels.

The recognizer's reading of a line is located in the reference text and
corrected letter by letter. Spacing, punctuation, capitals and jinkim come from
the reading, since reference editions differ in those; letters come from the
reference. Lines whose reading and reference disagree too much are rejected
rather than guessed.
"""

from __future__ import annotations

import unicodedata

import numpy as np
from rapidfuzz.distance import Levenshtein

from .corpus import OVERLINE, is_coptic_letter


def letter_positions(text: str) -> list[int]:
    return [i for i, ch in enumerate(text) if is_coptic_letter(ch)]


def letters(text: str) -> str:
    """Lowercase Coptic letters only: what is compared with the reference."""
    return "".join(ch.lower() for ch in text if is_coptic_letter(ch))


def codes(text: str) -> np.ndarray:
    return np.frombuffer(text.encode("utf-32-le"), dtype=np.uint32)


def locate(query: str, ref: np.ndarray, free_start: bool = True) -> tuple[int, int]:
    """(end, cost) of the best match of ``query`` inside ``ref`` (edit distance).

    With ``free_start`` the match may begin anywhere, otherwise at ref[0].
    Rows of the DP are vectorized; the in-row (insertion) term is a running minimum.
    """
    n = len(ref)
    ramp = np.arange(n + 1)
    prev = np.zeros(n + 1, dtype=np.int32) if free_start else ramp.astype(np.int32)
    row = np.empty(n + 1, dtype=np.int32)
    for i, q in enumerate(codes(query), 1):
        row[0] = i
        np.minimum(prev[:-1] + (ref != q), prev[1:] + 1, out=row[1:])
        prev = np.minimum.accumulate(row - ramp) + ramp
    end = int(np.argmin(prev))
    return end, int(prev[end])


def find(query: str, ref: np.ndarray, lo: int, hi: int) -> tuple[int, int, int]:
    """(start, end, cost) of ``query`` within ref[lo:hi]."""
    lo, hi = max(0, lo), min(len(ref), hi)
    end, cost = locate(query, ref[lo:hi])
    back = max(lo, lo + end - 2 * len(query) - 10)
    length, _ = locate(query[::-1], ref[back:lo + end][::-1], free_start=False)
    return lo + end - length, lo + end, cost


def correct(reading: str, confidences: list[float], ref: str, max_rate: float = 0.1,
            trust: float = 0.97) -> str | None:
    """The reading with its letters corrected to ``ref``, or None when that is unsafe.

    ``confidences`` holds one value per letter of the reading. A letter the model
    read with confidence of at least ``trust`` is never overruled: such a
    disagreement is more likely a spelling difference between editions.
    """
    positions = letter_positions(reading)
    source = letters(reading)
    ops = Levenshtein.editops(source, ref)
    if len(ops) > max(1, round(len(ref) * max_rate)):
        return None
    if any(op.src_pos in (0, len(source) - 1) or op.src_pos == len(source) for op in ops):
        return None  # at the ends the matched reference span itself is uncertain
    # Overlined words are abbreviations or numerals, which the reference spells out.
    abbreviated = []
    for word in reading.split():
        abbreviated += [OVERLINE in word] * len(letters(word))
    for op in ops:
        near = [op.src_pos, op.src_pos - 1] if op.tag == "insert" else [op.src_pos]
        if any(abbreviated[i] for i in near if 0 <= i < len(abbreviated)):
            return None
    tags = [(op.tag, op.src_pos) for op in ops]
    for (tag, src), (tag2, src2) in zip(tags, tags[1:]):
        if tag == tag2 == "insert" and src == src2 or tag == tag2 == "delete" and src2 == src + 1:
            return None  # a run of missing or extra letters: abbreviation, ligature, bad crop

    chars = list(reading)
    for op in reversed(ops):
        if op.tag == "replace":
            if confidences[op.src_pos] >= trust:
                return None
            at = positions[op.src_pos]
            new = ref[op.dest_pos]
            chars[at] = new.upper() if chars[at].isupper() else new
        elif op.tag == "delete":
            at = positions[op.src_pos]
            end = at + 1
            while end < len(chars) and unicodedata.combining(chars[end]):
                end += 1
            if end > at + 1:
                return None  # the extra letter carries marks; unclear where they belong
            del chars[at:end]
        else:  # insert: a letter the model missed
            at = positions[op.src_pos] if op.src_pos < len(positions) else len(chars)
            if at == len(chars):
                while at > 0 and not is_coptic_letter(chars[at - 1]) and not unicodedata.combining(chars[at - 1]):
                    at -= 1  # before trailing punctuation
            chars.insert(at, ref[op.dest_pos])
    return "".join(chars)
