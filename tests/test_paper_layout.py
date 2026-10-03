"""Tests for line splitting, ownership and text rendering on synthetic glyphs."""

from gate_atlas.layout import Char, Piece
from gate_atlas.paper import owner_index, render_line, split_line, split_options

BODY_FONT = "TimesNewRomanPSMT"
MATH_FONT = "CambriaMath"


def glyphs(text: str, x: float, baseline: float, size: float = 12.0, font: str = BODY_FONT) -> list[Char]:
    """Lay out text left to right with a fixed advance."""
    advance = size * 0.5
    return [
        Char(letter, x + i * advance, baseline - size * 0.8, x + (i + 1) * advance, baseline + size * 0.2, baseline, size, font)
        for i, letter in enumerate(text)
    ]


def test_anchor_and_inline_stem_are_split() -> None:
    """'Q.3 A 4 x 4 image' gives an anchor piece and a content piece."""
    pieces = split_line(0, glyphs("Q.3 A 4 x 4 image", 78, 100))
    assert [(p.kind, p.value) for p in pieces] == [("anchor", "3"), ("content", "")]


def test_label_and_option_text_on_one_line() -> None:
    """'(A) 3' gives a label piece and a content piece."""
    pieces = split_line(0, glyphs("(A) 3", 78, 100))
    assert [(p.kind, p.value) for p in pieces] == [("label", "A"), ("content", "")]


def test_bare_letter_in_margin_is_a_label() -> None:
    """A lone 'B' in the left margin labels an option; in the content column it does not."""
    assert split_line(0, glyphs("B", 78, 100))[0].kind == "label"
    assert split_line(0, glyphs("B", 300, 100))[0].kind == "content"


def test_owner_is_last_anchor_starting_above_piece_bottom() -> None:
    """A tall first stem line that starts above its anchor still belongs to it."""
    anchors = [Piece(0, glyphs("Q.1", 78, 100), "anchor", "1"), Piece(0, glyphs("Q.2", 78, 300), "anchor", "2")]
    tall_line = Piece(0, glyphs("x", 120, 300, size=30))  # top above Q.2's top, bottom below it
    above_q2 = Piece(0, glyphs("old", 120, 250))
    assert owner_index(tall_line, anchors) == 1
    assert owner_index(above_q2, anchors) == 0


def test_options_follow_their_labels() -> None:
    """Content goes to the nearest label row above it; text above all labels is the stem."""
    pieces = [
        Piece(0, glyphs("stem", 120, 100)),
        Piece(0, glyphs("(A)", 78, 140), "label", "A"),
        Piece(0, glyphs("alpha", 120, 140)),
        Piece(0, glyphs("(B)", 78, 180), "label", "B"),
        Piece(0, glyphs("beta", 120, 180)),
        Piece(0, glyphs("beta continued", 120, 194)),
    ]
    stem, options, letters = split_options(pieces)
    assert [p.text for p in stem] == ["stem"]
    assert letters == ["A", "B"]
    assert [p.text for p in options["B"]] == ["beta", "beta continued"]


def test_superscripts_and_subscripts_are_marked() -> None:
    """Smaller raised/lowered glyphs become ^{..} and _{..}."""
    chars = (
        glyphs("x", 100, 100, font=MATH_FONT)
        + glyphs("2", 106, 96, size=8, font=MATH_FONT)
        + glyphs(" + y", 112, 100, font=MATH_FONT)
        + glyphs("ij", 136, 103, size=8, font=MATH_FONT)
    )
    assert render_line([Piece(0, chars)]) == "x^2 + y_{ij}"


def test_negation_overlay_composes_with_following_relation() -> None:
    """TeX's \\not slash before '=' becomes '≠'."""
    chars = glyphs("x ", 100, 100) + [Char("̸", 112, 90, 112, 102, 100, 12, "CMSY10")] + glyphs("= y", 112, 100)
    assert render_line([Piece(0, chars)]) == "x ≠ y"
