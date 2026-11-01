"""Label the Arabic lines of a scanned bilingual Bible from its known text (Van Dyck).

    python tools/label_scan_arabic.py data/real/nt models/arabic-crnn-v1/best.pt data/corpus/arabic_nt.txt

Like label_scan.py for Coptic: each Arabic line listed in ``lines.tsv`` is read,
found in the reference, and kept as a label when it matches. Vowel marks and
verse numbers come from the reading (books print only some of the marks); a
letter the model was unsure of may be corrected to the reference. Writes
``labels_arabic.tsv`` and ``readings_arabic.tsv`` next to ``lines.tsv``.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image  # noqa: E402
from rapidfuzz.distance import Levenshtein  # noqa: E402

from copticocr.arabic import LETTERS, letters  # noqa: E402
from copticocr.data.align import codes, find  # noqa: E402
from copticocr.data.corpus import load_corpus  # noqa: E402
from copticocr.recog.infer import Recognizer  # noqa: E402

BATCH = 48
MIN_LETTERS = 6
MAX_COST = 0.2


def read_lines(root: Path) -> list[str]:
    rows = [line.split("\t") for line in (root / "lines.tsv").read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if r[3] == "arabic"]
    rows.sort(key=lambda r: (int(r[1]), int(r[2])))
    return [r[0] for r in rows]


def correct(reading: str, confidences: list[float], ref: str, max_rate: float = 0.1,
            trust: float = 0.97) -> str | None:
    """The reading with unsure letters set to ``ref``, or None unless that is all that differs."""
    positions = [i for i, ch in enumerate(reading) if ch in LETTERS]
    source = letters(reading)
    ops = Levenshtein.editops(source, ref)
    if len(ops) > max(1, round(len(ref) * max_rate)):
        return None
    chars = list(reading)
    for op in ops:
        # Only misread letters are mended; a missing or extra letter, a confident
        # disagreement or one at the line's ends (where the match itself is unsure) is not.
        if op.tag != "replace" or op.src_pos in (0, len(source) - 1) or confidences[op.src_pos] >= trust:
            return None
        chars[positions[op.src_pos]] = ref[op.dest_pos]
    return "".join(chars)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()

    ref_text = "".join(letters(v) for v in load_corpus(args.corpus))
    ref = codes(ref_text)
    recognizer = Recognizer(args.checkpoint)
    names = read_lines(args.root)
    readings = []
    for i in range(0, len(names), BATCH):
        images = [Image.open(args.root / name).convert("L") for name in names[i:i + BATCH]]
        readings.extend(recognizer.recognize_batch(images))
        if i % (BATCH * 100) == 0:
            print(f"read {i}/{len(names)}", file=sys.stderr, flush=True)

    stats, labels, report = Counter(), [], []
    pos, cooldown = None, 0
    for k, (name, (text, conf)) in enumerate(zip(names, readings)):
        query = letters(text)
        if len(query) < MIN_LETTERS:
            stats["short"] += 1
            report.append(f"{name}\tshort\t{text}\t")
            continue
        windows = []
        if pos is not None:
            windows += [(pos - 40, pos + 3 * len(query) + 80), (pos - 400, pos + 6000), (pos - 5000, pos + 60000)]
        if cooldown == 0:
            windows.append((0, len(ref)))
        else:
            cooldown -= 1
        span = None
        for lo, hi in windows:
            probe = query
            if hi - lo == len(ref):  # the whole text: a longer probe is needed to be unique
                probe = query + "".join(letters(t) for t, _ in readings[k + 1:k + 3])
            start, end, cost = find(probe, ref, lo, hi)
            if cost <= MAX_COST * len(probe):
                if probe is not query:
                    start, end, cost = find(query, ref, start - 20, start + 3 * len(query) + 40)
                    if cost > MAX_COST * len(query):
                        continue
                span = (start, end)
                break
        if span is None:
            stats["not found"] += 1
            if (0, len(ref)) in windows:
                cooldown = 4
            report.append(f"{name}\tnot found\t{text}\t")
            continue
        pos = span[1]
        target = ref_text[span[0]:span[1]]
        label = correct(text, conf, target)
        status = "exact" if label == text else "corrected" if label else "rejected"
        stats[status] += 1
        report.append(f"{name}\t{status}\t{text}\t{target}")
        if label:
            labels.append(f"{name}\t{label}\tnt-scan")

    (args.root / "labels_arabic.tsv").write_text("".join(r + "\n" for r in labels), encoding="utf-8")
    (args.root / "readings_arabic.tsv").write_text("".join(r + "\n" for r in report), encoding="utf-8")
    print(f"{len(names)} lines: " + ", ".join(f"{k} {v}" for k, v in stats.most_common()))


if __name__ == "__main__":
    main()
