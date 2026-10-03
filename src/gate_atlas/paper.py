"""Segment a GATE master question paper PDF into per-question records.

The papers are laid out as a left margin holding "Q.N" and "(A)".."(D)" labels and a
content column holding the stem and option text. A piece of text belongs to the last
question number whose top edge lies above the bottom edge of that piece; the same rule
assigns option text to option labels. Every question is also rendered to a PNG crop,
which is the visual ground truth whenever the extracted text is lossy.
"""

import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

import pymupdf

from gate_atlas.layout import (
    FOOTER_LIMIT_Y,
    HEADER_LIMIT_Y,
    Char,
    Graphic,
    Piece,
    document_graphics,
    in_margin_zone,
    page_lines,
)

log = logging.getLogger(__name__)

ANCHOR_MAX_X = 100.0  # question numbers sit in the left margin
OVERLAP_EPS = 1.0
LABEL_ROW_TOLERANCE = 3.0  # labels whose tops differ by less than this share a row
LABEL_X_TOLERANCE = 2.0
FRAME_COLUMN_MIN_PAGES = 3  # vertical rules at one x on this many pages = question frame, not a table
FRACTION_REACH = 12.0  # how far above/below a bar to look for numerator/denominator glyphs
FRACTION_MAX_WIDTH = 250.0
STACK_GAP = 6.0
SHORT_LINE_SHARE = 0.45
MATH_DOMINANT_SHARE = 0.6
SCRIPT_SIZE_RATIO = 0.85
SCRIPT_SHIFT_PT = 1.5
SPACE_GAP_RATIO = 0.22
VISUAL_LINE_TOLERANCE = 0.45
MIN_TABLE_RULE_HEIGHT = 8.0
MIN_FIGURE_PATHS = 3
MIN_FIGURE_AREA = 400.0
LARGE_OPERATORS = set("√∑∏∫∮⋃⋂")
STACK_OVERLAP_SHARE = 0.4
STACK_MIN_GAP, STACK_MAX_GAP = 0.75, 1.6  # baseline gap between stacked rows, in middle-glyph sizes
STACK_MIDDLE_MARGIN = 0.25
STACK_MIDDLE_REACH = 40.0
DEEP_SCRIPT_SHIFT = 0.6  # limits sit lower/higher than ordinary sub/superscripts (~0.3 of the size)
MATRIX_ROW_REACH = 1.6  # outer matrix rows lie within this many font sizes of the bracket line
OPENING_BRACKETS = set("[({|⌈⌊⟨‖")
BRACKET_GAP = 25.0
BRACKET_OVERLAP = 3.0  # glyph boxes of a bracket and the first entry may overlap slightly
NEGATION_OVERLAY = "̸"
MIN_UNDERLINE_WIDTH = 5.0
UNDERLINE_REACH = 4.0
CROP_X0, CROP_X1 = 52.0, 545.0
CROP_PAD = 4.0
CROP_GAP = 6.0
CROP_ZOOM = 2.0

ANCHOR_RE = re.compile(r"^\s*(Q\.\s?(\d{1,2}))(?=\s|$)")
LABEL_RE = re.compile(r"(?<!\S)\(([A-D])\)(?!\S)")
BARE_LABEL_RE = re.compile(r"^\s*([A-D])\s*$")  # a lone "A" in the margin column also labels an option
HEADING_RE = re.compile(
    r"(?i)^\s*(general aptitude(\s*\(ga\))?|q\.\s?\d+\s*[–-]+\s*q\.\s?\d+\s+carry\b.*"
    r"|end of (the )?question paper.*)\s*$"
)
MARK_HEADER_RE = re.compile(r"(?i)q\.\s?(\d+)\s*[–-]+\s*q\.\s?(\d+)\s+carry\s+(one|two)\s+marks?")
FURNITURE_TEXT_RE = re.compile(r"(?i)^\s*(page \d+ of \d+|organi[sz]ing institute\b.*)\s*$")
UNMAPPED_RE = re.compile(r"[-�]")
WORD_TO_MARKS = {"one": 1, "two": 2}


@dataclass
class ParsedQuestion:
    """Everything extracted for one question of a paper."""

    number: int
    stem: str
    options: dict[str, str]
    label_letters: list[str]
    regions: list[tuple[int, tuple[float, float, float, float]]]
    features: dict[str, bool | int]
    has_unmapped_glyphs: bool = False


