"""Reference syllabus tags: loading, validation and the shared tag record."""

import csv
from dataclasses import dataclass
from pathlib import Path

from gate_atlas.config import ROOT_DIR

REFERENCE_PATH = ROOT_DIR / "data" / "curation" / "reference_tags.csv"
FITS = ("direct", "indirect", "outside")
CONFIDENCES = ("high", "medium", "low")
MAX_SECONDARY = 3


@dataclass(frozen=True)
class Tag:
    """Syllabus tags of one question, from any tagger."""

    question_id: str
    primary: str
    secondary: tuple[str, ...] = ()
    fit: str = ""
    confidence: str = ""
    rationale: str = ""

    @property
    def items(self) -> tuple[str, ...]:
        """Primary followed by secondary items."""
        return (self.primary, *self.secondary)

    def as_dict(self) -> dict:
        """JSON-friendly form."""
        return {
            "primary": self.primary,
            "secondary": list(self.secondary),
            "fit": self.fit,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


def load_reference(path: Path = REFERENCE_PATH) -> dict[str, Tag]:
    """Read the reference tags CSV into Tag objects keyed by question id."""
    tags: dict[str, Tag] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            secondary = tuple(item.strip() for item in row["secondary"].split(";") if item.strip())
            tags[row["id"]] = Tag(
                row["id"], row["primary"].strip(), secondary, row["fit"].strip(), row["confidence"].strip(),
                row["rationale"].strip(),
            )
    return tags


def part_of(item_id: str) -> str:
    """Paper part of a syllabus item id: 'GA' or 'DA'."""
    return item_id.split(".", 1)[0]


def validate_tags(tags: dict[str, Tag], records: list[dict], item_ids: set[str], *, strict: bool = True) -> list[str]:
    """Return problems: unknown ids, wrong paper part, bad fields, missing or extra questions."""
    problems = []
    sections = {r["id"]: r["section"] for r in records}
    missing = sorted(set(sections) - set(tags))
    extra = sorted(set(tags) - set(sections))
    if strict and missing:
        problems.append(f"questions without tags: {missing}")
    if extra:
        problems.append(f"tags for unknown questions: {extra}")
    for question_id, tag in tags.items():
        if question_id not in sections:
            continue
        unknown = [item for item in tag.items if item not in item_ids]
        if unknown:
            problems.append(f"{question_id}: unknown syllabus ids {unknown}")
        wrong_part = [item for item in tag.items if part_of(item) != sections[question_id]]
        if wrong_part:
            problems.append(f"{question_id}: items {wrong_part} are outside its {sections[question_id]} section")
        if tag.primary in tag.secondary:
            problems.append(f"{question_id}: primary repeated in secondary")
        if len(tag.secondary) > MAX_SECONDARY:
            problems.append(f"{question_id}: more than {MAX_SECONDARY} secondary items")
        if tag.fit not in FITS or tag.confidence not in CONFIDENCES:
            problems.append(f"{question_id}: fit/confidence must be one of {FITS}/{CONFIDENCES}")
    return problems
