"""Tests for weightage attribution, trend labels and the empirical-Bayes forecast."""

import math

import pytest

from gate_atlas.analysis.forecast import backtest, fit_prior, posterior
from gate_atlas.analysis.weightage import aggregate, attribution, trend_label
from gate_atlas.config import PAPER_YEARS, PROCESSED_DIR


def test_attribution_weights_sum_to_one() -> None:
    """Primary gets everything; shared splits 1 : 0.5 : 0.5 and still sums to 1."""
    tags = {"primary": "A", "secondary": ["B", "C"]}
    assert attribution(tags, "primary") == {"A": 1.0}
    shared = attribution(tags, "shared")
    assert math.isclose(sum(shared.values()), 1.0) and math.isclose(shared["A"], 0.5) and math.isclose(shared["B"], 0.25)


@pytest.mark.parametrize(
    ("values", "label"),
    [([15, 19, 21], "rising"), ([20, 14, 14], "falling"), ([8, 11, 3], "mixed"), ([2, 3, 2], "stable")],
)
def test_trend_labels(values: list[float], label: str) -> None:
    """Only monotonic series with a real slope count as rising or falling."""
    assert trend_label(values)[1] == label


def test_posterior_shrinks_towards_section_rate() -> None:
    """A never-asked item gets a positive forecast; a frequent one is pulled down."""
    totals = {"DA.PS.01": 0, "DA.PS.02": 6, "DA.PS.03": 1, "DA.PS.04": 2}
    fit = fit_prior(totals, years=3)
    rate = fit.section_rates["DA.PS"]
    never, frequent = posterior(fit, "DA.PS.01", 0), posterior(fit, "DA.PS.02", 6)
    assert 0 < never["expected_questions"] < rate < frequent["expected_questions"] < 6 / 3
    assert 0 < never["p_asked"] < frequent["p_asked"] < 1
    assert frequent["rate_low"] < frequent["expected_questions"] < frequent["rate_high"]


def test_backtest_reports_every_method() -> None:
    """The leave-one-year-out backtest scores all three predictors with proper scores."""
    counts = {"DA.PS.01": [0, 0, 1], "DA.PS.02": [2, 1, 3], "DA.LA.01": [1, 0, 0], "DA.LA.02": [0, 1, 1]}
    scores = backtest(counts)
    assert set(scores) == {"pooled", "empirical", "bayes"}
    assert all(0 <= s["brier"] <= 1 and s["log_loss"] >= 0 and s["count_rmse"] >= 0 for s in scores.values())


ANALYSIS_PATH = PROCESSED_DIR / "analysis" / "analysis.json"


@pytest.mark.skipif(not ANALYSIS_PATH.exists(), reason="analysis not built")
def test_built_analysis_conserves_marks() -> None:
    """Sections sum to 85 DA and 15 GA marks every year under both attribution schemes."""
    import json

    document = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
    for scheme in ("primary", "shared"):
        for part, total in (("DA", 85), ("GA", 15)):
            for year in PAPER_YEARS:
                marks = sum(r[f"marks_{year}"] for r in document["sections"][scheme] if r["part"] == part)
                assert math.isclose(marks, total, abs_tol=0.01)  # stored values are rounded to 3 decimals
    never = [i for i in document["items"] if i["status"] == "never_asked"]
    assert all(i["primary_questions"] == 0 and i["secondary_uses"] == 0 for i in never)


def test_aggregate_counts_questions_once_per_scheme() -> None:
    """Question weights per year add up to the number of questions."""
    items = [{"id": x} for x in ("A", "B", "C")]
    records = [
        {"year": PAPER_YEARS[0], "marks": 2, "syllabus_tags": {"primary": "A", "secondary": ["B"]}},
        {"year": PAPER_YEARS[0], "marks": 1, "syllabus_tags": {"primary": "C", "secondary": []}},
    ]
    for scheme in ("primary", "shared"):
        table = aggregate(records, items, scheme)
        assert math.isclose(sum(t["questions"][PAPER_YEARS[0]] for t in table.values()), 2)
        assert math.isclose(sum(t["marks"][PAPER_YEARS[0]] for t in table.values()), 3)
