"""Low-level PDF layout extraction: characters, lines and graphics with positions."""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

import pymupdf

HEADER_LIMIT_Y = 68.0  # anything ending above this line is the running header
FOOTER_LIMIT_Y = 775.0  # anything starting below this line is the running footer
FURNITURE_PAGE_SHARE = 0.5  # a graphic repeated on >= half the pages is a watermark or rule
THIN_PT = 1.6  # max thickness of a border, rule or fraction bar

MATH_FONT_RE = re.compile(r"(?i)cambria\s?math|^cm(mi|sy|ex|r)\d|^msbm|^msam|^symbol")
MONO_FONT_RE = re.compile(r"(?i)courier|consolas|mono|^cmtt|nimbusmon|menlo|inconsolata")
BIG_DELIMITER_FONT_RE = re.compile(r"(?i)^cmex")
INVISIBLE_CHARS = {"⁡", "⁢", "⁣", "⁤", "​", "﻿"}
# Symbol-font glyphs exported as private-use code points, each confirmed against a crop.
SYMBOL_FONT_GLYPHS = {
    ("wingdings", ""): "→",  # functional-dependency arrows in 2026 Q17
}


@dataclass(frozen=True)
class Char:
    """One glyph with its box, baseline and font."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    baseline: float
    size: float
    font: str

    @property
    def is_math(self) -> bool:
        """True when the glyph is set in a math font."""
        return bool(MATH_FONT_RE.search(self.font))

    @property
    def is_mono(self) -> bool:
        """True when the glyph is set in a monospace (code) font."""
        return bool(MONO_FONT_RE.search(self.font))

    @property
    def is_big_delimiter(self) -> bool:
        """True for extensible brackets used by matrices, vectors and cases."""
        code = ord(self.text)
        return bool(BIG_DELIMITER_FONT_RE.search(self.font)) or 0x239B <= code <= 0x23B3

    @property
    def is_blank(self) -> bool:
        """True for whitespace glyphs."""
        return self.text.isspace()


@dataclass
class Piece:
    """A run of characters from one PDF line, tagged with its role in the paper."""

    page: int
    chars: list[Char]
    kind: str = "content"  # content | anchor | label | heading
    value: str = ""  # question number for anchors, option letter for labels

    @property
    def x0(self) -> float:
        """Left edge of the visible glyphs."""
        return min(c.x0 for c in self.visible)

    @property
    def x1(self) -> float:
        """Right edge of the visible glyphs."""
        return max(c.x1 for c in self.visible)

    @property
    def y0(self) -> float:
        """Top edge of the visible glyphs."""
        return min(c.y0 for c in self.visible)

    @property
    def y1(self) -> float:
        """Bottom edge of the visible glyphs."""
        return max(c.y1 for c in self.visible)

    @property
    def visible(self) -> list[Char]:
        """Glyphs that are not whitespace."""
        return [c for c in self.chars if not c.is_blank] or self.chars

    @property
    def text(self) -> str:
        """Raw text of the piece."""
        return "".join(c.text for c in self.chars)


@dataclass(frozen=True)
class Graphic:
    """An embedded image or a vector path on a page."""

    page: int
    kind: str  # image | vector
    x0: float
    y0: float
    x1: float
    y1: float
    thin: bool  # axis-aligned rule: border, table line, fraction bar
    curved: bool
    furniture: bool  # watermark, logo, header/footer rule

    @property
    def width(self) -> float:
        """Horizontal extent."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Vertical extent."""
        return self.y1 - self.y0

    @property
    def is_vertical_rule(self) -> bool:
        """Thin rule taller than it is wide."""
        return self.thin and self.height > self.width

    @property
    def is_horizontal_rule(self) -> bool:
        """Thin rule wider than it is tall."""
        return self.thin and self.width >= self.height


