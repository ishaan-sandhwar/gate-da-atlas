"""Project-wide paths and exam-pattern constants."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
CROPS_DIR = PROCESSED_DIR / "crops"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"

PAPER_CODE = "DA"
PAPER_YEARS = (2024, 2025, 2026)
SYLLABUS_YEARS = (2024, 2025, 2026, 2027)
# The syllabus every question is tagged against: the newest official edition.
CANONICAL_SYLLABUS_YEAR = 2027

# Official GATE pattern for a 100-mark paper (same for every year so far).
EXPECTED_QUESTIONS_PER_PAPER = 65
EXPECTED_MARKS_PER_PAPER = 100
EXPECTED_SECTION_PATTERN = {
    # section: {marks_per_question: question_count}
    "GA": {1: 5, 2: 5},
    "DA": {1: 25, 2: 30},
}
