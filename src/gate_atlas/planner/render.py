"""Write a plan as Markdown (to read) and JSON (for the web atlas)."""

import json
from pathlib import Path

from gate_atlas.planner.allocate import EVIDENCE_STRENGTH, MASTERY_CAP, marginal_value
from gate_atlas.planner.profile import LEVELS
from gate_atlas.planner.schedule import (
    MOCK_REVIEW_HOURS,
    MOCK_TEST_HOURS,
    PARALLEL_UNITS,
    REVISION_OFFSETS_WEEKS,
    REVISION_SHARE,
    Plan,
)


def _h(hours: float) -> str:
    """Hours with at most one decimal."""
    return f"{hours:.1f}".rstrip("0").rstrip(".") + " h"


def _pct(value: float) -> str:
    """Share as a whole percentage."""
    return f"{100 * value:.0f}%"


def _date(value) -> str:
    """Date like 5 Oct 2026."""
    return f"{value.day} {value:%b %Y}"


def plan_document(plan: Plan) -> dict:
    """JSON-friendly plan."""
    projected = plan.projected_mastery
    units = {u.id: u for u in plan.units}
    return {
        "name": plan.profile.name,
        "exam_date": plan.profile.exam_date.isoformat(),
        "start_date": plan.profile.start_date.isoformat(),
        "hours_per_day": plan.profile.hours_per_day,
        "study_days_per_week": plan.profile.study_days_per_week,
        "lambda_marks_per_hour": round(plan.lam, 4),
        "expected_marks_secured": {"now": round(plan.secured(False), 1), "after_plan": round(plan.secured(True), 1)},
        "units": [
            {
                "id": u.id, "part": u.part, "section": u.section_title, "title": u.title,
                "expected_marks": round(u.expected_marks, 2), "base_hours": u.hours,
                "mastery_now": round(plan.mastery_now[u.id], 3), "planned_hours": plan.hours[u.id],
                "mastery_after": round(projected[u.id], 3),
                "first_hour_value": round(marginal_value(u, plan.mastery_now[u.id]), 4),
                "pyqs": u.questions,
            }
            for u in sorted(plan.units, key=lambda u: -plan.hours[u.id])
        ],
        "weeks": [
            {
                "index": w.index + 1, "start": w.start.isoformat(), "end": w.end.isoformat(), "phase": w.phase,
                "capacity_hours": w.capacity, "planned_hours": round(w.planned, 2),
                "learning": {k: round(v, 2) for k, v in w.learning.items()},
                "revision": {k: round(v, 2) for k, v in w.revision.items()},
                "targeted_revision": w.targeted,
                "mocks": w.mocks,
                "finished": w.finished,
                "practice": w.practice,
                "unit_titles": {uid: units[uid].title for uid in {*w.learning, *w.revision, *w.targeted, *w.practice}},
            }
            for w in plan.weeks
        ],
        "notes": plan.notes,
    }


def _unit_label(plan: Plan, unit_id: str) -> str:
    """'Distributions (PS)' style label."""
    unit = next(u for u in plan.units if u.id == unit_id)
    return f"{unit.title} ({unit.section_id.split('.')[1]})"


