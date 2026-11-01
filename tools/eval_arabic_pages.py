"""Letter error rate of the Arabic read from whole pages against hand-typed text.

    python tools/eval_arabic_pages.py models/arabic-crnn-v2/best.pt data/real/arabic_pages/truth.tsv

``truth.tsv``: page image path, then its Arabic lines top to bottom separated by
``|``. Vowel marks are ignored (books print only some of them).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image  # noqa: E402
from rapidfuzz.distance import Levenshtein  # noqa: E402

from copticocr.arabic import normalize, strip_marks  # noqa: E402
from copticocr.pipeline import Engine  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    checkpoint, truth = Path(sys.argv[1]), Path(sys.argv[2])
    engine = Engine(sorted(Path("models").glob("coptic-*/best.pt"), key=lambda p: p.stat().st_mtime)[-1],
                    arabic_checkpoint=checkpoint)
    errors = total = 0
    for row in truth.read_text(encoding="utf-8").splitlines():
        path, lines = row.split("\t")
        result = engine.read(Image.open(path))
        read = [l for l in result.lines if l.script == "arabic" and l.text]
        read.sort(key=lambda l: l.box.y0)
        got = strip_marks(normalize(" ".join(l.text for l in read)))
        want = strip_marks(normalize(" ".join(lines.split("|"))))
        e = Levenshtein.distance(got, want)
        errors, total = errors + e, total + len(want)
        print(f"{Path(path).name}: {e} errors in {len(want)} characters")
    print(f"letter error rate {100 * errors / total:.2f}%")


if __name__ == "__main__":
    main()
