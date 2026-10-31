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

from . import abbreviations
from .corpus import OVERLINE, is_coptic_letter



def letter_positions(text: str) -> list[int]:
    return [i for i, ch in enumerate(text) if is_coptic_letter(ch)]


def letters(text: str) -> str:
    """Lowercase Coptic letters only: what is compared with the reference."""
    return "".join(ch.lower() for ch in text if is_coptic_letter(ch))


def is_short_form(word: str) -> bool:
    """Whether bare letters spell a printed abbreviation, as when the model missed its stroke (ⲡⲟⲥ)."""
    return abbreviations.match(word) is not None


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


def _restore_stroke(word: str, short: str) -> str:
    """Put the stroke of ``short`` (ⲟ̅ⲥ̅) on the matching last letters of ``word`` (ⲡⲟⲥ)."""
    strokes = [i + 1 < len(short) and short[i + 1] == OVERLINE for i, ch in enumerate(short) if ch != OVERLINE]
    chars, k = list(word), len(strokes)
    for i in range(len(chars) - 1, -1, -1):
        if k == 0:
            break
        if is_coptic_letter(chars[i]):
            k -= 1
            if strokes[k]:
                end = i + 1
                while end < len(chars) and unicodedata.combining(chars[end]):
                    end += 1
                chars.insert(end, OVERLINE)
    return "".join(chars)


def _strokes(word: str) -> list[bool]:
    """For each letter of ``word``, whether it carries a stroke."""
    out = []
    for ch in word:
        if is_coptic_letter(ch):
            out.append(False)
        elif ch == OVERLINE and out:
            out[-1] = True
    return out


def _closest_form(word: str, found) -> str:
    """Of the printed forms with these letters, the one whose stroke best fits what was read."""
    a, short = found
    bare = short.replace(OVERLINE, "")
    seen = _strokes(word)[-len(bare):]
    forms = [f for f in a.short if f.replace(OVERLINE, "") == bare]
    return max(forms, key=lambda f: sum(x == y for x, y in zip(_strokes(f), seen)))


def _is_numeral(word: str) -> bool:
    """Every letter under one stroke, as in ⲓ̅ⲃ̅ (12)."""
    return OVERLINE * 2 not in word and all(_strokes(word))


def correct(reading: str, confidences: list[float], ref: str, max_rate: float = 0.1,
            trust: float = 0.97) -> str | None:
    """The reading with its letters corrected to ``ref``, or None when that is unsafe.

    ``confidences`` holds one value per letter of the reading. A letter the model
    read with confidence of at least ``trust`` is never overruled: such a
    disagreement is more likely a spelling difference between editions.

    Abbreviations are kept as printed: where the reading has ⲡⲟ̅ⲥ̅, the reference's
    ϭⲟⲓⲥ is taken to match it (and a stroke the model missed is put back).
    Overlined numerals are kept as read and left out of the comparison.
    """
    # Each letter's word, and whether that word is plain text, an abbreviation or a numeral.
    words, kinds = [], []
    for word in reading.split(" "):
        bare = letters(word)
        found = abbreviations.match(bare) if bare else None
        if found is not None:
            # One stroke pattern per abbreviation, whatever part of the stroke the model saw.
            word = _restore_stroke(word.replace(OVERLINE, ""), _closest_form(word, found))
            kinds += [("short", len(words), found)] * len(bare)
        elif OVERLINE in word:
            if not _is_numeral(word):
                return None  # a stroke over part of a word, or a doubled one: a misreading
            kinds += [("numeral", len(words), None)] * len(bare)
        else:
            kinds += [("text", len(words), None)] * len(bare)
        words.append(word)
    reading = " ".join(words)
    positions = letter_positions(reading)

    # The reference with each abbreviated word shortened as printed.
    target, cursor = ref, 0
    for i, (kind, word_index, found) in enumerate(kinds):
        if kind != "short" or i > 0 and kinds[i - 1][1] == word_index:
            continue
        full, short = found[0].full, found[1].replace(OVERLINE, "")
        at = target.find(full, cursor)
        if at < 0:
            return None
        target = target[:at] + short + target[at + len(full):]
        cursor = at + len(short)

    kept = [i for i, k in enumerate(kinds) if k[0] != "numeral"]
    every = letters(reading)
    source = "".join(every[i] for i in kept)
    kind_of = [kinds[i] for i in kept]
    ops = Levenshtein.editops(source, target)
    if len(ops) > max(1, round(len(target) * max_rate)):
        return None
    if any(op.src_pos in (0, len(source) - 1) or op.src_pos == len(source) for op in ops):
        return None  # at the ends the matched reference span itself is uncertain
    for op in ops:
        near = [op.src_pos, op.src_pos - 1] if op.tag == "insert" else [op.src_pos]
        if any(kind_of[i][0] != "text" for i in near if 0 <= i < len(kind_of)):
            return None  # an abbreviation that does not match the reference exactly
    # Several letters missing from one word: an abbreviation the table does not know.
    inserted = [kind_of[min(op.src_pos, len(kind_of) - 1)][1] for op in ops if op.tag == "insert" and kind_of]
    if len(inserted) != len(set(inserted)):
        return None
    tags = [(op.tag, op.src_pos) for op in ops]
    for (tag, src), (tag2, src2) in zip(tags, tags[1:]):
        if tag == tag2 == "insert" and src == src2 or tag == tag2 == "delete" and src2 == src + 1:
            return None  # a run of missing or extra letters: ligature, bad crop

    chars = list(reading)
    for op in reversed(ops):
        letter = kept[op.src_pos] if op.src_pos < len(kept) else None
        if op.tag == "replace":
            if confidences[letter] >= trust:
                return None
            at = positions[letter]
            new = target[op.dest_pos]
            chars[at] = new.upper() if chars[at].isupper() else new
        elif op.tag == "delete":
            at = positions[letter]
            end = at + 1
            while end < len(chars) and unicodedata.combining(chars[end]):
                end += 1
            if end > at + 1:
                return None  # the extra letter carries marks; unclear where they belong
            del chars[at:end]
        else:  # insert: a letter the model missed
            at = positions[letter] if letter is not None else len(chars)
            if at == len(chars):
                while at > 0 and not is_coptic_letter(chars[at - 1]) and not unicodedata.combining(chars[at - 1]):
                    at -= 1  # before trailing punctuation
            chars.insert(at, target[op.dest_pos])
    return "".join(chars)
