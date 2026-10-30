# Coptic OCR

Open-source OCR for Coptic (Bohairic) liturgical books on Windows: scanned
books in, searchable and re-typeset PDFs out. Pages mixing Coptic and Arabic
columns are supported, as are the legacy ANSI Coptic fonts (CS fonts,
Athanasius, Abraam) used by most church publications.

> برنامج مفتوح المصدر للتعرّف الضوئي على الكتب الكنسية القبطية (بحيري + عربي)،
> بيحوّل الكتب الممسوحة ضوئياً لـ PDF حديث قابل للبحث، وبيدعم خطوط الـ ANSI القديمة.

**Status:** early development. Done so far: the legacy font ↔ Unicode converter.

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

## Fonts and books

Legacy fonts and scanned books are copyrighted and are **not** part of this
repository. Put them in `fonts/` and `resources/` locally (both are git-ignored).

## License

[AGPL-3.0-or-later](LICENSE)
