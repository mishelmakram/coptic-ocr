"""Download the Bohairic corpora and write them as plain text to data/corpus/.

    python tools/build_corpus.py [--lessons "resources/Coptic lessons.pdf"]

Source: Coptic SCRIPTORIUM (CC-BY-SA 4.0), https://github.com/CopticScriptorium/corpora
The Old Testament keeps church orthography (jinkim); the New Testament does not.
"""

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from copticocr.data.corpus import clean_word, jinkim_ratio, read_scriptorium_tt, write_corpus  # noqa: E402

BASE = "https://raw.githubusercontent.com/CopticScriptorium/corpora/master"
SOURCES = {
    "bohairic_ot": f"{BASE}/bohairic.ot/bohairic.ot_TT.zip",
    "bohairic_nt": f"{BASE}/bohairic.nt/bohairic.nt_TT.zip",
}


def lessons_lines(pdf: Path) -> list[str]:
    import pymupdf

    from copticocr.legacy.pdf import page_lines

    lines = []
    with pymupdf.open(pdf) as doc:
        for page in doc:
            for line in page_lines(page):
                words = (clean_word(w) for s in line if s.coptic for w in s.text.split())
                text = " ".join(w for w in words if w)
                if text:
                    lines.append(text)
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/corpus"))
    parser.add_argument("--lessons", type=Path, help="a typed PDF in a legacy Coptic font")
    args = parser.parse_args()

    raw = args.out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        archive = raw / f"{name}_TT.zip"
        if not archive.exists():
            print("downloading", url)
            urllib.request.urlretrieve(url, archive)
        verses = list(read_scriptorium_tt(archive))
        write_corpus(verses, args.out / f"{name}.txt")
        print(f"{name}: {len(verses)} verses, jinkim on {jinkim_ratio(verses):.0%} of words")

    if args.lessons:
        lines = lessons_lines(args.lessons)
        write_corpus(lines, args.out / "lessons.txt")
        print(f"lessons: {len(lines)} lines")


if __name__ == "__main__":
    main()
