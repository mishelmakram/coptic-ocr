# Coptic OCR

Open-source OCR for Coptic (Bohairic) liturgical books on Windows: scanned
books in, searchable and re-typeset PDFs out. Pages mixing Coptic and Arabic
columns are supported, as are the legacy ANSI Coptic fonts (CS fonts,
Athanasius, Abraam) used by most church publications.

> برنامج مجاني ومفتوح المصدر لويندوز، بيقرا كتب الكنيسة القبطية الممسوحة ضوئياً (قبطي بحيري وعربي)
> وبيحوّلها لـ PDF قابل للبحث، أو كتاب مُعاد صفّه، أو Word، أو نص، وبيحسّن جودة الصفحات.

## تنزيل البرنامج · Download

From the [Releases](../../releases/latest) page:

- **`CopticOCR-x.y.z-setup.exe`**: installs the program (no administrator rights needed).
  · ملف التثبيت.
- **`CopticOCR-x.y.z-portable.zip`**: unzip and run `CopticOCR.exe`, from a folder or a USB
  stick; settings stay beside it. · نسخة محمولة من غير تثبيت.

Windows 10 or 11, 64-bit. Everything runs on your own computer: no internet, no account.

## What it does · البرنامج بيعمل إيه

- **Reads** Coptic and Arabic: one column, two (Coptic | Arabic) or three (Coptic | Coptic in
  Arabic letters | Arabic), with verse numbers in the margin and titles across the columns.
- **Review:** every line read is shown beside the page; unsure lines are marked for a look,
  and the Coptic can be typed with the keyboard layout of the CS fonts.
- **Exports**
  - a book PDF re-typeset in clean type, Coptic beside Arabic, stanza by stanza;
  - a searchable PDF: the page as scanned, with its text hidden behind it;
  - Word (as a book, or line by line), with the Coptic in Unicode or a legacy font;
  - plain text.
- **Enhances** scans: white paper, black ink, faded print brought out whole, letters traced into
  sharp curves at their printed weight, so the page stays crisp at any zoom.
- Text typed in the legacy fonts (CS, Athanasius, Abraam), including whole PDFs, converts to Unicode
  with the `copticocr-legacy` command (below).
- Arabic and English interface; light and dark themes.

## Status

Version 0.1: the recognizers are trained on a few books and on generated lines, and read
clean print well; old or unusual typefaces may need more review. Reports and sample pages
are welcome in [Issues](../../issues).

## Building from source

```bash
pip install -e .[dev]
copticocr                      # the program
pytest                         # the tests
```

The trained models are not in the repository (they are inside the releases). To build the
installer, see [`packaging/README.md`](packaging/README.md).

## How it works

1. **Ingest:** PDF or images, page by page.
2. **Layout:** columns, lines and their script (Coptic / Arabic), by ink projection profiles.
3. **Recognizers:** a line-level CRNN with CTC for Coptic, and one for Arabic, trained mostly on
   synthetic lines; run with ONNX Runtime in the program.
4. **Post-processing:** jinkim and overline normalisation, hyphen joining.
5. **Output:** the formats above.

## Legacy font converter

| Layout | Fonts |
|---|---|
| `cs` | CS Avva Shenouda, CS Coptic Manuscript, CS Copto Manuscript |
| `athanasius` | Athanasius, Abraam |

Tables live in [`src/copticocr/legacy/maps`](src/copticocr/legacy/maps). Marks
typed before their letter (the jinkim `` ` ``) are listed under `prefix_marks`,
marks drawn over the previous letter under `postfix_marks`. Glyphs whose meaning
is not confirmed are listed under `unknown`; corrections are welcome.

```bash
pip install -e .[dev]
copticocr-legacy convert --font "CS Avva Shenouda" "`vnou] `nte peniwt"
copticocr-legacy convert --font abraam --reverse "ⲫ̀ⲛⲟⲩϯ"
copticocr-legacy pdf "lessons.pdf" -o lessons.txt
```

`tools/glyph_chart.py` renders every glyph of a font into a labelled chart, for
building or reviewing a table.

## Synthetic training lines

The Coptic recognizer is trained mostly on generated line images: real Bohairic
text rendered with each legacy and Unicode font, then degraded to look like an
old scan (skew, blur, faded or bleeding ink, paper texture, noise, JPEG,
bilevel scans). Labels are always Unicode.

```bash
pip install -e .[dev]
python tools/build_corpus.py --lessons "resources/Coptic lessons.pdf"
copticocr-synth --corpus data/corpus/bohairic_ot.txt data/corpus/lessons.txt \
    --fonts fonts data/fonts_unicode --count 100000 --out data/synth/v1
```

Unicode fonts go in `data/fonts_unicode/` (e.g. [Noto Sans Coptic](https://fonts.google.com/noto/specimen/Noto+Sans+Coptic), OFL).

### Text sources

- Bohairic Old and New Testament from [Coptic SCRIPTORIUM](https://github.com/CopticScriptorium/corpora)
  (CC-BY-SA 4.0; text from Marcion / Hany Takla). The Old Testament, including the
  Psalms, keeps church orthography with jinkim.

## Fonts and books

Legacy fonts and scanned books are copyrighted and are **not** part of this
repository. Put them in `fonts/` and `resources/` locally (both are git-ignored).

## License

Copyright © 2026 Mishel Makram.

This program is free software: you can redistribute it and/or modify it under the
terms of the [GNU Affero General Public License](LICENSE), version 3 or (at your
option) any later version. See [NOTICE](NOTICE) for the third-party parts.
