# Coptic OCR

Open-source OCR for Coptic (Bohairic) liturgical books on Windows: scanned
books in, searchable and re-typeset PDFs out. Pages mixing Coptic and Arabic
columns are supported, as are the legacy ANSI Coptic fonts (CS fonts,
Athanasius, Abraam) used by most church publications.

> برنامج مفتوح المصدر للتعرّف الضوئي على الكتب الكنسية القبطية (بحيري + عربي)،
> بيحوّل الكتب الممسوحة ضوئياً لـ PDF حديث قابل للبحث، وبيدعم خطوط الـ ANSI القديمة.

**Status:** early development. Done so far: the legacy font ↔ Unicode converter
and the synthetic training-line generator.

## Planned pipeline

1. **Ingest:** PDF/images; typed PDFs skip OCR and go through the legacy font converter.
2. **Layout model:** columns, blocks, lines and their script (Coptic / Arabic / mixed).
3. **Coptic recognizer:** line-level model trained mostly on synthetic data.
4. **Arabic recognizer**
5. **Post-processing:** jinkim/overline normalisation, hyphen joining, tatweel removal.
6. **Output:** searchable PDF, re-typeset PDF, Word, plain text.

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
