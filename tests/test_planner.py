"""Tests for the planner: allocation optimality, mastery updates, profiles and the schedule."""

import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from gate_atlas.config import PROCESSED_DIR, ROOT_DIR
from gate_atlas.planner.allocate import (
    allocate,
    estimate_mastery,
    hours_cap,
    marginal_value,
    mastery_after,
    time_constant,
)
from gate_atlas.planner.profile import LEVELS, Profile, load_profile
from gate_atlas.planner.schedule import make_plan
from gate_atlas.planner.units import Unit, dirichlet_expected_marks


def _unit(uid: str, marks: float, hours: float, prereqs: list[str] | None = None) -> Unit:
    section = uid.split(":")[0]
    return Unit(uid, "DA", section, section, uid.split(":")[1], [f"{section}.01"], hours, prereqs or [], marks,
                ["DA2024-Q11", "DA2026-Q12"])


UNITS = [
    _unit("DA.PS:A", 8.0, 20.0),
    _unit("DA.PS:B", 3.0, 10.0, ["DA.PS:A"]),
    _unit("DA.LA:C", 5.0, 16.0),
    _unit("DA.AI:D", 0.5, 12.0),
]


def _profile(**overrides) -> Profile:
    base = dict(name="t", exam_date=date(2027, 2, 6), start_date=date(2026, 10, 5), hours_per_day=2.0,
                study_days_per_week=6, ratings={"default": "basic"})
    return Profile(**{**base, **overrides})


def test_allocation_meets_kkt_conditions() -> None:
    """Hours add up to the budget; funded units share one marginal value; unfunded ones are below it."""
    mastery = {u.id: 0.3 for u in UNITS}
    hours, lam = allocate(UNITS, mastery, budget=25.0)
    assert math.isclose(sum(hours.values()), 25.0, rel_tol=1e-6)
    for unit in UNITS:
        cap = hours_cap(mastery[unit.id], time_constant(unit))
        if 1e-6 < hours[unit.id] < cap - 1e-6:
            assert math.isclose(marginal_value(unit, mastery[unit.id], hours[unit.id]), lam, rel_tol=1e-4)
        if hours[unit.id] <= 1e-9:
            assert marginal_value(unit, mastery[unit.id]) <= lam + 1e-12


def test_weaker_unit_gets_more_hours() -> None:
    """Lower mastery on the same unit attracts more hours."""
    strong, _ = allocate(UNITS, {u.id: 0.3 for u in UNITS} | {"DA.LA:C": 0.8}, budget=25.0)
    weak, _ = allocate(UNITS, {u.id: 0.3 for u in UNITS} | {"DA.LA:C": 0.1}, budget=25.0)
    assert weak["DA.LA:C"] > strong["DA.LA:C"]


def test_slack_budget_reaches_every_cap() -> None:
    """With more time than needed every unit reaches the mastery cap and lambda is zero."""
    mastery = {u.id: 0.3 for u in UNITS}
    hours, lam = allocate(UNITS, mastery, budget=10_000.0)
    assert lam == 0.0
    assert all(math.isclose(hours[u.id], hours_cap(0.3, time_constant(u))) for u in UNITS)


def test_mock_evidence_and_progress_move_mastery() -> None:
    """A bad mock lowers mastery, a good one raises it, logged hours raise it along the curve."""
    base, _ = estimate_mastery(UNITS, _profile())
    after, notes = estimate_mastery(UNITS, _profile(
        progress=[{"unit": "DA.AI:D", "hours": 6}],
        mocks=[{"date": "2026-12-01", "results": {"DA.PS": [1, 10], "DA.LA:C": [9, 10]}}],
    ))
    assert after["DA.PS:A"] < base["DA.PS:A"] and after["DA.PS:B"] < base["DA.PS:B"]
    assert after["DA.LA:C"] > base["DA.LA:C"]
    assert math.isclose(after["DA.AI:D"], mastery_after(base["DA.AI:D"], 6, time_constant(UNITS[3])))
    assert len(notes) == 3
    with pytest.raises(ValueError):
        estimate_mastery(UNITS, _profile(mocks=[{"results": {"DA.XX": [1, 2]}}]))


