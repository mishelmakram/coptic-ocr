"""Text normalisation shared by the PDF reader and the OCR post-processing."""

import unicodedata

TATWEEL = "ـ"

# Word often stores Arabic with Persian yeh/kaf/heh, which NFKC keeps as-is.
_ARABIC_FIXES = str.maketrans({"ی": "ي", "ک": "ك", "ھ": "ه"})


def normalize_arabic(text: str, keep_tatweel: bool = False) -> str:
    """Fold presentation forms (e.g. from PDF extraction) to plain Arabic letters."""
    text = unicodedata.normalize("NFKC", text).translate(_ARABIC_FIXES)
    if not keep_tatweel:
        text = text.replace(TATWEEL, "")
    return text
