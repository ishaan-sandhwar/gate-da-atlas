"""Tests for tag validation, the LLM prompt/schema helpers, ML scoring and evaluation."""

import numpy as np

from gate_atlas.tagging.evaluate import _metrics, agreement
from gate_atlas.tagging.llm import build_messages, parse_tag, response_schema
from gate_atlas.tagging.ml import Embeddings, blend_scores, zero_shot_rankings
from gate_atlas.tagging.reference import Tag, validate_tags

ITEMS = [
    {"id": "DA.PS.08", "label": "Bayes' theorem", "section_title": "Probability and Statistics", "part": "DA"},
    {"id": "DA.LA.12", "label": "Eigenvalues & eigenvectors", "section_title": "Linear Algebra", "part": "DA"},
    {"id": "GA.QA.06", "label": "Series", "section_title": "Quantitative Aptitude", "part": "GA"},
]
RECORDS = [
    {"id": "DA2024-Q58", "section": "DA", "status": "clean", "type": "NAT", "marks": 2, "stem": "Find P(T|S).", "options": None},
    {"id": "DA2024-Q13", "section": "DA", "status": "needs_review", "type": "MCQ", "marks": 1, "stem": "Eigenvalues of M?", "options": {"A": "real", "B": "complex"}},
    {"id": "DA2024-Q04", "section": "GA", "status": "clean", "type": "MCQ", "marks": 1, "stem": "Sum the series.", "options": {"A": "7/2"}},
]
ITEM_IDS = {i["id"] for i in ITEMS}


def test_validate_tags_flags_unknown_ids_wrong_part_and_bad_fields() -> None:
    """Every rule of the tag contract is enforced."""
    tags = {
        "DA2024-Q58": Tag("DA2024-Q58", "DA.PS.08", ("DA.PS.08",), "direct", "high"),
        "DA2024-Q13": Tag("DA2024-Q13", "GA.QA.06", (), "sideways", "high"),
        "DA2024-Q04": Tag("DA2024-Q04", "GA.QA.99", (), "direct", "high"),
    }
    problems = " ".join(validate_tags(tags, RECORDS, ITEM_IDS))
    assert "primary repeated" in problems
    assert "outside its DA section" in problems
    assert "fit/confidence" in problems
    assert "unknown syllabus ids" in problems


def test_strict_schema_requires_every_field_and_limits_ids() -> None:
    """Groq strict mode needs required fields and no extra properties."""
    schema = response_schema(["DA2024-Q58"], ["DA.PS.08", "DA.LA.12"])
    result = schema["properties"]["results"]["items"]
    assert schema["additionalProperties"] is False and result["additionalProperties"] is False
    assert set(result["required"]) == set(result["properties"])
    assert result["properties"]["primary"]["enum"] == ["DA.PS.08", "DA.LA.12"]


def test_hybrid_prompt_lists_each_questions_own_candidates() -> None:
    """In hybrid mode the prompt carries per-question candidates, not the whole syllabus."""
    candidates = {"DA2024-Q58": [ITEMS[0]], "DA2024-Q13": [ITEMS[1]]}
    text = build_messages(RECORDS[:2], ITEMS, candidates)[1]["content"]
    assert "Candidate items for this question: DA.PS.08 Bayes' theorem" in text
    assert "Candidate items for this question: DA.LA.12" in text
    assert "## Probability and Statistics" not in text


def test_parse_tag_drops_duplicate_and_disallowed_secondaries() -> None:
    """Secondary items repeat neither the primary nor items outside the allowed set."""
    payload = {"id": "q", "primary": "A", "secondary": ["A", "B", "B", "Z"], "fit": "direct", "confidence": "low", "rationale": " r "}
    tag = parse_tag(payload, {"A", "B"})
    assert tag.secondary == ("B",) and tag.rationale == "r"


def _embeddings() -> Embeddings:
    """Three questions and three items in 2D, unit-normalised."""
    questions = np.array([[1.0, 0.0], [0.0, 1.0], [0.6, 0.8]])
    items = np.array([[1.0, 0.0], [0.0, 1.0], [0.6, 0.8]])
    return Embeddings([r["id"] for r in RECORDS], questions, [i["id"] for i in ITEMS], items)


def test_zero_shot_ranks_only_items_of_the_questions_part() -> None:
    """A GA question never receives a DA item and vice versa."""
    rankings = zero_shot_rankings(_embeddings(), RECORDS)
    assert [item for item, _ in rankings["DA2024-Q04"]][0] == "GA.QA.06"
    assert all(item.startswith("DA.") for item, _ in rankings["DA2024-Q58"] if _ != -np.inf)


def test_blend_scores_are_a_probability_mixture_over_the_part() -> None:
    """Scores over the part's items sum to one; other parts are excluded."""
    reference = {r["id"]: Tag(r["id"], p) for r, p in zip(RECORDS, ["DA.PS.08", "DA.LA.12", "GA.QA.06"])}
    scores = blend_scores(0, [1], _embeddings(), RECORDS, reference, weight=0.5, temperature=0.05)
    finite = scores[np.isfinite(scores)]
    assert np.isclose(finite.sum(), 1.0) and len(finite) == 2


def test_metrics_and_agreement() -> None:
    """Primary accuracy, acceptable accuracy and agreement buckets add up."""
    reference = {"a": Tag("a", "DA.PS.08", ("DA.LA.12",)), "b": Tag("b", "DA.LA.12")}
    rows = [{"id": "a", "section": "DA"}, {"id": "b", "section": "DA"}]
    clusters = {"DA.PS.08": "x", "DA.LA.12": "y"}
    llm = {"a": {"primary": "DA.LA.12", "secondary": []}, "b": {"primary": "DA.LA.12", "secondary": []}}
    scores = _metrics(rows, llm, reference, clusters)
    assert scores["primary"] == 0.5 and scores["primary_in_reference_items"] == 1.0
    ml = {"a": {"primary": "DA.PS.08"}, "b": {"primary": "DA.LA.12"}}
    stats = agreement(llm, ml, reference)
    assert stats["agreement_rate"] == 0.5 and stats["accuracy_when_agree"] == 1.0
    assert stats["first_accuracy_when_disagree"] == 0.0 and stats["second_accuracy_when_disagree"] == 1.0
