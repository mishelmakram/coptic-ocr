"""Command line access to the legacy font converter.

    copticocr-legacy convert --font "CS Avva Shenouda" "peniwt etqen nivyoui"
    copticocr-legacy convert --font cs --reverse "ⲡⲉⲛⲓⲱⲧ"
    copticocr-legacy pdf "Coptic lessons.pdf" -o lessons.txt
"""

import argparse
import sys
from pathlib import Path

from .converter import get_layout
from .pdf import extract_text


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="copticocr-legacy", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    convert = sub.add_parser("convert", help="convert a string")
    convert.add_argument("text")
    convert.add_argument("--font", required=True, help="font family or layout name (cs, athanasius)")
    convert.add_argument("--reverse", action="store_true", help="Unicode -> legacy font")

    pdf = sub.add_parser("pdf", help="extract a typed PDF to Unicode text")
    pdf.add_argument("path", type=Path)
    pdf.add_argument("-o", "--output", type=Path)

    args = parser.parse_args(argv)
    if args.command == "convert":
        layout = get_layout(args.font)
        print(layout.from_unicode(args.text) if args.reverse else layout.to_unicode(args.text))
    else:
        text = "\n\f\n".join(extract_text(args.path))
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text)


if __name__ == "__main__":
    main()
