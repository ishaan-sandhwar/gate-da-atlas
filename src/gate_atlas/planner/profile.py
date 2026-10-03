"""Planner input: a TOML profile with dates, hours, self-ratings and optional evidence.

Example (see examples/profile_gate2027.toml):

    name = "my-gate-2027"
    exam_date = "2027-02-06"
    start_date = "2026-10-05"          # optional; defaults to today
    hours_per_day = 3.0
    study_days_per_week = 6
    reserve_papers_for_mocks = [2026]  # keep these papers unseen for full-length mocks

    [ratings]                          # unit id > section id > part > default
    default = "basic"
    "DA.LA" = "good"
    "DA.PD:Python programming" = "strong"

    [[progress]]                       # hours already studied since the ratings were set
    unit = "DA.PS:Distributions"
    hours = 6

    [[mocks]]                          # results by section or unit: [correct, attempted]
    date = "2026-12-20"
    results = { "DA.PS" = [6, 10], "DA.LA:Matrices" = [2, 3] }
"""

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

LEVELS = {
    "not_started": 0.05,
    "weak": 0.2,
    "basic": 0.35,
    "okay": 0.5,
    "good": 0.7,
    "strong": 0.85,
}
DEFAULT_LEVEL = "basic"


@dataclass
class Profile:
    """Everything the planner needs from the student."""

    name: str
    exam_date: date
    start_date: date
    hours_per_day: float
    study_days_per_week: int = 6
    final_weeks: int = 4
    reserve_papers_for_mocks: list[int] = field(default_factory=lambda: [2026])
    ratings: dict[str, str] = field(default_factory=dict)
    progress: list[dict] = field(default_factory=list)
    mocks: list[dict] = field(default_factory=list)

    def mastery(self, unit_id: str, section_id: str, part: str) -> float:
        """Prior mastery of a unit from the most specific rating that applies."""
        for key in (unit_id, section_id, part, "default"):
            if key in self.ratings:
                level = self.ratings[key]
                if level not in LEVELS:
                    raise ValueError(f"rating {level!r} for {key} must be one of {sorted(LEVELS)}")
                return LEVELS[level]
        return LEVELS[DEFAULT_LEVEL]


def _as_date(value: object) -> date:
    """TOML dates load as date objects; strings are parsed as ISO dates."""
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def load_profile(path: Path, today: date | None = None) -> Profile:
    """Read and validate a profile TOML."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    profile = Profile(
        name=data.get("name", path.stem),
        exam_date=_as_date(data["exam_date"]),
        start_date=_as_date(data.get("start_date", today or date.today())),
        hours_per_day=float(data["hours_per_day"]),
        study_days_per_week=int(data.get("study_days_per_week", 6)),
        final_weeks=int(data.get("final_weeks", 4)),
        reserve_papers_for_mocks=list(data.get("reserve_papers_for_mocks", [2026])),
        ratings={str(k): str(v) for k, v in data.get("ratings", {}).items()},
        progress=list(data.get("progress", [])),
        mocks=list(data.get("mocks", [])),
    )
    if profile.exam_date <= profile.start_date:
        raise ValueError("exam_date must be after start_date")
    if not 0 < profile.hours_per_day <= 16 or not 1 <= profile.study_days_per_week <= 7:
        raise ValueError("hours_per_day must be in (0, 16] and study_days_per_week in [1, 7]")
    return profile