def plan_markdown(plan: Plan) -> str:
    """Readable plan with allocation, skips, weekly schedule and how to adapt it."""
    profile = plan.profile
    projected = plan.projected_mastery
    capacity = sum(w.capacity for w in plan.weeks)
    learning = sum(sum(w.learning.values()) for w in plan.weeks)
    revision = sum(sum(w.revision.values()) + sum(w.targeted.values()) for w in plan.weeks)
    mocks = sum(sum(m["hours"] for m in w.mocks) for w in plan.weeks)
    funded = sorted((u for u in plan.units if plan.hours[u.id] > 0), key=lambda u: -plan.hours[u.id])
    skipped = sorted((u for u in plan.units if plan.hours[u.id] == 0), key=lambda u: -marginal_value(u, plan.mastery_now[u.id]))
    lines = [
        f"# {profile.name}",
        "",
        f"Exam {_date(profile.exam_date)} · start {_date(profile.start_date)} · {_h(profile.hours_per_day)} a day, "
        f"{profile.study_days_per_week} days a week · {len(plan.weeks)} weeks · {capacity:.0f} h available.",
        "",
        "## Summary",
        "",
        f"- **Time split:** {learning:.0f} h learning, {revision:.0f} h revision, {mocks:.0f} h full-length mocks "
        f"({len([m for w in plan.weeks for m in w.mocks])} mocks with review).",
        f"- **Value of the last planned hour:** {plan.lam:.3f} marks. Every unit that gets learning time earns at least this "
        "much per hour, and every skipped unit earns less.",
        f"- **Model estimate of marks secured:** {plan.secured(False):.0f} of 100 now → {plan.secured(True):.0f} after the plan. "
        "This is the planner's yardstick for comparing plans, built from the learning-curve assumption. It is not a score "
        "prediction.",
        *[f"- {note}" for note in plan.notes],
        "",
        "## Where the hours go",
        "",
        "| Unit | Section | Expected marks / paper | Mastery now | Planned hours | Mastery after | PYQs |",
        "|---|---|---|---|---|---|---|",
    ]
    for unit in funded:
        lines.append(
            f"| {unit.title} | {unit.section_title} | {unit.expected_marks:.1f} | {_pct(plan.mastery_now[unit.id])} | "
            f"{_h(plan.hours[unit.id])} | {_pct(projected[unit.id])} | {len(unit.questions)} |"
        )
    if skipped:
        lines += [
            "",
            "## Strategic skips (no new learning time)",
            "",
            "These units would earn less than the last planned hour. They are listed in the order they should be added if "
            "more time appears. Revision in the mock phase still covers them when marks are at risk.",
            "",
            "| Unit | Section | Expected marks / paper | Mastery now | Marks per first hour |",
            "|---|---|---|---|---|",
        ]
        for unit in skipped:
            lines.append(
                f"| {unit.title} | {unit.section_title} | {unit.expected_marks:.1f} | {_pct(plan.mastery_now[unit.id])} | "
                f"{marginal_value(unit, plan.mastery_now[unit.id]):.3f} |"
            )
    lines += ["", "## Week by week", ""]
    for week in plan.weeks:
        phase = "mock phase" if week.phase == "final" else "learning"
        lines.append(f"### Week {week.index + 1} · {_date(week.start)} – {_date(week.end)} · {phase} · {_h(week.planned)} of {_h(week.capacity)}")
        lines.append("")
        if week.learning:
            lines.append("- **Learn:** " + ", ".join(f"{_unit_label(plan, uid)} {_h(h)}" for uid, h in week.learning.items()))
        if week.revision:
            lines.append("- **Revise:** " + ", ".join(f"{_unit_label(plan, uid)} {_h(h)}" for uid, h in week.revision.items()))
        for mock in week.mocks:
            lines.append(f"- **Mock:** {mock['name']}: {_h(MOCK_TEST_HOURS)} test + {_h(MOCK_REVIEW_HOURS)} review")
        if week.targeted:
            lines.append("- **Targeted revision:** " + ", ".join(f"{_unit_label(plan, uid)} {_h(h)}" for uid, h in week.targeted.items()))
        for uid, questions in week.practice.items():
            if questions:
                lines.append(f"- **Finish {_unit_label(plan, uid)} with these PYQs:** " + ", ".join(questions))
        lines.append("")
    lines += [
        "## Make it adaptive",
        "",
        "Re-run the planner whenever something changes. It replans the remaining weeks from `start_date`:",
        "",
        "1. Set `start_date` to today.",
        "2. Log study done since the last run under `[[progress]]` (unit id and hours).",
        "3. Log each mock under `[[mocks]]`, with `[correct, attempted]` per section or unit.",
        "",
        "Mock results update mastery with a Bayesian (Beta) update: your rating counts like "
        f"{EVIDENCE_STRENGTH:g} answered questions, and each mock adds its real answers. A weak mock section therefore "
        "pulls hours towards itself in the next plan.",
        "",
        "## Assumptions",
        "",
        "- Expected marks per unit: the section's mean marks per paper (2024–2026) times the unit's share of the section, "
        "smoothed towards the unit's syllabus breadth (Dirichlet-multinomial, alpha = 10 marks). In a leave-one-paper-out "
        "backtest this beat the plain mean and the Phase 3 item forecast.",
        "- Learning curve: mastery = 1 − (1 − m₀)·e^(−h/T), with T = half the unit's base hours in "
        f"`data/curation/study_hours.toml`. Learning stops at {_pct(MASTERY_CAP)} mastery.",
        "- Ratings map to mastery: " + ", ".join(f"{k} {v:g}" for k, v in LEVELS.items()) + ".",
        f"- Revision: {_pct(REVISION_SHARE)} of each unit's learning hours, in weeks +{', +'.join(map(str, REVISION_OFFSETS_WEEKS))} "
        f"after it is finished. At most {PARALLEL_UNITS} units are learned at once. Papers reserved for mocks are left out "
        "of practice lists.",
        "",
    ]
    return "\n".join(lines)


def write_plan(plan: Plan, out_dir: Path) -> None:
    """Write plan.md and plan.json into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.md").write_text(plan_markdown(plan), encoding="utf-8")
    (out_dir / "plan.json").write_text(json.dumps(plan_document(plan), indent=2) + "\n", encoding="utf-8")
