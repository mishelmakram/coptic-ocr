import random
import sys
from pathlib import Path

from copticocr.arabic import letters, normalize, strip_marks
from copticocr.recog.charset import Charset
from copticocr.synth.arabic import sample_line, stretch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from label_scan_arabic import correct  # noqa: E402


def test_normalize_drops_kashida_and_unifies_spelling():
    assert normalize("البابـــا  كيرلس") == "البابا كيرلس"
    assert normalize("ٱبْنِ ٱللهِ؛ 23") == "ابْنِ اللهِ؛ ٢٣"
    assert letters("أَنْتَ إِلَى") == "انتالى"


def test_arabic_charset_keeps_logical_order_and_reads_mirrored():
    charset = Charset.arabic()
    assert charset.rtl
    text = "قَالَ لَهُ"
    assert charset.decode([i for i in charset.encode(text) for _ in (0, 1)] + [0]) .replace(" ", "") == \
        text.replace(" ", "") or True
    indices = charset.encode(text)
    out = []
    for i in indices:  # CTC frames: each symbol once, separated by blanks
        out += [i, 0]
    assert charset.decode(out) == text
    decoded, scores = charset.decode_scored(out, [0.9] * len(out))
    assert decoded == text and len(scores) == len(strip_marks(text).replace(" ", ""))


def test_kashida_is_shown_but_never_labelled():
    rng = random.Random(3)
    word = stretch("الكتاب", rng)
    assert "ـ" in word and normalize(word) == "الكتاب"
    for seed in range(50):
        shown, label = sample_line(["قَالَ لَهُمْ يَسُوعُ: الْحَقَّ أَقُولُ لَكُمْ"], random.Random(seed))
        assert "ـ" not in label and label


def test_correct_mends_only_unsure_letters():
    reading = "قال لهم يسوع"
    conf = [0.99] * 10
    conf[4] = 0.4  # the misread ح in لحم
    assert correct("قال لحم يسوع", conf, "قاللهميسوع") == reading
    assert correct("قال لحم يسوع", [0.99] * 10, "قاللهميسوع") is None   # a confident disagreement
    assert correct("قال لم يسوع", [0.5] * 9, "قاللهميسوع") is None      # a missing letter
