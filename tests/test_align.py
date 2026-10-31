import numpy as np

from copticocr.data.align import codes, correct, find, letters
from copticocr.layout.projection import Box, find_lines, split_margin, text_left_edge
from copticocr.recog.charset import Charset

JINKIM = "̀"


def test_letters_drop_marks_spaces_and_case():
    assert letters(f"Ⲛ{JINKIM}ⲑⲟϥ ⲡⲉ:") == "ⲛⲑⲟϥⲡⲉ"


def test_find_locates_a_line_with_errors():
    ref = "ⲁⲃⲅⲇⲉ" * 20 + "ⲡⲉϫⲁϥⲛⲱⲟⲩϫⲉⲛⲓⲙⲓⲥⲓ" + "ⲁⲃⲅⲇⲉ" * 20
    start, end, cost = find("ⲡⲉϫⲁϥⲛⲱⲟⲩϫⲉⲛⲓⲙⲓⲣⲓ", codes(ref), 0, len(ref))
    assert ref[start:end] == "ⲡⲉϫⲁϥⲛⲱⲟⲩϫⲉⲛⲓⲙⲓⲥⲓ"
    assert cost == 1


def test_correct_fixes_an_unsure_letter_and_keeps_jinkim_and_spacing():
    reading = f"ⲡⲉϫⲁϥ ⲛⲱⲟⲩ: ϫⲉ ⲛ{JINKIM}ⲧⲉ"
    confidences = [0.99] * 14
    confidences[1] = 0.6  # the model was unsure of the second letter
    reading = reading.replace("ⲉ", "ⲟ", 1)
    assert correct(reading, confidences, "ⲡⲉϫⲁϥⲛⲱⲟⲩϫⲉⲛⲧⲉ") == f"ⲡⲉϫⲁϥ ⲛⲱⲟⲩ: ϫⲉ ⲛ{JINKIM}ⲧⲉ"


def test_correct_keeps_capitals():
    assert correct("Ⲡⲉϫⲟϥ", [0.99, 0.99, 0.99, 0.5, 0.99], "ⲡⲉϫⲁϥ") == "Ⲡⲉϫⲁϥ"


def test_correct_refuses_to_overrule_a_confident_letter():
    assert correct("ⲡⲉϫⲟϥ", [0.99] * 5, "ⲡⲉϫⲁϥ") is None


def test_correct_rejects_runs_of_missing_letters():
    # An abbreviation (ⲓⲏ̅ⲥ̅) against the spelled-out word.
    assert correct("ⲛϫⲉ ⲓⲏⲥ", [0.5] * 6, "ⲛϫⲉⲓⲏⲥⲟⲩⲥ") is None


def test_decode_scored_gives_one_confidence_per_letter():
    charset = Charset.coptic()
    j, n, t = charset.encode(f"ⲛ{JINKIM}ⲧ")
    text, scores = charset.decode_scored([j, n, n, 0, t], [0.9, 0.7, 0.8, 1.0, 0.95])
    assert text == f"ⲛ{JINKIM}ⲧ"
    assert scores == [0.8, 0.95]


def page_with_lines():
    ink = np.zeros((200, 400), dtype=bool)
    ink[20:40, 100:380] = True   # line with a verse number
    ink[20:40, 20:50] = True     # the verse number
    ink[12:15, 150:155] = True   # a jinkim above the line
    ink[60:80, 100:300] = True   # continuation line
    ink[100:120, 100:390] = True
    return ink


def test_find_lines_attaches_marks_to_their_line():
    lines = find_lines(page_with_lines(), Box(0, 0, 400, 200))
    assert [(line.y0, line.y1) for line in lines] == [(12, 40), (60, 80), (100, 120)]


def test_split_margin_cuts_off_verse_numbers():
    ink = page_with_lines()
    lines = find_lines(ink, Box(0, 0, 400, 200))
    left = text_left_edge(lines)
    assert left == 100
    label, text = split_margin(ink, lines[0], left)
    assert (label.x0, label.x1) == (20, 50)
    assert text.x0 == 100
    assert split_margin(ink, lines[1], left) == (None, lines[1])


def test_correct_rejects_edits_at_the_line_ends():
    # An extra letter at the start may mean the matched reference span is off.
    assert correct("ⲫⲡⲉϫⲁϥ ⲛⲱⲟⲩ", [0.5] * 10, "ⲡⲉϫⲁϥⲛⲱⲟⲩ") is None
