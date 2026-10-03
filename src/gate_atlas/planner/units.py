"""Study units for the planner: syllabus clusters with expected marks, hours and PYQs.

Expected marks per unit (cluster) combine two estimates that are stable on their own:
* the section's mean marks per paper (sections are large, so 3 papers average well);
* the unit's share of its section, smoothed with a Dirichlet-multinomial prior:
      share_u = (marks_u + alpha * breadth_u) / (marks_section + alpha)
  where breadth_u is the unit's share of the section's syllabus items. A unit asked a lot
  (Python: 16 of 48 PD marks) keeps a large share; a unit asked once is pulled towards its
  breadth. `backtest_unit_marks` compares this with simpler estimators, holding out one
  paper at a time.
"""

import math
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from gate_atlas.analysis.forecast import fit_prior, posterior
from gate_atlas.config import PAPER_YEARS, ROOT_DIR

STUDY_HOURS_PATH = ROOT_DIR / "data" / "curation" / "study_hours.toml"
PART_MARKS = {"DA": 85.0, "GA": 15.0}
ALPHA_GRID = (1.0, 2.0, 5.0, 10.0, 20.0)
DEFAULT_ALPHA = 10.0  # marks of prior weight on breadth; chosen by the leave-one-paper-out backtest


@dataclass
class Unit:
    """One study unit (a syllabus cluster)."""

    id: str
    part: str
    section_id: str
    section_title: str
    title: str
    items: list[str]
    hours: float
    prereqs: list[str]
    expected_marks: float = 0.0
    questions: list[str] = field(default_factory=list)  # PYQ ids tagged with the unit's items


def unit_id(item: dict) -> str:
    """Unit id of a syllabus item: '<section id>:<cluster>'."""
    return f"{item['section_id']}:{item['cluster']}"


def unit_marks_by_year(records: list[dict], item_to_unit: dict[str, str]) -> dict[str, list[float]]:
    """Marks per paper whose primary item lies in each unit."""
    marks: dict[str, list[float]] = defaultdict(lambda: [0.0] * len(PAPER_YEARS))
    for record in records:
        unit = item_to_unit[record["syllabus_tags"]["primary"]]
        marks[unit][PAPER_YEARS.index(record["year"])] += record["marks"]
    return marks


def dirichlet_expected_marks(units: list[Unit], marks: dict[str, list[float]], years: list[int], alpha: float) -> dict[str, float]:
    """Section mean marks times the smoothed within-section share, from the given paper indices."""
    by_section: dict[str, list[Unit]] = defaultdict(list)
    for unit in units:
        by_section[unit.section_id].append(unit)
    expected = {}
    for members in by_section.values():
        unit_totals = {u.id: sum(marks.get(u.id, [0.0] * len(PAPER_YEARS))[y] for y in years) for u in members}
        section_total = sum(unit_totals.values())
        section_mean = section_total / len(years)
        item_count = sum(len(u.items) for u in members)
        for unit in members:
            breadth = len(unit.items) / item_count
            share = (unit_totals[unit.id] + alpha * breadth) / (section_total + alpha)
            expected[unit.id] = section_mean * share
    return expected


def load_units(records: list[dict], items: list[dict], alpha: float = DEFAULT_ALPHA) -> list[Unit]:
    """Build every study unit with hours, prerequisites, expected marks and tagged PYQs."""
    config = tomllib.loads(STUDY_HOURS_PATH.read_text(encoding="utf-8"))["units"]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        grouped[unit_id(item)].append(item)
    missing = sorted(set(grouped) - set(config))
    if missing:
        raise ValueError(f"study_hours.toml has no entry for units {missing}")
    units = []
    for uid, members in grouped.items():
        settings = config[uid]
        first = members[0]
        units.append(Unit(
            id=uid, part=first["part"], section_id=first["section_id"], section_title=first["section_title"],
            title=first["cluster"], items=[m["id"] for m in members], hours=float(settings["hours"]),
            prereqs=list(settings.get("prereqs", [])),
        ))
    item_to_unit = {item_id: u.id for u in units for item_id in u.items}
    marks = unit_marks_by_year(records, item_to_unit)
    expected = dirichlet_expected_marks(units, marks, list(range(len(PAPER_YEARS))), alpha)
    for unit in units:
        unit.expected_marks = expected[unit.id]
    for record in sorted(records, key=lambda r: (-r["year"], r["number"])):
        tags = record["syllabus_tags"]
        for uid in dict.fromkeys(item_to_unit[i] for i in (tags["primary"], *tags["secondary"])):
            next(u for u in units if u.id == uid).questions.append(record["id"])
    return units


def backtest_unit_marks(records: list[dict], items: list[dict], units: list[Unit]) -> dict:
    """Hold out each paper; compare estimators of each unit's marks in that paper (RMSE)."""
    item_to_unit = {item_id: u.id for u in units for item_id in u.items}
    marks = unit_marks_by_year(records, item_to_unit)
    n_years = len(PAPER_YEARS)
    errors: dict[str, list[float]] = defaultdict(list)
    for held_out in range(n_years):
        train = [y for y in range(n_years) if y != held_out]
        actual = {u.id: marks.get(u.id, [0.0] * n_years)[held_out] for u in units}
        estimates = {
            "unit mean of other papers": {u.id: np.mean([marks.get(u.id, [0.0] * n_years)[y] for y in train]) for u in units},
            "section mean x breadth share": dirichlet_expected_marks(units, marks, train, alpha=1e9),
            "item-level Gamma-Poisson (Phase 3)": _item_forecast_marks(records, items, units, held_out),
        }
        for alpha in ALPHA_GRID:
            estimates[f"Dirichlet-multinomial, alpha={alpha:g}"] = dirichlet_expected_marks(units, marks, train, alpha)
        for name, predicted in estimates.items():
            errors[name].extend((predicted[u.id] - actual[u.id]) ** 2 for u in units)
    return {name: round(math.sqrt(sum(values) / len(values)), 4) for name, values in errors.items()}


def _item_forecast_marks(records: list[dict], items: list[dict], units: list[Unit], held_out: int) -> dict[str, float]:
    """Phase 3 item forecast refitted without the held-out paper, summed per unit."""
    train_records = [r for r in records if PAPER_YEARS.index(r["year"]) != held_out]
    counts: dict[str, int] = defaultdict(int)
    marks_by_section, questions_by_section = defaultdict(float), defaultdict(int)
    for record in train_records:
        primary = record["syllabus_tags"]["primary"]
        counts[primary] += 1
        marks_by_section[primary.rsplit(".", 1)[0]] += record["marks"]
        questions_by_section[primary.rsplit(".", 1)[0]] += 1
    per_unit: dict[str, float] = defaultdict(float)
    item_to_unit = {item_id: u.id for u in units for item_id in u.items}
    for part in ("DA", "GA"):
        part_items = [i["id"] for i in items if i["part"] == part]
        fit = fit_prior({i: counts.get(i, 0) for i in part_items}, len(PAPER_YEARS) - 1)
        for item_id in part_items:
            section = item_id.rsplit(".", 1)[0]
            marks_each = marks_by_section[section] / questions_by_section[section] if questions_by_section[section] else 1.5
            per_unit[item_to_unit[item_id]] += posterior(fit, item_id, counts.get(item_id, 0))["expected_questions"] * marks_each
    return per_unit
