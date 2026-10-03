"""Invariants of the built dataset (skipped until `python -m gate_atlas build` has run)."""

from collections import Counter

import pytest

from gate_atlas.config import EXPECTED_MARKS_PER_PAPER, EXPECTED_QUESTIONS_PER_PAPER, PAPER_YEARS, PROCESSED_DIR, ROOT_DIR
from gate_atlas.dataset import REVIEW_REASONS, load_questions

QUESTIONS_PATH = PROCESSED_DIR / "questions.jsonl"
pytestmark = pytest.mark.skipif(not QUESTIONS_PATH.exists(), reason="dataset not built")


@pytest.fixture(scope="module")
def records() -> list[dict]:
    """All question records."""
    return load_questions(QUESTIONS_PATH)


def test_every_year_has_65_questions_and_100_marks(records: list[dict]) -> None:
    """The official paper pattern holds for every year."""
    for year in PAPER_YEARS:
        rows = [r for r in records if r["year"] == year]
        assert len(rows) == EXPECTED_QUESTIONS_PER_PAPER
        assert sum(r["marks"] for r in rows) == EXPECTED_MARKS_PER_PAPER
        assert sorted(r["number"] for r in rows) == list(range(1, EXPECTED_QUESTIONS_PER_PAPER + 1))


def test_ids_are_unique(records: list[dict]) -> None:
    """No two records share an id."""
    assert max(Counter(r["id"] for r in records).values()) == 1


def test_status_matches_reasons(records: list[dict]) -> None:
    """Clean records have no reasons; flagged records have known reasons."""
    for record in records:
        if record["status"] == "clean":
            assert record["review_reasons"] == []
        else:
            assert record["review_reasons"] and set(record["review_reasons"]) <= set(REVIEW_REASONS)


def test_clean_choice_questions_have_four_options_and_valid_keys(records: list[dict]) -> None:
    """Clean MCQ/MSQ records carry options A-D and their keyed letters exist."""
    for record in records:
        if record["status"] == "clean" and record["type"] in ("MCQ", "MSQ"):
            assert sorted(record["options"]) == ["A", "B", "C", "D"]
            if record["answer"]["kind"] == "options":
                assert set(record["answer"]["options"]) <= set(record["options"])


def test_every_record_has_a_crop(records: list[dict]) -> None:
    """The visual ground truth exists for every question."""
    assert all((ROOT_DIR / r["crop"]).exists() for r in records)