@dataclass
class ParsedPaper:
    """Questions of one paper plus paper-level facts used for validation."""

    questions: list[ParsedQuestion]
    header_marks: dict[int, int]
    anchor_numbers: list[int]
    page_count: int
    dropped_pieces: list[str] = field(default_factory=list)


def parse_paper(pdf_path: Path, crops_dir: Path | None = None, id_prefix: str = "") -> ParsedPaper:
    """Parse a master question paper and optionally render one PNG crop per question."""
    doc = pymupdf.open(pdf_path)
    pieces: list[Piece] = []
    headings: list[str] = []
    for page_index, page in enumerate(doc):
        for chars in page_lines(page):
            line = Piece(page_index, chars)
            if in_margin_zone(line.y0, line.y1) or FURNITURE_TEXT_RE.match(line.text):
                continue
            if HEADING_RE.match(line.text):
                headings.append(line.text.strip())
                continue
            pieces.extend(split_line(page_index, chars))

    anchors = sorted((p for p in pieces if p.kind == "anchor"), key=lambda p: (p.page, p.y0))
    owned: list[list[Piece]] = [[] for _ in anchors]
    dropped = []
    for piece in pieces:
        if piece.kind == "anchor":
            continue
        index = owner_index(piece, anchors)
        if index is None:
            dropped.append(piece.text.strip())
        else:
            owned[index].append(piece)

    graphics = document_graphics(doc)
    frame_columns = find_frame_columns(graphics)
    bands = question_bands(anchors, owned, doc.page_count)

    questions = []
    for index, anchor in enumerate(anchors):
        number = int(anchor.value)
        own_graphics = [
            g for g in graphics
            if not g.furniture and _graphic_in_bands(g, bands[index])
        ]
        stem_pieces, option_pieces, letters = split_options(owned[index])
        regions = crop_regions(anchor, owned[index], own_graphics, bands[index])
        text_pieces = stem_pieces + [p for group in option_pieces.values() for p in group]
        all_text = " ".join(p.text for p in text_pieces)
        question = ParsedQuestion(
            number=number,
            stem=render_text(stem_pieces),
            options={letter: render_text(group) for letter, group in option_pieces.items()},
            label_letters=letters,
            regions=regions,
            features=question_features(text_pieces, own_graphics, frame_columns),
            has_unmapped_glyphs=bool(UNMAPPED_RE.search(all_text)),
        )
        if crops_dir is not None and regions:
            render_crop(doc, regions, crops_dir / f"{id_prefix}Q{number:02d}.png")
        questions.append(question)

    return ParsedPaper(
        questions=questions,
        header_marks=parse_mark_headers(headings),
        anchor_numbers=[int(a.value) for a in anchors],
        page_count=doc.page_count,
        dropped_pieces=dropped,
    )


def split_line(page_index: int, chars: list[Char]) -> list[Piece]:
    """Split one PDF line into anchor, option-label and content pieces."""
    text = "".join(c.text for c in chars)
    cuts: list[tuple[int, int, str, str]] = []
    first_visible = next(c for c in chars if not c.is_blank)
    anchor = ANCHOR_RE.match(text)
    if anchor and first_visible.x0 < ANCHOR_MAX_X:
        cuts.append((anchor.start(1), anchor.end(1), "anchor", anchor.group(2)))
    labels = list(LABEL_RE.finditer(text))
    starts_with_label = bool(labels) and not text[: labels[0].start()].strip()
    if labels and (starts_with_label or len(labels) >= 2):
        cuts.extend((m.start(), m.end(), "label", m.group(1)) for m in labels)
    bare = BARE_LABEL_RE.match(text)
    if bare and first_visible.x0 < ANCHOR_MAX_X:
        cuts.append((bare.start(1), bare.end(1), "label", bare.group(1)))

    pieces = []
    position = 0
    for start, end, kind, value in sorted(cuts):
        if text[position:start].strip():
            pieces.append(Piece(page_index, chars[position:start]))
        pieces.append(Piece(page_index, chars[start:end], kind, value))
        position = end
    if text[position:].strip():
        pieces.append(Piece(page_index, chars[position:]))
    return pieces


