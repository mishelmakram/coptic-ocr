import random

from copticocr.data.abbreviations import ABBREVIATIONS, abbreviate, abbreviate_word
from copticocr.recog.charset import Charset

JINKIM = "̀"
OVERLINE = "̅"


def test_stem_keeps_the_prefix_and_its_jinkim():
    rng = random.Random(0)
    assert abbreviate_word(f"ⲙ{JINKIM}ⲫ{JINKIM}ⲛⲟⲩϯ:", rng) == f"ⲙ{JINKIM}ⲫϯ:"
    assert abbreviate_word("ⲡϭⲟⲓⲥ", rng) in (f"ⲡⲟ{OVERLINE}ⲥ{OVERLINE}", f"ⲡϭ{OVERLINE}ⲥ{OVERLINE}")


def test_long_prefixes_are_compounds_not_articles():
    assert abbreviate_word("ⲧⲉⲕⲙⲉⲧϭⲟⲓⲥ", random.Random(0)) == "ⲧⲉⲕⲙⲉⲧϭⲟⲓⲥ"


def test_capital_and_punctuation_survive():
    assert abbreviate_word("Ⲓⲏⲥⲟⲩⲥ.", random.Random(0)) in (f"Ⲓ{OVERLINE}ⲏ{OVERLINE}ⲥ{OVERLINE}.",
                                                               f"Ⲓⲏ{OVERLINE}ⲥ{OVERLINE}.")


def test_words_without_abbreviation_are_unchanged():
    text = f"ⲡⲉⲛⲓⲱⲧ ⲉⲧϧⲉⲛ ⲛⲓⲫⲏⲟⲩⲓ ⲡⲉⲛⲛⲟⲩϯ"
    assert abbreviate(text, random.Random(0)) == text


def test_every_abbreviation_can_be_recognized():
    charset = Charset.coptic()
    for a in ABBREVIATIONS:
        for short in a.short:
            assert len(charset.encode(short)) == len(short), short
