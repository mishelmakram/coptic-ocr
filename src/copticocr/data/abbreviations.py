"""Abbreviations (nomina sacra and church shorthand) printed in Coptic books.

Books print ⲡⲟ̅ⲥ̅ for ⲡϭⲟⲓⲥ, ⲫϯ for ⲫ̀ⲛⲟⲩϯ, ⲁ̅ⲗ̅ for ⲁⲗⲗⲏⲗⲟⲩⲓⲁ and so on. The
recognizer transcribes what is printed; this table says which full word an
abbreviation stands for, so synthetic lines can show abbreviations and output
can offer the full word for searching.

Keys are full words without jinkim, in lowercase. A stem may also be
abbreviated after a short prefix (an article or possessive), as in ⲙ̀ⲡⲟ̅ⲥ̅ or
ⲡⲁⲟ̅ⲥ̅.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from .corpus import JINKIM, OVERLINE


def over(letters: str) -> str:
    """Put the supralinear stroke over every letter: ⲓⲏⲥ -> ⲓ̅ⲏ̅ⲥ̅."""
    return "".join(ch + OVERLINE for ch in letters)


@dataclass(frozen=True)
class Abbreviation:
    full: str
    short: tuple[str, ...]
    stem: bool = False  # also after a prefix


ABBREVIATIONS = [
    # God, Lord, Jesus Christ, Spirit
    Abbreviation("ϭⲟⲓⲥ", (over("ⲟⲥ"), over("ϭⲥ")), stem=True),
    Abbreviation("ⲫⲛⲟⲩϯ", ("ⲫϯ",), stem=True),
    Abbreviation("ⲑⲉⲟⲥ", (over("ⲑⲥ"),)),
    Abbreviation("ⲑⲉⲟⲩ", (over("ⲑⲩ"),)),
    Abbreviation("ⲓⲏⲥⲟⲩⲥ", (over("ⲓⲏⲥ"),)),
    Abbreviation("ⲡⲓⲭⲣⲓⲥⲧⲟⲥ", (over("ⲡⲭⲥ"),)),
    Abbreviation("ⲡⲛⲉⲩⲙⲁ", (over("ⲡⲛⲁ"),), stem=True),
    # Names and books
    Abbreviation("ⲓⲱⲁⲛⲛⲏⲥ", (over("ⲓⲱⲁ"),)),
    Abbreviation("ⲙⲁⲧⲑⲉⲟⲥ", (over("ⲙⲁⲧ"),)),
    Abbreviation("ⲙⲁⲣⲕⲟⲥ", (over("ⲙⲁⲣ"),)),
    Abbreviation("ⲗⲟⲩⲕⲁⲥ", (over("ⲗⲟⲩⲕ"),)),
    Abbreviation("ⲇⲁⲩⲓⲇ", (over("ⲇⲁⲇ"),)),
    Abbreviation("ⲡⲓⲥⲣⲁⲏⲗ", (over("ⲡⲓⲥⲗ"),)),
    Abbreviation("ⲓⲥⲣⲁⲏⲗ", (over("ⲓⲥⲗ"),)),
    Abbreviation("ⲓⲉⲣⲟⲩⲥⲁⲗⲏⲙ", (over("ⲓⲗⲏⲙ"),)),
    Abbreviation("ⲯⲁⲗⲙⲟⲥ", (over("ⲯⲁⲗ"),)),
    Abbreviation("ⲉⲩⲁⲅⲅⲉⲗⲓⲟⲛ", (over("ⲉⲩⲁⲅ"),)),
    Abbreviation("ⲡⲁⲣⲑⲉⲛⲟⲥ", (over("ⲡⲁⲣ"),)),
    Abbreviation("ⲥⲧⲁⲩⲣⲟⲥ", (over("ⲥⲧⲣ"),)),
    # Responses
    Abbreviation("ⲁⲗⲗⲏⲗⲟⲩⲓⲁ", (over("ⲁⲗ"),)),
    Abbreviation("ⲁⲙⲏⲛ", (over("ⲁⲙ"),)),
    Abbreviation("ⲭⲉⲣⲉ", (over("ⲭⲉ"),)),
    Abbreviation("ⲁⲣⲓⲡⲣⲉⲥⲃⲉⲩⲓⲛ", (over("ⲁⲣⲓ"),)),
    Abbreviation("ⲇⲟⲝⲁⲥⲓ", (over("ⲇⲟⲝ"),)),
    Abbreviation("ⲉⲑⲟⲩⲁⲃ", (over("ⲉⲑⲩ"),)),
]

PHRASES = [  # several words printed as one abbreviation
    Abbreviation("ⲕⲩⲣⲓⲉ ⲉⲗⲉⲏⲥⲟⲛ", (over("ⲕⲉ"), over("ⲕⲉⲛ"))),
]


def _plain(text: str) -> str:
    return text.replace(JINKIM, "").lower()


_BY_WORD = {a.full: a for a in ABBREVIATIONS if not a.stem}
_STEMS = [a for a in ABBREVIATIONS if a.stem]
MAX_PREFIX = 4  # ⲙ̀ⲡⲉϥ-; longer ones are compounds such as ⲙⲉⲧϭⲟⲓⲥ
_TRAILING = re.compile(r"[^\ẁ-ͯ]+$")


def abbreviate_word(word: str, rng: random.Random) -> str:
    """``word`` printed with an abbreviation, or unchanged when it has none."""
    trail = _TRAILING.search(word)
    tail = trail.group() if trail else ""
    core = word[:len(word) - len(tail)]
    plain = _plain(core)
    capital = core[:1].isupper()
    if plain in _BY_WORD:
        short = rng.choice(_BY_WORD[plain].short)
        return (short[0].upper() + short[1:] if capital else short) + tail
    for a in _STEMS:
        if plain.endswith(a.full) and 0 < len(plain) - len(a.full) <= MAX_PREFIX:
            # Keep the prefix as written (with its jinkim); only the stem changes.
            letters_kept = len(plain) - len(a.full)
            cut, seen = 0, 0
            while seen < letters_kept:
                cut += 1
                if core[cut - 1] != JINKIM:
                    seen += 1
            while cut < len(core) and core[cut] == JINKIM:
                cut += 1
            return core[:cut] + rng.choice(a.short) + tail
        if plain == a.full:
            short = rng.choice(a.short)
            return (short[0].upper() + short[1:] if capital else short) + tail
    return word


def abbreviate(text: str, rng: random.Random, rate: float = 1.0) -> str:
    """Abbreviate each word that has an abbreviation, with probability ``rate``."""
    words = text.split(" ")
    return " ".join(abbreviate_word(w, rng) if rng.random() < rate else w for w in words)


def sample(rng: random.Random) -> str:
    """A random abbreviation, to drop into a synthetic line."""
    a = rng.choice(ABBREVIATIONS + PHRASES)
    return rng.choice(a.short)
