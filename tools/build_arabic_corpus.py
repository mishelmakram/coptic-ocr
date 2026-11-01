"""Turn the Arabic Van Dyck Bible (USFM, public domain) into corpus files, one verse per line.

    python tools/build_arabic_corpus.py data/corpus/raw/vandyck data/corpus

Writes ``arabic_ot.txt`` (books 1-39) and ``arabic_nt.txt`` (40-66) in canonical
order, normalized as the recognizer reads Arabic (see ``copticocr.arabic``).
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from copticocr.arabic import normalize  # noqa: E402


def verses(path: Path):
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"\\v\s+\d+\S*\s+(.*)", line)
        if match:
            text = normalize(re.sub(r"\\[a-z]+\d*\*?", " ", match.group(1)))
            if text:
                yield text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("usfm", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    files = sorted(args.usfm.glob("*.SFM"))
    for name, books in (("arabic_ot.txt", files[:39]), ("arabic_nt.txt", files[39:])):
        lines = [v for f in books for v in verses(f)]
        (args.out / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(name, len(books), "books", len(lines), "verses")


if __name__ == "__main__":
    main()
