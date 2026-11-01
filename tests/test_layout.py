import numpy as np

from copticocr.layout.projection import Box, find_lines, skip_header, split_further, split_margin


def page(width=600, height=300):
    return np.zeros((height, width), bool)


def test_a_third_column_is_split_off():
    ink = page()
    for y in range(20, 280, 30):  # two blocks of lines with a blank strip between them
        ink[y:y + 15, 10:180] = True
        ink[y:y + 15, 240:400] = True
    parts = split_further(ink, Box(10, 20, 400, 280), ink.shape[1])
    assert [(p.x0, p.x1) for p in parts] == [(10, 180), (240, 400)]


def test_one_column_with_word_spaces_stays_whole():
    ink = page()
    for k, y in enumerate(range(20, 280, 30)):
        gap = 60 + 25 * (k % 4)  # the spaces fall in different places on each line
        ink[y:y + 15, 10:gap] = True
        ink[y:y + 15, gap + 8:400] = True
    assert split_further(ink, Box(10, 20, 400, 280), ink.shape[1]) == [Box(10, 20, 400, 280)]


def test_an_arabic_baseline_is_not_a_header_rule():
    ink = page(600, 600)
    for x in range(10, 590, 40):  # a long baseline broken between words
        ink[30:33, x:x + 34] = True
    box = Box(0, 0, 600, 600)
    assert skip_header(ink, box) == box
    ink[60:62, 5:595] = True  # a real rule
    assert skip_header(ink, box).y0 == 62


def test_the_ragged_end_of_a_right_aligned_line_is_text():
    ink = page()
    ink[100:120, 100:140] = True  # a word
    ink[100:120, 146:400] = True  # the rest of the line, after a word space
    label, text = split_margin(ink, Box(100, 100, 400, 120), text_left=200)
    assert label is None and text == Box(100, 100, 400, 120)


def test_a_verse_number_in_the_margin_is_a_label():
    ink = page()
    ink[100:120, 100:120] = True  # the number
    ink[100:120, 200:400] = True  # the text, well apart
    label, text = split_margin(ink, Box(100, 100, 400, 120), text_left=200)
    assert label == Box(100, 100, 120, 120) and text.x0 == 200


def test_marks_far_apart_do_not_join_lines():
    ink = page(400, 400)
    ink[20:40, 10:300] = True
    ink[44:46, 50:60] = True    # a descender's tail under the first line
    ink[130:132, 80:90] = True  # an accent over the second line, far below
    ink[134:154, 10:300] = True
    lines = find_lines(ink, Box(0, 0, 400, 400))
    assert [(b.y0, b.y1) for b in lines] == [(20, 46), (130, 154)]