def test_rating_precedence() -> None:
    """Unit rating beats section, section beats part, part beats default."""
    profile = _profile(ratings={"default": "weak", "DA": "okay", "DA.PS": "good", "DA.PS:A": "strong"})
    assert profile.mastery("DA.PS:A", "DA.PS", "DA") == LEVELS["strong"]
    assert profile.mastery("DA.PS:B", "DA.PS", "DA") == LEVELS["good"]
    assert profile.mastery("DA.LA:C", "DA.LA", "DA") == LEVELS["okay"]
    assert profile.mastery("GA.QA:Q", "GA.QA", "GA") == LEVELS["weak"]


def test_dirichlet_shares_preserve_section_totals() -> None:
    """Unit expected marks within a section add up to the section's mean marks."""
    marks = {"DA.PS:A": [6.0, 8.0, 10.0], "DA.PS:B": [0.0, 1.0, 0.0], "DA.LA:C": [5.0, 5.0, 5.0], "DA.AI:D": [0.0, 0.0, 0.0]}
    expected = dirichlet_expected_marks(UNITS, marks, [0, 1, 2], alpha=10.0)
    assert math.isclose(expected["DA.PS:A"] + expected["DA.PS:B"], (24 + 1) / 3)
    assert expected["DA.PS:A"] > expected["DA.PS:B"] > 0


def test_schedule_respects_capacity_prerequisites_and_mock_phase() -> None:
    """No week is over capacity; a unit starts after its prerequisite; mocks sit in the final weeks."""
    mastery = {u.id: 0.3 for u in UNITS}
    plan = make_plan(UNITS, mastery, _profile())
    assert all(w.planned <= w.capacity + 1e-6 for w in plan.weeks)
    first_week = {uid: min(w.index for w in plan.weeks if uid in w.learning) for uid in plan.hours if plan.hours[uid] > 0}
    finished_week = {uid: w.index for w in plan.weeks for uid in w.finished}
    if {"DA.PS:A", "DA.PS:B"} <= set(first_week):
        assert first_week["DA.PS:B"] >= finished_week["DA.PS:A"]
    assert all(w.phase == "final" for w in plan.weeks if w.mocks)
    practice = [q for w in plan.weeks for qs in w.practice.values() for q in qs]
    assert "DA2026-Q12" not in practice  # 2026 is reserved for a full mock by default


def test_profile_validation(tmp_path: Path) -> None:
    """Exam date must follow the start date."""
    bad = tmp_path / "bad.toml"
    bad.write_text('exam_date = 2026-01-01\nstart_date = 2026-02-01\nhours_per_day = 2\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_profile(bad)


EXAMPLE = ROOT_DIR / "examples" / "profile_gate2027.toml"


@pytest.mark.skipif(not (PROCESSED_DIR / "questions.jsonl").exists(), reason="dataset not built")
def test_example_plan_on_real_data() -> None:
    """The shipped example builds, uses the whole learning budget sensibly and stays within capacity."""
    from gate_atlas.dataset import load_questions
    from gate_atlas.planner.units import load_units
    from gate_atlas.tagging.text import load_items

    units = load_units(load_questions(), load_items())
    assert math.isclose(sum(u.expected_marks for u in units if u.part == "DA"), 85.0)
    assert math.isclose(sum(u.expected_marks for u in units if u.part == "GA"), 15.0)
    profile = load_profile(EXAMPLE)
    mastery, _ = estimate_mastery(units, profile)
    plan = make_plan(units, mastery, profile)
    assert all(w.planned <= w.capacity + 1e-6 for w in plan.weeks)
    assert plan.weeks[-1].end == profile.exam_date - timedelta(days=1)
    assert plan.secured(after=True) > plan.secured(after=False)