def clean_char(text: str) -> str:
    """Map math-italic letters and ligatures to plain text; drop invisible operators."""
    if text in INVISIBLE_CHARS:
        return ""
    if text == " ":
        return " "
    if text == "ℎ":  # Planck constant: Word's glyph for a math-italic h
        return "h"
    code = ord(text) if len(text) == 1 else 0
    if 0x1D400 <= code <= 0x1D7FF or 0xFB00 <= code <= 0xFB06:
        return unicodedata.normalize("NFKC", text)
    return text


def page_lines(page: pymupdf.Page) -> list[list[Char]]:
    """Return the text lines of a page as lists of positioned characters."""
    lines: list[list[Char]] = []
    raw = page.get_text("rawdict")
    for block in raw["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            chars = []
            for span in line["spans"]:
                for glyph in span["chars"]:
                    symbol = SYMBOL_FONT_GLYPHS.get((span["font"].lower(), glyph["c"]))
                    text = symbol or clean_char(glyph["c"])
                    x0, y0, x1, y1 = glyph["bbox"]
                    # Keep one Char per output character (ligatures expand), so string
                    # offsets of a line's text map 1:1 onto its Char list.
                    step = (x1 - x0) / max(len(text), 1)
                    for offset, letter in enumerate(text):
                        left = x0 + offset * step
                        chars.append(
                            Char(letter, left, y0, left + step, y1, glyph["origin"][1], span["size"], span["font"])
                        )
            if any(not c.is_blank for c in chars):
                lines.append(chars)
    return lines


def in_margin_zone(y0: float, y1: float) -> bool:
    """True when a box lies in the running header or footer."""
    return y1 <= HEADER_LIMIT_Y or y0 >= FOOTER_LIMIT_Y


def document_graphics(doc: pymupdf.Document) -> list[Graphic]:
    """Collect images and vector paths of every page, marking page furniture."""
    raw: list[tuple[int, str, tuple[float, float, float, float], bool, bool, tuple]] = []
    for page_index, page in enumerate(doc):
        for info in page.get_image_info():
            box = tuple(info["bbox"])
            # Watermarks are often re-embedded on every page under a new xref, so the
            # signature uses placement and pixel size instead of the xref.
            signature = ("img", info["width"], info["height"], _round_box(box))
            raw.append((page_index, "image", box, False, False, signature))
        for path in page.get_drawings():
            rect = path["rect"]
            box = (rect.x0, rect.y0, rect.x1, rect.y1)
            kinds = {item[0] for item in path["items"]}
            curved = "c" in kinds or ("qu" in kinds and not _is_axis_aligned(path))
            thin = min(rect.width, rect.height) <= THIN_PT and _is_axis_aligned(path)
            fill = tuple(round(v, 2) for v in (path.get("fill") or ()))
            raw.append((page_index, "vector", box, thin, curved, ("vec", fill, _round_box(box))))

    pages_by_signature: dict[tuple, set[int]] = defaultdict(set)
    for page_index, _, _, _, _, signature in raw:
        pages_by_signature[signature].add(page_index)
    min_pages = max(3, int(doc.page_count * FURNITURE_PAGE_SHARE))

    graphics = []
    for page_index, kind, box, thin, curved, signature in raw:
        furniture = len(pages_by_signature[signature]) >= min_pages or in_margin_zone(box[1], box[3])
        graphics.append(Graphic(page_index, kind, *box, thin=thin, curved=curved, furniture=furniture))
    return graphics


def _round_box(box: tuple[float, ...]) -> tuple[int, ...]:
    """Round a box to whole points so repeated elements share a signature."""
    return tuple(round(v) for v in box)


def _is_axis_aligned(path: dict) -> bool:
    """True when a vector path only has horizontal/vertical lines and rectangles."""
    for item in path["items"]:
        op = item[0]
        if op == "re":
            continue
        if op == "l":
            start, end = item[1], item[2]
            if abs(start.x - end.x) > 0.5 and abs(start.y - end.y) > 0.5:
                return False
            continue
        if op == "qu":
            quad = item[1]
            if not quad.is_rectangular:
                return False
            continue
        return False
    return True
