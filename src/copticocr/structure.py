"""What a bilingual church book page is made of: titles, and Coptic beside Arabic.

Lines printed side by side (a Coptic line and the Arabic line level with it) form
a row. Rows group into stanzas: a stanza starts where the Coptic is indented, as
in most psalmodies, and its Coptic and Arabic are kept together, so a table can
hold one stanza per row and the text can flow inside its cell. A line running
across both columns before the text, or with no Coptic beside it, is a title.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .layout.projection import Box
from .pipeline import PageResult, TextLine

INDENT = 0.6  # of a line's height: how far in a stanza's first line starts


@dataclass
class Row:
    coptic: list[TextLine] = field(default_factory=list)
    arabic: list[TextLine] = field(default_factory=list)
    title: list[TextLine] = field(default_factory=list)  # lines of a title across the page

    @property
    def is_title(self) -> bool:
        return bool(self.title)

    @property
    def coptic_text(self) -> str:
        return join_lines(line.text for line in self.coptic)

    @property
    def box(self) -> Box:
        lines = self.title or self.coptic + self.arabic
        return Box(min(l.box.x0 for l in lines), min(l.box.y0 for l in lines),
                   max(l.box.x1 for l in lines), max(l.box.y1 for l in lines))


def join_lines(texts) -> str:
    """Lines as running text: a word broken with a hyphen at a line end is joined again.

    A colon or full stop printed after a space stays with its word (no-break space),
    so a reflowed line never starts with one.
    """
    out = ""
    for text in texts:
        text = text.strip()
        if not text:
            continue
        if out.endswith("-"):
            out = out[:-1] + text
        else:
            out = f"{out} {text}" if out else text
    return out.replace(" :", " :").replace(" .", " .")


def _is_coptic(line: TextLine) -> bool:
    return line.script == "coptic" and bool(line.text.strip())


def _overlap(a: Box, b: Box) -> float:
    """Vertical overlap of two lines, as a share of the shorter one."""
    shared = min(a.y1, b.y1) - max(a.y0, b.y0)
    return max(0.0, shared) / max(1, min(a.height, b.height))


def line_rows(result: PageResult) -> list[Row]:
    """One row per printed line: each line with the lines level with it in the other columns."""
    groups: list[list[TextLine]] = []
    for line in sorted(result.lines, key=lambda l: (l.box.y0 + l.box.y1) / 2):
        for group in reversed(groups[-3:]):
            if all(other.column != line.column for other in group) and \
                    max(_overlap(other.box, line.box) for other in group) >= 0.5:
                group.append(line)
                break
        else:
            groups.append([line])

    rows: list[Row] = []
    seen_coptic = False
    for group in groups:
        group.sort(key=lambda l: l.column)
        coptic = [l for l in group if _is_coptic(l)]
        if coptic:
            seen_coptic = True
            rows.append(Row(coptic=coptic, arabic=[l for l in group if not _is_coptic(l)]))
        elif not seen_coptic or len({l.column for l in group}) > 1:
            rows.append(Row(title=group))  # above the text, or across both columns
        else:
            rows.append(Row(arabic=group))
    return rows


def stanza_rows(result: PageResult) -> list[Row]:
    """Rows joined into stanzas; one row per line where the page shows no stanzas."""
    rows = line_rows(result)
    coptic = [line for row in rows for line in row.coptic]
    if len(coptic) < 4:
        return rows
    edge = float(np.percentile([l.box.x0 for l in coptic], 25))
    height = float(np.median([l.box.height for l in coptic]))

    def starts_stanza(row: Row) -> bool:
        return bool(row.coptic) and row.coptic[0].box.x0 - edge >= INDENT * height

    if sum(starts_stanza(row) for row in rows) < 2:
        return rows  # no indented stanza starts: keep the page's lines
    stanzas: list[Row] = []
    for row in rows:
        previous = stanzas[-1] if stanzas else None
        if row.is_title or previous is None or previous.is_title or starts_stanza(row):
            stanzas.append(Row(coptic=list(row.coptic), arabic=list(row.arabic), title=list(row.title)))
        else:
            previous.coptic += row.coptic
            previous.arabic += row.arabic
    return stanzas
