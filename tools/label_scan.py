"""Label line images of a scanned known text (the Coptic New Testament).

    python tools/label_scan.py data/real/nt models/coptic-crnn-v1/best.pt data/corpus/bohairic_nt.txt

Reads every Coptic line listed in ``lines.tsv`` (see scan_lines.py), finds it
in the reference text and keeps the corrected reading as a label. Writes
``labels.tsv`` (accepted lines, for training) and ``readings.tsv`` (every line
with its reading, status and the matching reference letters, for inspection).
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image  # noqa: E402

from copticocr.data.align import codes, correct, find, letters  # noqa: E402
from copticocr.data.corpus import load_corpus  # noqa: E402
from copticocr.recog.infer import Recognizer  # noqa: E402

BATCH = 48
MIN_LETTERS = 5
MAX_COST = 0.2  # edits per letter for a line to count as located


def read_lines(root: Path) -> list[str]:
    rows = [line.split("\t") for line in (root / "lines.tsv").read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if r[3] == "coptic"]
    rows.sort(key=lambda r: (int(r[1]), int(r[2])))
    return [r[0] for r in rows]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--trust", type=float, default=0.97)
    args = parser.parse_args()

    ref_text = "".join(letters(v) for v in load_corpus(args.corpus))
    ref = codes(ref_text)
    recognizer = Recognizer(args.checkpoint)
    names = read_lines(args.root)

    readings = []
    for i in range(0, len(names), BATCH):
        images = []
        for name in names[i:i + BATCH]:
            with Image.open(args.root / name) as img:
                images.append(img.convert("L"))
        readings.extend(recognizer.recognize_batch(images))
        if i % (BATCH * 100) == 0:
            print(f"read {i}/{len(names)}", file=sys.stderr, flush=True)

    stats = Counter()
    pos = None
    cooldown = 0  # lines to wait before another (slow) search of the whole text
    labels, report = [], []
    for k, (name, (text, conf)) in enumerate(zip(names, readings)):
        if k % 2000 == 0:
            print(f"aligned {k}/{len(names)}: " + ", ".join(f"{a} {b}" for a, b in stats.most_common()),
                  file=sys.stderr, flush=True)
        query = letters(text)
        if len(query) < MIN_LETTERS:
            stats["short"] += 1
            report.append(f"{name}\tshort\t{text}\t")
            continue
        span = None
        windows = []
        if pos is not None:
            windows += [(pos - 40, pos + 3 * len(query) + 80), (pos - 400, pos + 6000),
                        (pos - 5000, pos + 60000)]
        if cooldown == 0:
            windows.append((0, len(ref)))
        else:
            cooldown -= 1
        for lo, hi in windows:
            probe = query
            if hi - lo == len(ref):
                # A longer probe (with the next lines) is needed to be unique in the whole text.
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
                cooldown = 4  # probably a page of other text (an introduction or a title)
            report.append(f"{name}\tnot found\t{text}\t")
            continue
        pos = span[1]
        target = ref_text[span[0]:span[1]]
        label = correct(text, conf, target, trust=args.trust)
        status = "exact" if label == text else "corrected" if label else "rejected"
        stats[status] += 1
        report.append(f"{name}\t{status}\t{text}\t{target}")
        if label:
            labels.append(f"{name}\t{label}\tnt-scan")

    (args.root / "labels.tsv").write_text("".join(r + "\n" for r in labels), encoding="utf-8")
    (args.root / "readings.tsv").write_text("".join(r + "\n" for r in report), encoding="utf-8")
    print(f"{len(names)} lines: " + ", ".join(f"{k} {v}" for k, v in stats.most_common()))


if __name__ == "__main__":
    main()
