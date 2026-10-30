"""Bohairic text corpora used to generate synthetic training lines.

The main source is the Coptic SCRIPTORIUM Bohairic Old Testament
(CC-BY-SA 4.0, https://github.com/CopticScriptorium/corpora), which keeps the
church orthography with jinkim. Corpora are kept as plain text, one verse per
line, in ``data/corpus/``.
"""

from __future__ import annotations

import html
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Iterable, Iterator

JINKIM = "̀"
OVERLINE = "̅"

_ORIG_GROUP = re.compile(r'<orig_group orig_group="([^"]*)"')
_VERSE = re.compile(r'<verse_n verse_n="')


def is_coptic_letter(ch: str) -> bool:
    return 0x2C80 <= ord(ch) <= 0x2CFF or 0x03E2 <= ord(ch) <= 0x03EF


def clean_word(word: str) -> str:
    """Keep Coptic letters and their marks; drop editorial brackets and junk."""
    word = unicodedata.normalize("NFC", html.unescape(word))
    kept = [ch for ch in word if is_coptic_letter(ch) or ch in (JINKIM, OVERLINE)]
    while kept and not is_coptic_letter(kept[0]):  # a mark needs a base letter
        kept.pop(0)
    return "".join(kept)


def read_scriptorium_tt(path: str | Path) -> Iterator[str]:
    """Yield verses (space separated words) from a Scriptorium ``*_TT.zip``."""
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".tt"):
                continue
            text = archive.read(name).decode("utf-8")
            for chunk in _VERSE.split(text)[1:]:
                words = [clean_word(w) for w in _ORIG_GROUP.findall(chunk)]
                verse = " ".join(w for w in words if w)
                if verse:
                    yield verse


def write_corpus(verses: Iterable[str], path: str | Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as out:
        for verse in verses:
            out.write(verse + "\n")
            count += 1
    return count


def load_corpus(*paths: str | Path) -> list[str]:
    verses = []
    for path in paths:
        verses.extend(line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines())
    return [v for v in verses if v]


def jinkim_ratio(verses: Iterable[str]) -> float:
    """Share of words carrying a jinkim; ~0 means the text lacks church orthography."""
    words = [w for v in verses for w in v.split()]
    return sum(JINKIM in w for w in words) / max(len(words), 1)
