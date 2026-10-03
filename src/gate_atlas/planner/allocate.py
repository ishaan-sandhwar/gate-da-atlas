"""Mastery estimates and the hour allocation that maximises expected marks.

Learning curve of a unit with base hours H (hours from scratch to ~86% mastery):
    m(h) = 1 - (1 - m0) * exp(-h / T),   T = H / 2
so each extra hour helps less than the one before (diminishing returns).

Allocation problem for a learning budget B:
    maximise   sum_u  w_u * m_u(h_u)          w_u = expected marks of unit u in a paper
    subject to sum_u  h_u = B,  0 <= h_u <= cap_u
Every term is concave, so the KKT conditions are necessary and sufficient. With multiplier
lambda on the budget, stationarity gives
    w_u (1 - m0_u) e^(-h_u / T_u) / T_u = lambda           for units with 0 < h_u < cap_u
and complementary slackness leaves h_u = 0 where even the first hour is worth less than
lambda. Hence h_u(lambda) = clip(T_u * ln(w_u (1 - m0_u) / (lambda T_u)), 0, cap_u), and
lambda is found by bisection so that the hours add up to B. lambda is the value, in marks, of
the last hour planned: every funded unit earns at least that much per hour.

Mastery updates: a self-rating is a Beta prior worth EVIDENCE_STRENGTH questions; logged study
hours move it along the learning curve; mock results add [correct, attempted] as Beta counts.
"""

import math

from gate_atlas.planner.profile import Profile
from gate_atlas.planner.units import Unit

TIME_CONSTANT_FRACTION = 0.5  # T = H / 2 because 1 - e^-2 = 0.86
MASTERY_CAP = 0.95  # stop planning hours once the curve is this close to full mastery
EVIDENCE_STRENGTH = 8.0  # a self-rating counts like 8 answered questions
BISECTION_STEPS = 200


def time_constant(unit: Unit) -> float:
    """Learning-curve time constant T in hours."""
    return unit.hours * TIME_CONSTANT_FRACTION


def mastery_after(start: float, hours: float, time_constant_hours: float) -> float:
    """Mastery after studying `hours` from `start` on the exponential learning curve."""
    return 1 - (1 - start) * math.exp(-hours / time_constant_hours)


def hours_cap(start: float, time_constant_hours: float) -> float:
    """Hours needed to reach MASTERY_CAP from `start` (zero if already there)."""
    if start >= MASTERY_CAP:
        return 0.0
    return time_constant_hours * math.log((1 - start) / (1 - MASTERY_CAP))


def marginal_value(unit: Unit, start: float, hours: float = 0.0) -> float:
    """Expected marks gained per extra hour after `hours` of study."""
    tau = time_constant(unit)
    return unit.expected_marks * (1 - start) * math.exp(-hours / tau) / tau


def estimate_mastery(units: list[Unit], profile: Profile) -> tuple[dict[str, float], list[str]]:
    """Current mastery of every unit: rating prior, then study progress, then mock evidence."""
    by_id = {u.id: u for u in units}
    alpha, beta = {}, {}
    for unit in units:
        prior = profile.mastery(unit.id, unit.section_id, unit.part)
        alpha[unit.id], beta[unit.id] = prior * EVIDENCE_STRENGTH, (1 - prior) * EVIDENCE_STRENGTH
    notes = []
    for entry in profile.progress:
        unit = by_id.get(entry["unit"])
        if unit is None:
            raise ValueError(f"progress refers to unknown unit {entry['unit']!r}")
        strength = alpha[unit.id] + beta[unit.id]
        mean = mastery_after(alpha[unit.id] / strength, float(entry["hours"]), time_constant(unit))
        alpha[unit.id], beta[unit.id] = mean * strength, (1 - mean) * strength
        notes.append(f"{unit.id}: +{entry['hours']}h studied")
    for mock in sorted(profile.mocks, key=lambda m: str(m.get("date", ""))):
        for key, (correct, attempted) in mock["results"].items():
            if not 0 <= correct <= attempted:
                raise ValueError(f"mock result for {key} must satisfy 0 <= correct <= attempted")
            targets = [by_id[key]] if key in by_id else [u for u in units if u.section_id == key]
            if not targets:
                raise ValueError(f"mock result key {key!r} is neither a unit nor a section id")
            total = sum(u.expected_marks for u in targets)
            for unit in targets:
                share = unit.expected_marks / total if total else 1 / len(targets)
                alpha[unit.id] += share * correct
                beta[unit.id] += share * (attempted - correct)
            notes.append(f"{mock.get('date', 'mock')}: {key} {correct}/{attempted}")
    return {uid: alpha[uid] / (alpha[uid] + beta[uid]) for uid in alpha}, notes


def allocate(units: list[Unit], mastery: dict[str, float], budget: float) -> tuple[dict[str, float], float]:
    """Hours per unit maximising expected marks for a learning budget; returns (hours, lambda)."""
    caps = {u.id: hours_cap(mastery[u.id], time_constant(u)) for u in units}
    if budget <= 0:
        return {u.id: 0.0 for u in units}, math.inf
    if sum(caps.values()) <= budget:
        return caps, 0.0  # time for everything: the budget constraint is slack

    def hours_at(lam: float) -> dict[str, float]:
        out = {}
        for unit in units:
            first_hour = marginal_value(unit, mastery[unit.id])
            raw = time_constant(unit) * math.log(first_hour / lam) if first_hour > lam else 0.0
            out[unit.id] = min(max(raw, 0.0), caps[unit.id])
        return out

    low = 1e-12
    high = max(marginal_value(u, mastery[u.id]) for u in units)
    for _ in range(BISECTION_STEPS):  # total hours falls as lambda rises
        middle = math.sqrt(low * high)
        if sum(hours_at(middle).values()) > budget:
            low = middle
        else:
            high = middle
    return hours_at(high), high


def expected_secured(units: list[Unit], mastery: dict[str, float], hours: dict[str, float] | None = None) -> float:
    """Model estimate of marks secured: sum of expected marks times mastery (after `hours`)."""
    total = 0.0
    for unit in units:
        level = mastery[unit.id]
        if hours:
            level = mastery_after(level, hours.get(unit.id, 0.0), time_constant(unit))
        total += unit.expected_marks * level
    return total
