import pytest

from copticocr.recog.charset import Charset, from_visual, to_visual
from copticocr.recog.metrics import cer, edit_distance

JINKIM = "̀"
OVERLINE = "̅"


@pytest.mark.parametrize("text", [
    f"ⲛ{JINKIM}ⲧⲉ ⲫ{JINKIM}ⲛⲟⲩϯ",
    f"ⲡ{OVERLINE}ⲟ{OVERLINE}ⲥ{OVERLINE} :",
    f"ⲁ{JINKIM}{OVERLINE}ⲃ",
    "ⲉϥ-",
])
def test_visual_order_round_trip(text):
    assert from_visual(to_visual(text)) == text


def test_visual_order_puts_jinkim_first():
    assert to_visual(f"ⲛ{JINKIM}ⲧⲉ") == f"{JINKIM}ⲛⲧⲉ"


def test_ctc_decode_merges_repeats_and_drops_blanks():
    charset = Charset.coptic()
    encoded = charset.encode(f"ⲛ{JINKIM}ⲧⲧⲉ")
    j, n, t, e = encoded[0], encoded[1], encoded[2], encoded[4]
    frames = [0, j, j, n, 0, t, t, 0, t, e, e, 0]
    assert charset.decode(frames) == f"ⲛ{JINKIM}ⲧⲧⲉ"


def test_charset_covers_uppercase_and_drops_unknown():
    charset = Charset.coptic()
    assert len(charset.encode("Ⲫⲁ")) == 2
    assert charset.encode("ⲁxⲃ") == charset.encode("ⲁⲃ")


def test_cer():
    assert edit_distance("ⲁⲃⲅ", "ⲁⲅ") == 1
    assert cer(["ⲁⲃⲅⲇ"], ["ⲁⲃⲅⲇ"]) == 0
    assert cer(["ⲁⲃⲅⲇ"], ["ⲁⲃ"]) == 0.5
