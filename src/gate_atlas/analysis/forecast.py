"""Empirical-Bayes forecast of how often each syllabus item is asked in the next paper.

Model, fitted separately for the DA and GA parts:
    c[i,t] | rate_i  ~ Poisson(rate_i)                questions with primary item i in year t
    rate_i           ~ Gamma(shape=a, rate=a / mu_s)  mu_s = mean questions per item per year
                                                        in item i's syllabus section s
mu_s comes from the data, plus a 0.5-question pseudo-count so that a section with no
question so far is not forecast at exactly zero. The shared shape a measures how much
items differ within a section. It is fitted by maximum marginal likelihood: the 3-year
total y_i is negative binomial with r = a and mean T * mu_s.

The posterior is rate_i | y_i ~ Gamma(a + y_i, a / mu_s + T): an item that was never asked
is pulled up towards its section's rate, and a frequent item is pulled down. The
next-year count is negative binomial, so P(asked at least once) = 1 - (b'/(b'+1))^a'.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import gamma, nbinom

SECTION_PSEUDO_QUESTIONS = 0.5
LOG_SHAPE_BOUNDS = (math.log(1e-3), math.log(1e3))
CREDIBLE_LOW, CREDIBLE_HIGH = 0.1, 0.9  # 80% credible interval
PROBABILITY_FLOOR = 1e-6  # keeps log loss finite


@dataclass(frozen=True)
class Fit:
    """Fitted prior: shared shape and per-section mean rates."""

    shape: float
    section_rates: dict[str, float]
    years: int


def section_of(item_id: str) -> str:
    """Section id of an item id."""
    return item_id.rsplit(".", 1)[0]


def fit_prior(totals: dict[str, int], years: int) -> Fit:
    """Fit section rates and the shared Gamma shape from per-item totals over `years` papers."""
    section_totals, section_sizes = defaultdict(int), defaultdict(int)
    for item_id, total in totals.items():
        section_totals[section_of(item_id)] += total
        section_sizes[section_of(item_id)] += 1
    rates = {
        section: (section_totals[section] + SECTION_PSEUDO_QUESTIONS) / (years * section_sizes[section])
        for section in section_sizes
    }
    observed = np.array(list(totals.values()))
    means = np.array([years * rates[section_of(item_id)] for item_id in totals])

    def negative_log_likelihood(log_shape: float) -> float:
        shape = math.exp(log_shape)
        return float(-nbinom.logpmf(observed, shape, shape / (shape + means)).sum())

    best = minimize_scalar(negative_log_likelihood, bounds=LOG_SHAPE_BOUNDS, method="bounded")
    return Fit(shape=math.exp(best.x), section_rates=rates, years=years)


def posterior(fit: Fit, item_id: str, total: int) -> dict:
    """Posterior summary for one item: expected questions, P(asked), 80% interval of the rate."""
    rate = fit.section_rates[section_of(item_id)]
    shape_post = fit.shape + total
    rate_post = fit.shape / rate + fit.years
    low, high = gamma.ppf([CREDIBLE_LOW, CREDIBLE_HIGH], shape_post, scale=1 / rate_post)
    return {
        "expected_questions": shape_post / rate_post,
        "p_asked": 1 - (rate_post / (rate_post + 1)) ** shape_post,
        "rate_low": float(low),
        "rate_high": float(high),
    }


def forecast(counts: dict[str, list[int]], marks_per_question: dict[str, float]) -> tuple[Fit, dict[str, dict]]:
    """Fit on all years and forecast every item; expected marks use the section's marks/question."""
    years = len(next(iter(counts.values())))
    fit = fit_prior({item_id: sum(c) for item_id, c in counts.items()}, years)
    out = {}
    for item_id, per_year in counts.items():
        summary = posterior(fit, item_id, sum(per_year))
        summary["expected_marks"] = summary["expected_questions"] * marks_per_question[section_of(item_id)]
        out[item_id] = {key: round(value, 4) for key, value in summary.items()}
    return fit, out


def backtest(counts: dict[str, list[int]]) -> dict:
    """Leave-one-year-out check of three ways to predict whether each item is asked.

    pooled    - every item gets its section's rate (complete pooling, no item history);
    empirical - each item's own frequency in the training years (no pooling);
    bayes     - the empirical-Bayes posterior above (partial pooling).
    Years are treated as exchangeable; with three papers this is the only way to hold one out.
    """
    years = len(next(iter(counts.values())))
    scores = {name: {"brier": [], "log_loss": [], "count_squared_error": []} for name in ("pooled", "empirical", "bayes")}
    for held_out in range(years):
        train = {item_id: [c for t, c in enumerate(per_year) if t != held_out] for item_id, per_year in counts.items()}
        fit = fit_prior({item_id: sum(c) for item_id, c in train.items()}, years - 1)
        for item_id, per_year in counts.items():
            actual = per_year[held_out]
            asked = float(actual > 0)
            rate = fit.section_rates[section_of(item_id)]
            bayes = posterior(fit, item_id, sum(train[item_id]))
            predictions = {
                "pooled": (1 - math.exp(-rate), rate),
                "empirical": (sum(c > 0 for c in train[item_id]) / (years - 1), sum(train[item_id]) / (years - 1)),
                "bayes": (bayes["p_asked"], bayes["expected_questions"]),
            }
            for name, (p_asked, expected) in predictions.items():
                p = min(max(p_asked, PROBABILITY_FLOOR), 1 - PROBABILITY_FLOOR)
                scores[name]["brier"].append((p_asked - asked) ** 2)
                scores[name]["log_loss"].append(-(asked * math.log(p) + (1 - asked) * math.log(1 - p)))
                scores[name]["count_squared_error"].append((expected - actual) ** 2)
    # Squared error (not absolute error) is the proper score for a predicted mean count.
    return {
        name: {
            "brier": round(float(np.mean(metrics["brier"])), 4),
            "log_loss": round(float(np.mean(metrics["log_loss"])), 4),
            "count_rmse": round(float(np.sqrt(np.mean(metrics["count_squared_error"]))), 4),
        }
        for name, metrics in scores.items()
    }
