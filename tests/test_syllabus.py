"""Tests for syllabus normalization and the coverage guarantee."""

import pytest

from gate_atlas.syllabus import SyllabusError, check_coverage, content_words, normalize_text, split_sections

BODY = "Search: informed, uninformed, adversarial; logic, propositional, predicate"
PARTS = [
    {"heading": True, "source": "Search"},
    {"item": "01", "source": "informed"},
    {"item": "02", "source": "uninformed"},
    {"item": "03", "source": "adversarial"},
    {"heading": True, "source": "logic"},
    {"item": "04", "source": "propositional"},
    {"item": "05", "source": "predicate"},
]


def test_full_coverage_passes() -> None:
    """Parts that cover every word in order are accepted."""
    check_coverage("DA.AI", BODY, PARTS)


def test_dropped_phrase_is_rejected() -> None:
    """Leaving an official phrase out of the curation fails the build."""
    with pytest.raises(SyllabusError, match="not covered"):
        check_coverage("DA.AI", BODY, [part for part in PARTS if part["source"] != "adversarial"])


def test_invented_phrase_is_rejected() -> None:
    """A curated phrase that is not in the official text fails the build."""
    with pytest.raises(SyllabusError, match="not found"):
        check_coverage("DA.AI", BODY, [*PARTS, {"item": "06", "source": "planning"}])


def test_normalize_repairs_broken_glyphs_and_hyphenation() -> None:
    """2024's broken 'ti' glyph and line-break hyphens are repaired."""
    assert normalize_text("ProbabiliƟes and t-\ndistribuƟon, cross- validaƟon") == (
        "Probabilities and t-distribution, cross-validation"
    )


def test_split_sections_handles_both_layouts() -> None:
    """'Title: body' and 'Section N: Title body' layouts give the same words."""
    old = "Linear Algebra: Vector space, rank. AI: Search: informed"
    new = "Section 1: Linear Algebra Vector space, rank. Section 2: AI Search: informed"
    titles = ["Linear Algebra", "AI"]
    old_sections, new_sections = split_sections(old, titles), split_sections(new, titles)
    assert [content_words(s.body) for s in old_sections] == [content_words(s.body) for s in new_sections]