def starts_before(page: int, top: float, piece: Piece) -> bool:
    """True when a marker at (page, top) begins above the bottom of a piece."""
    return page < piece.page or (page == piece.page and top < piece.y1 - OVERLAP_EPS)


def owner_index(piece: Piece, anchors: list[Piece]) -> int | None:
    """Index of the question anchor that owns a piece, or None before the first one."""
    owner = None
    for index, anchor in enumerate(anchors):
        if not starts_before(anchor.page, anchor.y0, piece):
            break
        owner = index
    return owner


def split_options(pieces: list[Piece]) -> tuple[list[Piece], dict[str, list[Piece]], list[str]]:
    """Split a question's pieces into stem pieces and per-option pieces."""
    labels = sorted((p for p in pieces if p.kind == "label"), key=lambda p: (p.page, p.y0, p.x0))
    rows: list[list[Piece]] = []
    for label in labels:
        last = rows[-1][0] if rows else None
        if last and last.page == label.page and abs(last.y0 - label.y0) <= LABEL_ROW_TOLERANCE:
            rows[-1].append(label)
        else:
            rows.append([label])

    stem: list[Piece] = []
    by_label: dict[int, list[Piece]] = {id(label): [] for label in labels}
    for piece in pieces:
        if piece.kind != "content":
            continue
        row = None
        for candidate in rows:
            if not starts_before(candidate[0].page, min(l.y0 for l in candidate), piece):
                break
            row = candidate
        if row is None:
            stem.append(piece)
            continue
        left_of_piece = [l for l in row if l.x0 <= piece.x0 + LABEL_X_TOLERANCE]
        label = max(left_of_piece, key=lambda l: l.x0) if left_of_piece else min(row, key=lambda l: l.x0)
        by_label[id(label)].append(piece)

    options: dict[str, list[Piece]] = {}
    for label in labels:
        options.setdefault(label.value, []).extend(by_label[id(label)])
    return stem, options, [label.value for label in labels]


def render_text(pieces: list[Piece]) -> str:
    """Rebuild readable text from pieces, marking super/subscripts as ^{..} and _{..}.

    When the pieces contain code (monospace glyphs), each line keeps its indentation
    relative to the leftmost line, because indentation carries meaning in Python.
    """
    lines = [line for line in group_visual_lines(pieces) if render_line(line)]
    mono = [c for p in pieces for c in p.chars if c.is_mono and not c.is_blank]
    if not mono:
        return "\n".join(render_line(line) for line in lines)
    unit = median(c.x1 - c.x0 for c in mono)
    left = min(min(p.x0 for p in line) for line in lines)
    rendered = []
    for line in lines:
        indent = round((min(p.x0 for p in line) - left) / unit)
        rendered.append(" " * max(indent, 0) + render_line(line))
    return "\n".join(rendered)


def group_visual_lines(pieces: list[Piece]) -> list[list[Piece]]:
    """Group pieces whose vertical centres are close into visual lines."""
    ordered = sorted(pieces, key=lambda p: (p.page, (p.y0 + p.y1) / 2, p.x0))
    lines: list[list[Piece]] = []
    for piece in ordered:
        centre = (piece.y0 + piece.y1) / 2
        if lines:
            head = lines[-1][0]
            head_centre = (head.y0 + head.y1) / 2
            tolerance = VISUAL_LINE_TOLERANCE * max(head.y1 - head.y0, piece.y1 - piece.y0)
            if head.page == piece.page and abs(centre - head_centre) <= tolerance:
                lines[-1].append(piece)
                continue
        lines.append([piece])
    return lines


def line_metrics(visible: list[Char]) -> tuple[float, float]:
    """Base font size and baseline of a visual line.

    The base size is the largest size used by at least two glyphs: scripts are smaller,
    and a lone big operator (a large sum sign) should not set the base.
    """
    size_counts = Counter(round(c.size * 2) / 2 for c in visible)
    repeated = [size for size, count in size_counts.items() if count >= 2]
    main_size = max(repeated) if repeated else max(size_counts)
    main_baseline = median(c.baseline for c in visible if round(c.size * 2) / 2 == main_size)
    return main_size, main_baseline


