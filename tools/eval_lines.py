"""Character error rate of a checkpoint on a folder of labelled line images.

    python tools/eval_lines.py models/coptic-crnn-v1/best.pt data/real/sample_page
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image  # noqa: E402

from copticocr.recog.dataset import read_labels  # noqa: E402
from copticocr.recog.infer import Recognizer  # noqa: E402
from copticocr.recog.metrics import cer  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("folders", nargs="+", type=Path)
    parser.add_argument("--quiet", action="store_true", help="only print the totals")
    args = parser.parse_args()

    recognizer = Recognizer(args.checkpoint)
    for folder in args.folders:
        refs, hyps = [], []
        for path, text in read_labels(folder):
            with Image.open(path) as img:
                hyp = recognizer.recognize(img)
            refs.append(text)
            hyps.append(hyp)
            if not args.quiet:
                mark = "  " if hyp == text else "✗ "
                print(f"{mark}{path.name}\n   ref: {text}\n   hyp: {hyp}")
        print(f"{folder}: {len(refs)} lines, CER {cer(refs, hyps):.2%}")


if __name__ == "__main__":
    main()
