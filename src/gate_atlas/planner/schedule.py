"""Turn the hour allocation into a weekly calendar.

* Weeks run from the start date to the day before the exam; each week's capacity is its
  study days times hours per day.
* The last `final_weeks` weeks are the mock phase: full-length mocks (reserved official
  papers first), their review, and targeted revision of the units where marks are most at
  risk.
* Before that, units are learned at most PARALLEL_UNITS at a time. The order respects
  prerequisites and puts the best marks-per-hour units first, mixing sections.
* A unit finished in week c is revised in weeks c+1, c+3 and c+7 (spaced repetition).
  Revision takes REVISION_SHARE of its learning hours in total and is protected from
  being crowded out by new learning.
* The week a unit is finished, it lists past-paper questions on that unit to solve,
  excluding papers reserved as mocks.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from gate_atlas.planner.allocate import allocate, expected_secured, marginal_value, mastery_after, time_constant
from gate_atlas.planner.profile import Profile
from gate_atlas.planner.units import Unit

REVISION_SHARE = 0.15
REVISION_OFFSETS_WEEKS = (1, 3, 7)
MAX_REVISION_SHARE_OF_WEEK = 0.4
PARALLEL_UNITS = 3
MOCK_TEST_HOURS = 3.0
MOCK_REVIEW_HOURS = 2.0
MOCKS_BY_WEEKS_LEFT = {4: 1, 3: 1, 2: 2, 1: 1}  # mocks in the week that is N weeks before the exam
PYQ_PER_UNIT = 6
TARGETED_UNITS_PER_WEEK = 6
HOUR_STEP = 0.5
EPS = 1e-9
DAYS_PER_WEEK = 7


@dataclass
class Week:
    """One calendar week of the plan."""

    index: int
    start: date
    end: date
    capacity: float
    phase: str  # learn | final
    learning: dict[str, float] = field(default_factory=dict)
    revision: dict[str, float] = field(default_factory=dict)
    mocks: list[dict] = field(default_factory=list)
    targeted: dict[str, float] = field(default_factory=dict)
    practice: dict[str, list[str]] = field(default_factory=dict)
    finished: list[str] = field(default_factory=list)

    @property
    def planned(self) -> float:
        """Hours planned this week."""
        mock_hours = sum(m["hours"] for m in self.mocks)
        return sum(self.learning.values()) + sum(self.revision.values()) + sum(self.targeted.values()) + mock_hours


@dataclass
class Plan:
    """Allocation plus calendar plus the numbers behind them."""

    profile: Profile
    units: list[Unit]
    mastery_now: dict[str, float]
    hours: dict[str, float]
    lam: float
    weeks: list[Week]
    notes: list[str]

    @property
    def projected_mastery(self) -> dict[str, float]:
        """Mastery after the planned learning hours (revision keeps it from decaying)."""
        return {u.id: mastery_after(self.mastery_now[u.id], self.hours[u.id], time_constant(u)) for u in self.units}

    def secured(self, after: bool) -> float:
        """Model estimate of marks secured now or after the plan."""
        return expected_secured(self.units, self.mastery_now, self.hours if after else None)


def round_hours(value: float) -> float:
    """Round to the nearest HOUR_STEP."""
    return round(value / HOUR_STEP) * HOUR_STEP


def round_down(value: float) -> float:
    """Round down to a whole number of HOUR_STEP blocks."""
    return math.floor(value / HOUR_STEP + EPS) * HOUR_STEP


def build_weeks(profile: Profile) -> list[Week]:
    """Calendar weeks from start date to the day before the exam, with capacities."""
    weeks, cursor, index = [], profile.start_date, 0
    last_day = profile.exam_date - timedelta(days=1)
    while cursor <= last_day:
        end = min(cursor + timedelta(days=DAYS_PER_WEEK - 1), last_day)
        days = (end - cursor).days + 1
        capacity = profile.hours_per_day * days * profile.study_days_per_week / DAYS_PER_WEEK
        weeks.append(Week(index, cursor, end, round(capacity, 2), "learn"))
        cursor, index = end + timedelta(days=1), index + 1
    final = min(profile.final_weeks, max(1, len(weeks) // 4))
    for week in weeks[-final:]:
        week.phase = "final"
    return weeks


def learning_order(units: list[Unit], hours: dict[str, float], mastery: dict[str, float]) -> list[Unit]:
    """Funded units in a prerequisite-respecting order, best marks-per-hour first."""
    funded = {u.id: u for u in units if hours[u.id] > EPS}
    priority = {uid: marginal_value(u, mastery[uid]) for uid, u in funded.items()}
    done: set[str] = set()
    order: list[Unit] = []
    while len(order) < len(funded):
        ready = [
            u for uid, u in funded.items()
            if uid not in done and all(p in done or p not in funded for p in u.prereqs)
        ]
        if not ready:  # a prerequisite cycle in the curation file: fall back to priority
            ready = [u for uid, u in funded.items() if uid not in done]
        best = max(ready, key=lambda u: priority[u.id])
        order.append(best)
        done.add(best.id)
    return order


def make_plan(units: list[Unit], mastery: dict[str, float], profile: Profile, notes: list[str] | None = None) -> Plan:
    """Allocate hours and lay them out week by week."""
    notes = list(notes or [])
    weeks = build_weeks(profile)
    learn_weeks = [w for w in weeks if w.phase == "learn"]
    final_weeks = [w for w in weeks if w.phase == "final"]
    budget = sum(w.capacity for w in learn_weeks) / (1 + REVISION_SHARE)
    raw_hours, lam = allocate(units, mastery, budget)
    hours = {uid: round_hours(h) for uid, h in raw_hours.items()}
    by_id = {u.id: u for u in units}

    queue = learning_order(units, hours, mastery)
    remaining = {u.id: hours[u.id] for u in queue}
    finished: set[str] = set()
    revision_due: dict[int, dict[str, float]] = defaultdict(dict)
    final_revision: dict[str, float] = defaultdict(float)
    active: list[str] = []

    def can_start(unit: Unit) -> bool:
        return all(p in finished or p not in remaining for p in unit.prereqs)

    def refill() -> None:
        while len(active) < PARALLEL_UNITS:
            sections = {by_id[a].section_id for a in active}
            ready = [u for u in queue if u.id not in finished and u.id not in active and can_start(u)]
            if not ready:
                return
            fresh = [u for u in ready if u.section_id not in sections]
            active.append((fresh or ready)[0].id)

    def finish(unit_id: str, week: Week) -> None:
        finished.add(unit_id)
        active.remove(unit_id)
        week.finished.append(unit_id)
        reserved = set(profile.reserve_papers_for_mocks)
        week.practice[unit_id] = [q for q in by_id[unit_id].questions if int(q[2:6]) not in reserved][:PYQ_PER_UNIT]
        each = max(HOUR_STEP, round_hours(REVISION_SHARE * hours[unit_id] / len(REVISION_OFFSETS_WEEKS)))
        for offset in REVISION_OFFSETS_WEEKS:
            target = week.index + offset
            if target < len(weeks) and weeks[target].phase == "learn":
                revision_due[target][unit_id] = revision_due[target].get(unit_id, 0.0) + each
            else:
                final_revision[unit_id] += each

    def study(week: Week, free: float) -> float:
        """Spend up to `free` hours on active units in HOUR_STEP blocks; return hours left unused."""
        refill()
        while free >= HOUR_STEP - EPS and active:
            share = max(HOUR_STEP, round_down(free / len(active)))
            for unit_id in list(active):
                spend = min(share, remaining[unit_id], round_down(free))
                if spend < HOUR_STEP - EPS:
                    continue
                week.learning[unit_id] = week.learning.get(unit_id, 0.0) + spend
                remaining[unit_id] -= spend
                free -= spend
                if remaining[unit_id] <= EPS:
                    finish(unit_id, week)
            refill()
        return free

    carry: dict[str, float] = {}
    for week in learn_weeks:
        due = {**carry}
        for unit_id, h in revision_due.get(week.index, {}).items():
            due[unit_id] = due.get(unit_id, 0.0) + h
        room = round_down(MAX_REVISION_SHARE_OF_WEEK * week.capacity)
        carry = {}
        for unit_id, h in due.items():
            take = round_down(min(h, room))
            if take > EPS:
                week.revision[unit_id] = take
                room -= take
            if h - take > EPS:
                carry[unit_id] = h - take
        study(week, week.capacity - sum(week.revision.values()))
    for unit_id, h in carry.items():
        final_revision[unit_id] += h

    leftover_learning = {uid: h for uid, h in remaining.items() if h > EPS}
    if leftover_learning:
        notes.append(f"{len(leftover_learning)} unit(s) spill into the mock phase: " + ", ".join(sorted(leftover_learning)))

    reserved_papers = [f"GATE DA {year} (official paper from this dataset)" for year in profile.reserve_papers_for_mocks]
    mock_names = iter(reserved_papers)
    projected = {u.id: mastery_after(mastery[u.id], hours[u.id], time_constant(u)) for u in units}
    for week in final_weeks:
        weeks_left = len(weeks) - week.index
        free = week.capacity
        for _ in range(MOCKS_BY_WEEKS_LEFT.get(weeks_left, 1)):
            if free < MOCK_TEST_HOURS + MOCK_REVIEW_HOURS - EPS:
                break
            name = next(mock_names, "Full-length mock test (external)")
            week.mocks.append({"name": name, "hours": MOCK_TEST_HOURS + MOCK_REVIEW_HOURS})
            free -= MOCK_TEST_HOURS + MOCK_REVIEW_HOURS
        free = study(week, free)
        if free > EPS:
            # Marks still at risk on each unit; revision owed from late finishes adds weight.
            at_risk = {u.id: u.expected_marks * (1 - projected[u.id]) + final_revision.get(u.id, 0.0) for u in units}
            focus = sorted(at_risk, key=lambda uid: -at_risk[uid])[:TARGETED_UNITS_PER_WEEK]
            total = sum(at_risk[uid] for uid in focus)
            shares = {uid: round_down(free * at_risk[uid] / total) for uid in focus}
            shares[focus[0]] += round_down(free - sum(shares.values()))  # blocks lost to rounding go to the top unit
            for unit_id in focus:
                share = shares[unit_id]
                if share >= HOUR_STEP:
                    week.targeted[unit_id] = share
                    projected[unit_id] = mastery_after(projected[unit_id], share, time_constant(by_id[unit_id]))
                    final_revision[unit_id] = max(0.0, final_revision.get(unit_id, 0.0) - share)
    unused = [w for w in learn_weeks if w.capacity - w.planned > HOUR_STEP]
    if lam == 0.0 and unused:
        notes.append("There is more time than the plan needs; spare hours are left for extra practice and mocks.")
    return Plan(profile, units, mastery, hours, lam, weeks, notes)