def render_line(pieces: list[Piece]) -> str:
    """Render one visual line, inserting spaces at gaps and marking scripts."""
    chars = sorted((c for p in pieces for c in p.chars), key=lambda c: c.x0)
    visible = [c for c in chars if not c.is_blank]
    if not visible:
        return ""
    main_size, main_baseline = line_metrics(visible)
    marks_after = _attach_combining_marks(visible)

    out: list[str] = []
    state = "base"
    previous: Char | None = None
    for char in chars:
        if _is_combining(char):
            continue
        if char.is_blank:
            if out and out[-1] != " ":
                out.append(" ")
            previous = None
            continue
        script = _script_of(char, main_size, main_baseline)
        gap = previous is not None and char.x0 - previous.x1 > SPACE_GAP_RATIO * min(char.size, previous.size)
        # Word often drops the space between a math zone and the next word ("h_1and").
        if state != "base" and script == "base" and previous is not None and previous.is_math:
            gap = gap or (char.text.isalpha() and not char.is_math)
        if script != state:
            if state != "base":
                _close_script(out)
                if gap and script == "base" and out[-1] != " ":
                    out.append(" ")
            if script != "base":
                out.append("^{" if script == "sup" else "_{")
            state = script
        elif gap and out and out[-1] != " ":
            out.append(" ")
        out.append(char.text + "".join(marks_after.get(id(char), [])))
        previous = char
    if state != "base":
        _close_script(out)
    text = "".join(out)
    text = re.sub(r"([\^_])\{(\w)\}", r"\1\2", text)  # n^{2} -> n^2
    text = unicodedata.normalize("NFC", text)  # "=" + overlay slash -> "≠", "T" + overline -> "T̄"
    return re.sub(r"[ \t]+", " ", text).strip()


def _is_combining(char: Char) -> bool:
    """True for combining marks (overlines, negation slashes, hats) drawn over a glyph."""
    return unicodedata.category(char.text) == "Mn"


def _attach_combining_marks(visible: list[Char]) -> dict[int, list[str]]:
    """Map each base glyph to the combining marks drawn over it.

    A zero-width mark sits at the pen position where it was emitted. Word emits a mark
    after its base letter (overline: T then U+0305); TeX's \\not emits the slash before
    the relation it negates (U+0338 then =). Reading order alone would attach the mark
    to the wrong letter ("T d̅enote").
    """
    bases = sorted((c for c in visible if not _is_combining(c)), key=lambda c: c.x0)
    attached: dict[int, list[str]] = {}
    for mark in (c for c in visible if _is_combining(c)):
        if mark.text == NEGATION_OVERLAY:
            following = [c for c in bases if c.x0 >= mark.x0 - OVERLAP_EPS]
            target = following[0] if following else None
        else:
            preceding = [c for c in bases if c.x1 <= mark.x0 + OVERLAP_EPS]
            target = max(preceding, key=lambda c: c.x1) if preceding else None
        if target is not None:
            attached.setdefault(id(target), []).append(mark.text)
    return attached


def _close_script(out: list[str]) -> None:
    """Close a ^{..}/_{..} group, moving a trailing space outside the braces."""
    trailing_space = bool(out) and out[-1] == " "
    if trailing_space:
        out.pop()
    out.append("}")
    if trailing_space:
        out.append(" ")


def _script_of(char: Char, main_size: float, main_baseline: float) -> str:
    """Classify a glyph as base text, superscript or subscript."""
    if char.size >= SCRIPT_SIZE_RATIO * main_size:
        return "base"
    if char.baseline < main_baseline - SCRIPT_SHIFT_PT:
        return "sup"
    if char.baseline > main_baseline + SCRIPT_SHIFT_PT:
        return "sub"
    return "base"


def find_frame_columns(graphics: list[Graphic]) -> set[int]:
    """x positions of vertical rules that frame questions on several pages."""
    pages_by_x: dict[int, set[int]] = {}
    for graphic in graphics:
        if graphic.kind == "vector" and graphic.is_vertical_rule:
            pages_by_x.setdefault(round(graphic.x0), set()).add(graphic.page)
    return {x for x, pages in pages_by_x.items() if len(pages) >= FRAME_COLUMN_MIN_PAGES}


