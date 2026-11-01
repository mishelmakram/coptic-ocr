"""Symbol set of the Coptic line recognizer.

Labels are stored in Unicode order (letter, then its combining mark), but in
print a jinkim sits on the left edge of its letter. The model reads left to
right, so it is trained on *visual order* (mark before letter) and its output
is turned back into Unicode order.
"""

from __future__ import annotations

import unicodedata

from .. import arabic

LETTERS = "ⲁⲃⲅⲇⲉⲋⲍⲏⲑⲓⲕⲗⲙⲛⲝⲟⲡⲣⲥⲧⲩⲫⲭⲯⲱϣϥϧϩϫϭϯ"
MARKS = "̀́̅"  # jinkim, acute jinkim, supralinear stroke
PUNCTUATION = " :.-,;·"


class Charset:
    """Maps symbols to class indices; index 0 is the CTC blank.

    Coptic is trained in visual order (a jinkim before its letter). Arabic is read
    from a mirrored line image, so its text keeps logical order with marks after
    their letter (``rtl``).
    """

    def __init__(self, symbols: str, script: str = "coptic"):
        self.symbols = symbols
        self.script = script
        self.rtl = script == "arabic"
        self.letters = set(arabic.LETTERS) if self.rtl else set(LETTERS)
        self.index = {s: i + 1 for i, s in enumerate(symbols)}

    @classmethod
    def coptic(cls) -> Charset:
        return cls(LETTERS + LETTERS.upper() + MARKS + PUNCTUATION)

    @classmethod
    def arabic(cls) -> Charset:
        return cls(arabic.LETTERS + arabic.MARKS + arabic.DIGITS + arabic.PUNCTUATION, "arabic")

    @classmethod
    def for_script(cls, script: str) -> Charset:
        return cls.arabic() if script == "arabic" else cls.coptic()

    def _order(self, text: str) -> str:
        return text if self.rtl else to_visual(text)

    def _unorder(self, text: str) -> str:
        return text if self.rtl else from_visual(text)

    def __len__(self) -> int:
        return len(self.symbols) + 1

    def encode(self, text: str) -> list[int]:
        """Unicode text -> class indices in visual order. Unknown symbols are dropped."""
        return [self.index[s] for s in self._order(text) if s in self.index]

    def decode(self, indices) -> str:
        """Greedy CTC decoding: merge repeats, drop blanks, back to Unicode order."""
        out, previous = [], 0
        for i in indices:
            i = int(i)
            if i != previous and i != 0:
                out.append(self.symbols[i - 1])
            previous = i
        return self._unorder("".join(out))

    def decode_scored(self, indices, probs) -> tuple[str, list[float]]:
        """Like :meth:`decode`, plus the confidence of each letter (peak frame probability)."""
        out, scores, previous = [], [], 0
        for i, p in zip(indices, probs):
            i, p = int(i), float(p)
            if i != 0 and i == previous:
                scores[-1] = max(scores[-1], p)
            elif i != 0:
                out.append(self.symbols[i - 1])
                scores.append(p)
            previous = i
        letters = [p for s, p in zip(out, scores) if s.lower() in self.letters]
        return self._unorder("".join(out)), letters


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
