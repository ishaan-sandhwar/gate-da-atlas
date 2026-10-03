"""Build the tagged syllabus from the official syllabus PDFs and the curation file.

The curation file (data/curation/syllabus.toml) splits each official section into
taggable items, interleaved with the official sub-headings ("Search algorithms:").
Every part stores the exact official wording it comes from, and the build verifies
that the parts, read in order, cover the whole official section with only punctuation
and "and" left over. So no item can be invented, and no official phrase can be
silently dropped.
"""

import csv
import difflib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from gate_atlas.config import CANONICAL_SYLLABUS_YEAR, RAW_DIR, ROOT_DIR, SYLLABUS_YEARS

CURATION_PATH = ROOT_DIR / "data" / "curation" / "syllabus.toml"
GLYPH_FIXES = {"Ɵ": "ti", "Ʃ": "tt", "ﬁ": "fi", "ﬀ": "ff", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "’": "'"}
SEPARATOR_RE = re.compile(r"[\s,;:.()\-–—]+|\band\b")
SECTION_MARKER_RE = re.compile(r"Section\s+\d+\s*:")
LIST_MARKER_RE = re.compile(r"\((?:i|ii|iii|iv)\)\s*")


class SyllabusError(ValueError):
    """Raised when the curation does not match the official syllabus text."""


@dataclass(frozen=True)
class SectionText:
    """Official text of one syllabus section."""

    title: str
    body: str


def normalize_text(text: str) -> str:
    """Repair broken glyphs, join hyphenated line breaks and collapse whitespace."""
    for broken, fixed in GLYPH_FIXES.items():
        text = text.replace(broken, fixed)
    text = re.sub(r"-\s*\n\s*", "-", text)  # "t-\ndistribution" -> "t-distribution"
    text = re.sub(r"-\s+(?=[a-z])", "-", text)  # "cross- validation" -> "cross-validation"
    return re.sub(r"\s+", " ", text).strip()


def pdf_text(path: Path) -> str:
    """Normalized text of a (one-page) syllabus PDF."""
    with pymupdf.open(path) as doc:
        return normalize_text("\n".join(page.get_text() for page in doc))


def split_sections(text: str, titles: list[str]) -> list[SectionText]:
    """Cut a syllabus text into sections using the known section titles, in order."""
    positions = []
    cursor = 0
    for title in titles:
        match = re.compile(rf"(?<![A-Za-z]){re.escape(title)}\s*:?").search(text, cursor)
        if not match:
            raise SyllabusError(f"Section title {title!r} not found after offset {cursor}")
        positions.append((match.start(), match.end()))
        cursor = match.end()
    sections = []
    for index, title in enumerate(titles):
        end = positions[index + 1][0] if index + 1 < len(titles) else len(text)
        body = text[positions[index][1]:end]
        body = SECTION_MARKER_RE.sub(" ", body)
        body = LIST_MARKER_RE.sub("", body)
        sections.append(SectionText(title, re.sub(r"\s+", " ", body).strip(" .")))
    return sections


def content_words(text: str) -> list[str]:
    """Lower-case word sequence used to compare editions."""
    return re.findall(r"[a-z0-9]+", text.lower().replace("—", " ").replace("–", " "))


def check_coverage(section_id: str, body: str, parts: list[dict]) -> None:
    """Verify items and headings cover the official section text exactly, in order."""
    cursor = 0
    for part in parts:
        source = part["source"]
        found = body.find(source, cursor)
        if found < 0:
            raise SyllabusError(f"{section_id}: {source!r} not found in order in official text")
        _check_gap(section_id, body[cursor:found])
        cursor = found + len(source)
    _check_gap(section_id, body[cursor:])


def _check_gap(section_id: str, gap: str) -> None:
    """Fail if text between curated parts contains words."""
    leftover = SEPARATOR_RE.sub("", gap)
    if leftover:
        raise SyllabusError(f"{section_id}: official text not covered by any item: {gap!r}")


def build_syllabus() -> dict:
    """Return the syllabus document: curated items checked against every edition."""
    curation = tomllib.loads(CURATION_PATH.read_text(encoding="utf-8"))
    papers = {}
    for paper_code, paper in curation["paper"].items():
        titles = [section["title"] for section in paper["section"]]
        editions = {}
        canonical: list[SectionText] = []
        for year in SYLLABUS_YEARS:
            sections = split_sections(pdf_text(RAW_DIR / f"{year}_{paper_code}_syllabus.pdf"), titles)
            editions[year] = sections
            if year == CANONICAL_SYLLABUS_YEAR:
                canonical = sections

        edition_report = {}
        for year, sections in editions.items():
            differences = []
            for base, other in zip(canonical, sections):
                if content_words(base.body) != content_words(other.body):
                    diff = difflib.unified_diff(content_words(base.body), content_words(other.body), lineterm="", n=0)
                    differences.append({"section": base.title, "diff": [line for line in diff if line[:1] in "+-"][2:]})
            edition_report[str(year)] = {"identical_to_canonical": not differences, "differences": differences}

        out_sections = []
        for number, (section, official) in enumerate(zip(paper["section"], canonical), start=1):
            parts = section["parts"]
            check_coverage(section["id"], official.body, parts)
            items = [
                {
                    "id": f"{section['id']}.{part['item']}",
                    "label": part["label"],
                    "cluster": part.get("cluster", section["title"]),
                    "official_text": part["source"],
                    "note": part.get("note", ""),
                }
                for part in parts
                if "item" in part
            ]
            out_sections.append({
                "id": section["id"],
                "number": number,
                "title": section["title"],
                "official_text": official.body,
                "items": items,
            })
        papers[paper_code] = {
            "title": paper["title"],
            "canonical_edition": CANONICAL_SYLLABUS_YEAR,
            "editions": edition_report,
            "sections": out_sections,
        }
    _check_unique_ids(papers)
    return {"papers": papers}


def _check_unique_ids(papers: dict) -> None:
    """Fail on duplicate item ids."""
    seen = set()
    for paper in papers.values():
        for section in paper["sections"]:
            for item in section["items"]:
                if item["id"] in seen:
                    raise SyllabusError(f"duplicate syllabus id {item['id']}")
                seen.add(item["id"])


def write_syllabus_outputs(syllabus: dict, out_dir: Path) -> None:
    """Write syllabus.json (nested) and syllabus_items.csv (one row per item)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "syllabus.json").write_text(json.dumps(syllabus, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = flat_items(syllabus)
    with (out_dir / "syllabus_items.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def flat_items(syllabus: dict) -> list[dict]:
    """One row per syllabus item, for CSV export and tagging."""
    rows = []
    for paper_code, paper in syllabus["papers"].items():
        for section in paper["sections"]:
            for item in section["items"]:
                rows.append({
                    "paper": paper_code,
                    "section_id": section["id"],
                    "section_title": section["title"],
                    "item_id": item["id"],
                    "label": item["label"],
                    "cluster": item["cluster"],
                    "official_text": item["official_text"],
                    "note": item["note"],
                })
    return rows