def question_bands(anchors: list[Piece], owned: list[list[Piece]], page_count: int) -> list[list[tuple[int, float, float]]]:
    """Vertical bands (page, top, bottom) of the document flow owned by each question."""
    starts = []
    for anchor, pieces in zip(anchors, owned):
        same_page = [p.y0 for p in pieces if p.page == anchor.page]
        starts.append((anchor.page, min([anchor.y0, *same_page])))
    bands = []
    for index, (page, top) in enumerate(starts):
        if index + 1 < len(starts):
            end_page, end_top = starts[index + 1]
        else:
            end_page, end_top = page_count - 1, FOOTER_LIMIT_Y
        question_bands_list = []
        for current in range(page, end_page + 1):
            band_top = top if current == page else HEADER_LIMIT_Y
            band_bottom = end_top if current == end_page else FOOTER_LIMIT_Y
            if band_bottom > band_top:
                question_bands_list.append((current, band_top, band_bottom))
        bands.append(question_bands_list)
    return bands


def _graphic_in_bands(graphic: Graphic, bands: list[tuple[int, float, float]]) -> bool:
    """True when a graphic's centre falls inside one of a question's bands."""
    centre = (graphic.y0 + graphic.y1) / 2
    return any(page == graphic.page and top - OVERLAP_EPS <= centre < bottom for page, top, bottom in bands)


def crop_regions(
    anchor: Piece, pieces: list[Piece], graphics: list[Graphic], bands: list[tuple[int, float, float]]
) -> list[tuple[int, tuple[float, float, float, float]]]:
    """Tight per-page clip rectangles covering a question's text and graphics."""
    regions = []
    for page, top, bottom in bands:
        # Only text, images and drawings set the extent. Thin rules (question frames, empty
        # table rows below the options) would otherwise stretch crops down the page.
        boxes = [(p.y0, p.y1) for p in [anchor, *pieces] if p.page == page]
        boxes += [(g.y0, g.y1) for g in graphics if g.page == page and not g.thin]
        if not boxes:
            continue
        clip_top = max(top - CROP_PAD, min(b[0] for b in boxes) - CROP_PAD)
        clip_bottom = min(bottom, max(b[1] for b in boxes) + CROP_PAD)
        if clip_bottom - clip_top > 2:
            regions.append((page, (CROP_X0, clip_top, CROP_X1, clip_bottom)))
    return regions


def question_features(pieces: list[Piece], graphics: list[Graphic], frame_columns: set[int]) -> dict[str, bool | int]:
    """Detect math, figures, tables and stacked math inside one question."""
    chars = [c for p in pieces for c in p.chars if not c.is_blank]
    images = [g for g in graphics if g.kind == "image"]
    shapes = [g for g in graphics if g.kind == "vector" and not g.thin]
    curves = [g for g in shapes if g.curved]
    inner_verticals = [
        g for g in graphics
        if g.kind == "vector" and g.is_vertical_rule and g.height >= MIN_TABLE_RULE_HEIGHT
        and round(g.x0) not in frame_columns
    ]
    shape_area = sum(g.width * g.height for g in shapes)
    return {
        "has_math": any(c.is_math for c in chars),
        "has_code": any(c.is_mono for c in chars),
        "image_count": len(images),
        "vector_shape_count": len(shapes),
        "has_figure": bool(images) or bool(curves) or len(shapes) >= MIN_FIGURE_PATHS or shape_area >= MIN_FIGURE_AREA,
        "has_table": len(inner_verticals) >= 2,
        "fraction_bars": count_fraction_bars(chars, graphics),
        "stacked_math_lines": count_stacked_math_lines(pieces),
        "stacked_glyphs": count_stacked_glyphs(pieces),
        "matrix_rows": count_matrix_rows(pieces),
        "deep_scripts": count_deep_scripts(pieces),
        "display_math_glyphs": count_display_math_glyphs(chars),
        "underline_rules": count_underlines(chars, graphics),
    }


def count_display_math_glyphs(chars: list[Char]) -> int:
    """Count extensible brackets, roots and n-ary operators (sums, products, integrals).

    A root's extent is only drawn by its overline and an operator's limits sit above or
    below it, so linear text cannot say where either ends.
    """
    return sum(c.is_big_delimiter or c.text in LARGE_OPERATORS for c in chars)


