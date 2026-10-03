"""Parse official GATE answer-key PDFs into one record per question."""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

QUESTION_TYPES = ("MCQ", "MSQ", "NAT")
NUMBER = r"-?\d+(?:\.\d+)?"
# One row of the key table: Q.No, Session, Type, Section, Key/Range, Marks.
ROW_RE = re.compile(
    rf"(?<!\S)(\d{{1,2}})\s+(\d{{1,2}})\s+(MCQ|MSQ|NAT)\s+(GA|DA)\s+"
    rf"(MTA|[A-D](?:\s*;\s*[A-D])*|{NUMBER}\s*to\s*{NUMBER})\s+([12])(?!\S)"
)
RANGE_RE = re.compile(rf"({NUMBER})\s*to\s*({NUMBER})")


@dataclass(frozen=True)
class KeyEntry:
    """One row of an official answer key."""

    number: int
    session: int
    qtype: str
    section: str
    raw: str
    marks: int

    @property
    def is_mta(self) -> bool:
        """True when the key awards marks to all candidates."""
        return self.raw == "MTA"

    @property
    def options(self) -> list[str]:
        """Correct option letters for MCQ/MSQ keys."""
        if self.is_mta or self.qtype == "NAT":
            return []
        return [letter.strip() for letter in self.raw.split(";")]

    @property
    def numeric_range(self) -> tuple[float, float] | None:
        """Inclusive accepted range for NAT keys."""
        match = RANGE_RE.fullmatch(self.raw)
        return (float(match[1]), float(match[2])) if match else None

    def as_answer(self) -> dict:
        """Answer in the dataset's JSON shape."""
        if self.is_mta:
            return {"kind": "mta"}
        if self.qtype == "NAT":
            low, high = self.numeric_range
            return {"kind": "range", "low": low, "high": high}
        return {"kind": "options", "options": self.options}


def parse_key_text(text: str) -> list[KeyEntry]:
    """Parse key rows out of the text of an answer-key PDF."""
    flat = re.sub(r"\s+", " ", text)
    entries = []
    for match in ROW_RE.finditer(flat):
        raw = re.sub(r"\s+", " ", match[5]).replace(" ;", ";").replace("; ", ";")
        entries.append(KeyEntry(int(match[1]), int(match[2]), match[3], match[4], raw, int(match[6])))
    return entries


def parse_key_pdf(pdf_path: Path) -> list[KeyEntry]:
    """Parse every row of an answer-key PDF."""
    with pymupdf.open(pdf_path) as doc:
        text = "\n".join(page.get_text() for page in doc)
    return parse_key_text(text)
