"""Rebuild running text from labelled lines, for use as a synthetic-text corpus.

    python tools/lines_to_corpus.py data/real/kiahk/labels.tsv data/corpus/kiahk.txt

Takes the first variant of each line in reading order, joins words split by
a hyphen at the line end, and writes one sentence (ending in ".") per line.
"""

import argparse
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("labels", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()

    lines = []
    for row in args.labels.read_text(encoding="utf-8").splitlines():
        name, text = row.split("\t")[:2]
        if name.endswith("_0.png"):
            lines.append(text)
    text = " ".join(lines)
    text = re.sub(r"-\s+", "", text)
    sentences = [s.strip() for s in re.split(r"(?<=\.)\s+", text)]
    sentences = [s for s in sentences if len(s.split()) >= 3]
    args.out.write_text("\n".join(sentences) + "\n", encoding="utf-8")
    print(f"{len(sentences)} sentences from {len(lines)} lines")


if __name__ == "__main__":
    main()
