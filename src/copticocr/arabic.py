"""Arabic text as the recognizer reads and writes it.

Printed church books use the Arabic Bible's orthography but rarely all of its
vowel marks, and stretch words with kashida (البابـــا). Text is kept in logical
order; kashida, alef wasla and similar variants are normalized so that the same
printed line always has the same label.
"""

from __future__ import annotations

import re
import unicodedata

LETTERS = "ءآأؤإئابةتثجحخدذرزسشصضطظعغفقكلمنهوىي"
MARKS = "ًٌٍَُِّْٰ"  # tanween (3), fatha, damma, kasra, shadda, sukun, dagger alef
DIGITS = "٠١٢٣٤٥٦٧٨٩"
PUNCTUATION = " ،؛؟.:!«»()-"

_MAP = str.maketrans({
    "ٱ": "ا",  # alef wasla: printed as a plain alef
    "ـ": None,  # kashida only stretches a word
    "‌": None, "‍": None, "‏": None, "‎": None,
    ";": "؛", "?": "؟", ",": "،",
    "ک": "ك", "ی": "ي", "ھ": "ه",  # Persian forms some fonts and PDFs produce
})
_DIGITS = str.maketrans("0123456789", DIGITS)


def normalize(text: str) -> str:
    """One spelling for one printed line: no kashida, plain alef, Arabic punctuation and digits."""
    text = unicodedata.normalize("NFC", text).translate(_MAP).translate(_DIGITS)
    text = "".join(ch for ch in text if ch in LETTERS or ch in MARKS or ch in DIGITS or ch in PUNCTUATION)
    text = re.sub(r"\s+", " ", text).strip()
    # A mark needs a letter before it.
    return re.sub(rf"(^|\s)[{MARKS}]+", r"\1", text)


def strip_marks(text: str) -> str:
    return "".join(ch for ch in text if ch not in MARKS)


def is_letter(ch: str) -> bool:
    return ch in LETTERS


_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا"})


def letters(text: str) -> str:
    """Bare letters, hamza on alef ignored: what is compared with a reference text."""
    return "".join(ch for ch in text if ch in LETTERS).translate(_ALEF)
