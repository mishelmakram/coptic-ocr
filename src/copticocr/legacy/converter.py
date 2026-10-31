"""Convert between legacy (ANSI) Coptic fonts and Unicode Coptic.

Legacy Coptic fonts draw Coptic letters on Latin codepoints, so the stored
text is meaningless without the font. Each font family ("layout") has its own
table in ``maps/*.json``.

Diacritics are zero-width glyphs. Some fonts place them over the *next*
letter (prefix marks, e.g. the jinkim ````` typed before the letter) and
some over the *previous* letter (postfix marks). Unicode always stores the
combining mark after its base letter, so conversion reorders them.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import cache
from importlib import resources

REPLACEMENT = "�"


@dataclass(frozen=True)
class Layout:
    name: str
    description: str
    fonts: tuple[str, ...]
    chars: dict[str, str]
    prefix_marks: dict[str, str]
    postfix_marks: dict[str, str]
    unknown: dict[str, str]
    passthrough: str
    _reverse_chars: dict[str, str] = field(init=False, repr=False)
    _reverse_marks: dict[str, tuple[str, bool]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        reverse_chars: dict[str, str] = {}
        for key, value in self.chars.items():
            if len(value) == 1:
                reverse_chars.setdefault(value, key)
        for ch in self.passthrough:
            reverse_chars.setdefault(ch, ch)

        # mark -> (legacy key, is_prefix); the first listed key wins.
        reverse_marks: dict[str, tuple[str, bool]] = {}
        for key, mark in self.prefix_marks.items():
            reverse_marks.setdefault(mark, (key, True))
        for key, mark in self.postfix_marks.items():
            reverse_marks.setdefault(mark, (key, False))

        object.__setattr__(self, "_reverse_chars", reverse_chars)
        object.__setattr__(self, "_reverse_marks", reverse_marks)

    def to_unicode(self, text: str) -> str:
        out: list[str] = []
        pending: list[str] = []  # prefix marks waiting for their base letter
        for ch in text:
            if ch in self.prefix_marks:
                pending.append(self.prefix_marks[ch])
                continue
            if ch in self.postfix_marks:
                out.append(self.postfix_marks[ch])
                continue

            if ch in self.chars:
                piece = self.chars[ch]
            elif ch in self.passthrough or ch.isspace():
                piece = ch
            else:
                piece = REPLACEMENT

            if pending and piece and not piece.isspace():  # "" is an invisible glyph
                piece = piece[0] + "".join(pending) + piece[1:]
                pending.clear()
            out.append(piece)
        out.extend(pending)
        return "".join(out)

    def from_unicode(self, text: str, errors: str = "strict") -> str:
        out: list[str] = []
        for base, marks in _clusters(text):
            if base in self._reverse_chars:
                key = self._reverse_chars[base]
            elif base.isspace():
                key = base
            elif errors == "replace":
                key = "?"
            else:
                raise ValueError(f"{base!r} (U+{ord(base):04X}) has no glyph in layout {self.name!r}")

            before, after = [], []
            for mark in marks:
                if mark not in self._reverse_marks:
                    if errors == "replace":
                        continue
                    raise ValueError(f"mark U+{ord(mark):04X} has no glyph in layout {self.name!r}")
                mark_key, is_prefix = self._reverse_marks[mark]
                (before if is_prefix else after).append(mark_key)
            out.append("".join(before) + key + "".join(after))
        return "".join(out)


def _clusters(text: str):
    """Yield (base character, [combining marks]) pairs."""
    base, marks = None, []
    for ch in text:
        if unicodedata.combining(ch) and base is not None:
            marks.append(ch)
            continue
        if base is not None:
            yield base, marks
        base, marks = ch, []
    if base is not None:
        yield base, marks


def _normalize_font_name(name: str) -> str:
    name = name.split("+", 1)[-1]  # drop PDF subset prefix, e.g. "ABCDEF+"
    return re.sub(r"[^a-z0-9]", "", name.lower())


@cache
def layouts() -> dict[str, Layout]:
    result = {}
    for entry in resources.files(__package__).joinpath("maps").iterdir():
        if not entry.name.endswith(".json"):
            continue
        data = json.loads(entry.read_text(encoding="utf-8"))
        data["fonts"] = tuple(data["fonts"])
        data.setdefault("postfix_marks", {})
        data.setdefault("unknown", {})
        result[data["name"]] = Layout(**data)
    return result


def layout_for_font(font_name: str) -> Layout | None:
    """Find the layout for a font family name, as written in Word or a PDF."""
    wanted = _normalize_font_name(font_name)
    for layout in layouts().values():
        for font in layout.fonts:
            if wanted.startswith(_normalize_font_name(font)):
                return layout
    return None


def get_layout(name_or_font: str) -> Layout:
    if name_or_font in layouts():
        return layouts()[name_or_font]
    layout = layout_for_font(name_or_font)
    if layout is None:
        raise KeyError(f"unknown Coptic layout or font: {name_or_font!r}")
    return layout
