"""Symbol set of the Coptic line recognizer.

Labels are stored in Unicode order (letter, then its combining mark), but in
print a jinkim sits on the left edge of its letter. The model reads left to
right, so it is trained on *visual order* (mark before letter) and its output
is turned back into Unicode order.
"""

from __future__ import annotations

import unicodedata

LETTERS = "ⲁⲃⲅⲇⲉⲋⲍⲏⲑⲓⲕⲗⲙⲛⲝⲟⲡⲣⲥⲧⲩⲫⲭⲯⲱϣϥϧϩϫϭϯ"
MARKS = "̀́̅"  # jinkim, acute jinkim, supralinear stroke
PUNCTUATION = " :.-,;·"


class Charset:
    """Maps symbols to class indices; index 0 is the CTC blank."""

    def __init__(self, symbols: str):
        self.symbols = symbols
        self.index = {s: i + 1 for i, s in enumerate(symbols)}

    @classmethod
    def coptic(cls) -> Charset:
        return cls(LETTERS + LETTERS.upper() + MARKS + PUNCTUATION)

    def __len__(self) -> int:
        return len(self.symbols) + 1

    def encode(self, text: str) -> list[int]:
        """Unicode text -> class indices in visual order. Unknown symbols are dropped."""
        return [self.index[s] for s in to_visual(text) if s in self.index]

    def decode(self, indices) -> str:
        """Greedy CTC decoding: merge repeats, drop blanks, back to Unicode order."""
        out, previous = [], 0
        for i in indices:
            i = int(i)
            if i != previous and i != 0:
                out.append(self.symbols[i - 1])
            previous = i
        return from_visual("".join(out))


def to_visual(text: str) -> str:
    """Move every combining mark in front of its base letter."""
    out: list[str] = []
    for ch in text:
        if unicodedata.combining(ch) and out:
            # The base letter stays last; earlier marks keep their order.
            out.insert(len(out) - 1, ch)
        else:
            out.append(ch)
    return "".join(out)


def from_visual(text: str) -> str:
    """Inverse of :func:`to_visual`: marks follow their base letter again."""
    out: list[str] = []
    pending: list[str] = []
    for ch in text:
        if unicodedata.combining(ch):
            pending.append(ch)
        else:
            out.append(ch)
            if pending and not ch.isspace():
                out.extend(pending)
                pending.clear()
    out.extend(pending)
    return "".join(out)
