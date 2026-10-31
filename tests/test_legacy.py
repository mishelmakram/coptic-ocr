from pathlib import Path

import pytest

from copticocr.legacy import get_layout, layout_for_font, layouts
from copticocr.normalize import normalize_arabic

ROOT = Path(__file__).resolve().parents[1]

JINKIM = "̀"
OVERLINE = "̅"


def is_coptic_letter(ch: str) -> bool:
    return 0x2C80 <= ord(ch) <= 0x2CFF or 0x03E2 <= ord(ch) <= 0x03EF


def test_every_lowercase_latin_letter_maps_to_a_coptic_letter():
    for layout in layouts().values():
        for ch in "abcdefghijklmnopqrstuvwxyz":
            assert is_coptic_letter(layout.chars[ch]), (layout.name, ch)


def test_layouts_cover_all_bohairic_letters():
    alphabet = "ⲁⲃⲅⲇⲉⲍⲏⲑⲓⲕⲗⲙⲛⲝⲟⲡⲣⲥⲧⲩⲫⲭⲯⲱϣϥϧϩϫϭϯ"
    for layout in layouts().values():
        produced = set("".join(layout.chars.values()))
        assert set(alphabet) <= produced, (layout.name, set(alphabet) - produced)
        assert set(alphabet.upper()) <= produced, layout.name


@pytest.mark.parametrize("legacy, expected", [
    ("peniwt etqen nivyoui", "ⲡⲉⲛⲓⲱⲧ ⲉⲧϧⲉⲛ ⲛⲓⲫⲏⲟⲩⲓ"),
    ("`nte", "ⲛ" + JINKIM + "ⲧⲉ"),
    ("`pcaji `nte `vnou]", f"ⲡ{JINKIM}ⲥⲁϫⲓ ⲛ{JINKIM}ⲧⲉ ⲫ{JINKIM}ⲛⲟⲩϯ"),
    ("pi=p=n=a e;ouab", f"ⲡⲓⲡ{OVERLINE}ⲛ{OVERLINE}ⲁ{OVERLINE} ⲉⲑⲟⲩⲁⲃ"),
    ("[i", "ϭⲓ"),
])
def test_cs_to_unicode(legacy, expected):
    assert get_layout("CS Avva Shenouda").to_unicode(legacy) == expected


def test_athanasius_postfix_overline_and_letters():
    layout = get_layout("Athanasius")
    assert layout.to_unicode("Pq/c/") == f"Ⲡⲑ{OVERLINE}ⲥ{OVERLINE}"
    assert layout.to_unicode("`n;") == f"ⲛ{JINKIM}ϯ"
    assert layout.to_unicode("]\\'") == "ϣϩϧ"


def test_athanasius_invisible_glyphs_are_dropped():
    # The Kiahk Psalmody has empty quote glyphs, sometimes between a jinkim and its letter.
    layout = get_layout("Athanasius")
    assert layout.to_unicode("Anon ‘'a") == "Ⲁⲛⲟⲛ ϧⲁ"
    assert layout.to_unicode("`‘'en") == f"ϧ{JINKIM}ⲉⲛ"


@pytest.mark.parametrize("name", ["cs", "athanasius"])
def test_round_trip(name):
    layout = get_layout(name)
    text = f"ⲡ{JINKIM}ⲥⲁϫⲓ ⲛ{JINKIM}ⲧⲉ ⲫ{JINKIM}ⲛⲟⲩϯ ⲡⲓⲡ{OVERLINE}ⲛ{OVERLINE}ⲁ{OVERLINE} ϧⲉⲛ ϣⲁ ϩⲁⲛ ϭⲓ"
    assert layout.to_unicode(layout.from_unicode(text)) == text


def test_unmappable_character():
    with pytest.raises(ValueError):
        get_layout("cs").from_unicode("ⲁب")
    assert get_layout("cs").from_unicode("ⲁب", errors="replace") == "a?"


@pytest.mark.parametrize("pdf_font, expected", [
    ("ABCDEF+CSAvvaShenouda", "cs"),
    ("CS Copto Manuscript", "cs"),
    ("Abraam", "athanasius"),
    ("ATHANASIUS-Bold", "athanasius"),
    ("ArialMT", None),
])
def test_font_detection(pdf_font, expected):
    layout = layout_for_font(pdf_font)
    assert (layout.name if layout else None) == expected


def test_normalize_arabic_presentation_forms():
    assert normalize_arabic("ﺛﺎﻧﯾﺎً") == "ثانياً"
    assert normalize_arabic("يـــا") == "يا"
    assert normalize_arabic("يذھب") == "يذهب"


LESSONS = ROOT / "resources" / "Coptic lessons.pdf"


@pytest.mark.skipif(not LESSONS.exists(), reason="local sample PDF not available")
def test_lessons_pdf_has_no_unmapped_coptic():
    from copticocr.legacy.pdf import extract_text

    text = "\n".join(extract_text(LESSONS))
    assert "�" not in text
    assert "ⲡⲉⲛⲓⲱⲧ ⲉⲧϧⲉⲛ ⲛⲓⲫⲏⲟⲩⲓ" in text
    # Bohairic jinkim is typed before its letter and must land on that letter.
    assert f"ⲥ{JINKIM}ⲙⲟⲩ" in text
    assert f"ϣ{JINKIM}ⲗⲏⲗ" in text
    assert sum(is_coptic_letter(ch) for ch in text) > 5000
    # A Coptic mark never starts a word (a lone mark shown as an example is fine).
    for word in text.split():
        assert len(word) == 1 or word[0] not in (JINKIM, OVERLINE), word