def count_stacked_glyphs(pieces: list[Piece]) -> int:
    """Count glyph pairs stacked in rows around a glyph on a middle baseline.

    This is the shape of matrices, column vectors, binomial coefficients and case
    braces: two rows of math overlap horizontally and the surrounding line (a bracket,
    an equals sign) runs on a baseline between them. Ordinary consecutive text lines
    never have a full-size glyph sitting between their baselines.
    """
    by_page: dict[int, list[Char]] = {}
    for piece in pieces:
        by_page.setdefault(piece.page, []).extend(c for c in piece.chars if c.text.strip())
    hits = 0
    for glyphs in by_page.values():
        glyphs.sort(key=lambda c: c.x0)
        for index, first in enumerate(glyphs):
            for second in glyphs[index + 1:]:
                if second.x0 >= first.x1:
                    break
                narrow = min(first.x1 - first.x0, second.x1 - second.x0)
                overlap = min(first.x1, second.x1) - max(first.x0, second.x0)
                if narrow <= 0 or overlap < STACK_OVERLAP_SHARE * narrow:
                    continue
                top, bottom = sorted((first, second), key=lambda c: c.baseline)
                gap = bottom.baseline - top.baseline
                size = max(top.size, bottom.size)
                left = min(top.x0, bottom.x0) - STACK_MIDDLE_REACH
                right = max(top.x1, bottom.x1) + STACK_MIDDLE_REACH
                # The gap is measured against the middle glyph: a superscript stacked over a
                # subscript (x^T_i) sits closer together than two rows of a matrix or binomial.
                hits += any(
                    m.size >= SCRIPT_SIZE_RATIO * size
                    and STACK_MIN_GAP * m.size <= gap <= STACK_MAX_GAP * m.size
                    and top.baseline + STACK_MIDDLE_MARGIN * gap <= m.baseline <= bottom.baseline - STACK_MIDDLE_MARGIN * gap
                    and m.x1 >= left and m.x0 <= right
                    for m in glyphs
                )
    return hits


def count_matrix_rows(pieces: list[Piece]) -> int:
    """Count short numeric rows sitting just above/below a line with a bracket at their left.

    In a 3-row matrix the middle row shares the main line, so the outer rows appear as
    short orphan lines of numbers whose left edge starts right after the opening bracket.
    """
    lines = [line for line in group_visual_lines(pieces) if line]
    all_x0 = [p.x0 for p in pieces]
    all_x1 = [p.x1 for p in pieces]
    content_width = (max(all_x1) - min(all_x0)) if pieces else 0
    hits = 0
    for row in lines:
        chars = [c for p in row for c in p.chars if c.text.strip()]
        if not chars or content_width <= 0:
            continue
        row_x0, row_x1 = min(c.x0 for c in chars), max(c.x1 for c in chars)
        math_share = sum(c.is_math or c.text.isdigit() for c in chars) / len(chars)
        if row_x1 - row_x0 >= SHORT_LINE_SHARE * content_width or math_share < MATH_DOMINANT_SHARE:
            continue
        centre = (min(c.y0 for c in chars) + max(c.y1 for c in chars)) / 2
        size = max(c.size for c in chars)
        for other in lines:
            if other is row or other[0].page != row[0].page:
                continue
            other_chars = [c for p in other for c in p.chars if c.text.strip()]
            other_centre = (min(c.y0 for c in other_chars) + max(c.y1 for c in other_chars)) / 2
            if not 0 < abs(other_centre - centre) <= MATRIX_ROW_REACH * size:
                continue
            if any(c.text in OPENING_BRACKETS and -BRACKET_OVERLAP <= row_x0 - c.x1 <= BRACKET_GAP for c in other_chars):
                hits += 1
                break
    return hits


def count_deep_scripts(pieces: list[Piece]) -> int:
    """Count small glyphs shifted far from their line's baseline (limits under max/lim/sum)."""
    count = 0
    for line in group_visual_lines(pieces):
        visible = [c for p in line for c in p.chars if not c.is_blank]
        if not visible:
            continue
        main_size, main_baseline = line_metrics(visible)
        count += sum(
            c.size < SCRIPT_SIZE_RATIO * main_size and abs(c.baseline - main_baseline) > DEEP_SCRIPT_SHIFT * main_size
            for c in visible
        )
    return count


def count_underlines(chars: list[Char], graphics: list[Graphic]) -> int:
    """Count horizontal rules drawn directly under ordinary (non-math) text."""
    count = 0
    for rule in graphics:
        if rule.kind != "vector" or not rule.is_horizontal_rule or rule.width < MIN_UNDERLINE_WIDTH:
            continue
        resting = [
            c for c in chars
            if not c.is_math and c.text.strip() and c.x0 >= rule.x0 - OVERLAP_EPS and c.x1 <= rule.x1 + OVERLAP_EPS
            and rule.y0 - UNDERLINE_REACH <= c.y1 <= rule.y1 + OVERLAP_EPS
        ]
        count += bool(resting)
    return count


def count_fraction_bars(chars: list[Char], graphics: list[Graphic]) -> int:
    """Count short horizontal rules with math glyphs directly above and below them."""
    count = 0
    for bar in graphics:
        if bar.kind != "vector" or not bar.is_horizontal_rule or not 3 <= bar.width <= FRACTION_MAX_WIDTH:
            continue
        overlapping = [c for c in chars if c.is_math and c.x1 > bar.x0 and c.x0 < bar.x1 and c.text.strip()]
        above = any(bar.y0 - FRACTION_REACH <= c.y1 <= bar.y1 + OVERLAP_EPS for c in overlapping)
        below = any(bar.y0 - OVERLAP_EPS <= c.y0 <= bar.y1 + FRACTION_REACH for c in overlapping)
        count += above and below
    return count


def count_stacked_math_lines(pieces: list[Piece]) -> int:
    """Count short, math-dominated visual lines stacked directly on another such line."""
    lines = [line for line in group_visual_lines(pieces) if line]
    content_width = max((p.x1 for p in pieces), default=0) - min((p.x0 for p in pieces), default=0)
    math_lines = []
    for line in lines:
        chars = [c for p in line for c in p.chars if not c.is_blank]
        if not chars or content_width <= 0:
            continue
        width = max(c.x1 for c in chars) - min(c.x0 for c in chars)
        math_share = sum(c.is_math or c.text.isdigit() for c in chars) / len(chars)
        if width < SHORT_LINE_SHARE * content_width and math_share >= MATH_DOMINANT_SHARE:
            math_lines.append((line[0].page, min(c.x0 for c in chars), min(c.y0 for c in chars),
                               max(c.x1 for c in chars), max(c.y1 for c in chars)))
    stacked = 0
    for upper, lower in zip(math_lines, math_lines[1:]):
        same_page = upper[0] == lower[0]
        overlaps = upper[1] < lower[3] and lower[1] < upper[3]
        if same_page and overlaps and 0 <= lower[2] - upper[4] <= STACK_GAP:
            stacked += 1
    return stacked


def render_crop(doc: pymupdf.Document, regions: list[tuple[int, tuple[float, float, float, float]]], target: Path) -> None:
    """Stack a question's clip rectangles into one PNG image."""
    target.parent.mkdir(parents=True, exist_ok=True)
    width = CROP_X1 - CROP_X0
    heights = [clip[3] - clip[1] for _, clip in regions]
    sheet = pymupdf.open()
    page = sheet.new_page(width=width, height=sum(heights) + CROP_GAP * (len(regions) - 1))
    y = 0.0
    for (page_index, clip), height in zip(regions, heights):
        page.show_pdf_page(pymupdf.Rect(0, y, width, y + height), doc, page_index, clip=pymupdf.Rect(clip))
        y += height + CROP_GAP
    page.get_pixmap(matrix=pymupdf.Matrix(CROP_ZOOM, CROP_ZOOM), alpha=False).save(target)


def parse_mark_headers(headings: list[str]) -> dict[int, int]:
    """Map question numbers to marks using lines like 'Q.11 – Q.35 Carry ONE mark Each'."""
    marks: dict[int, int] = {}
    for heading in headings:
        match = MARK_HEADER_RE.search(heading)
        if match:
            first, last, word = int(match[1]), int(match[2]), match[3].lower()
            marks.update({number: WORD_TO_MARKS[word] for number in range(first, last + 1)})
    return marks
