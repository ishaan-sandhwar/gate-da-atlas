"""Weightage of syllabus sections, clusters and items across the papers.

Each question's marks are attributed to syllabus items in two ways:
* primary - all marks go to the primary item (simple, the default view);
* shared  - the primary item gets weight 1 and each secondary item 0.5, normalised to 1,
            so a question that needs several concepts spreads its marks over them.
Both schemes conserve marks: every year still sums to 85 DA + 15 GA.
"""

from collections import Counter, defaultdict
from itertools import combinations

import numpy as np

from gate_atlas.config import PAPER_YEARS

SECONDARY_WEIGHT = 0.5
SCHEMES = ("primary", "shared")
TREND_THRESHOLD = 2.0  # marks per year needed to call a section rising or falling
MIXED_RANGE = 4.0  # marks between best and worst year that make a non-monotonic series "mixed"


def attribution(tags: dict, scheme: str) -> dict[str, float]:
    """Weights of the items a question's marks are attributed to (they sum to 1)."""
    if scheme == "primary" or not tags["secondary"]:
        return {tags["primary"]: 1.0}
    raw = {tags["primary"]: 1.0, **{item: SECONDARY_WEIGHT for item in tags["secondary"]}}
    total = sum(raw.values())
    return {item: weight / total for item, weight in raw.items()}


def trend_label(values: list[float]) -> tuple[float, str]:
    """Least-squares slope (marks per year) and a label.

    rising/falling need both a slope of at least TREND_THRESHOLD and a monotonic series;
    a series that jumps up and down by at least MIXED_RANGE marks is "mixed"; else "stable".
    With three papers these labels describe the past, not a forecast.
    """
    slope = float(np.polyfit(PAPER_YEARS, values, 1)[0])
    steps = np.diff(values)
    if slope >= TREND_THRESHOLD and (steps >= 0).all():
        return slope, "rising"
    if slope <= -TREND_THRESHOLD and (steps <= 0).all():
        return slope, "falling"
    if max(values) - min(values) >= MIXED_RANGE:
        return slope, "mixed"
    return slope, "stable"


def aggregate(records: list[dict], items: list[dict], scheme: str) -> dict[str, dict]:
    """Marks and question counts per item and year under one attribution scheme."""
    table = {i["id"]: {"marks": defaultdict(float), "questions": defaultdict(float)} for i in items}
    for record in records:
        for item_id, weight in attribution(record["syllabus_tags"], scheme).items():
            table[item_id]["marks"][record["year"]] += weight * record["marks"]
            table[item_id]["questions"][record["year"]] += weight
    return table


def group_rows(items: list[dict], table: dict[str, dict], key: str) -> list[dict]:
    """Roll item totals up to sections or clusters, with per-year values and a trend."""
    groups: dict[tuple, dict] = {}
    for item in items:
        group_id = item["section_id"] if key == "section" else f"{item['section_id']}:{item['cluster']}"
        title = item["section_title"] if key == "section" else item["cluster"]
        entry = groups.setdefault(
            (item["part"], group_id),
            {"part": item["part"], "id": group_id, "section_id": item["section_id"], "title": title,
             "items": 0, "marks": Counter(), "questions": Counter()},
        )
        entry["items"] += 1
        for year in PAPER_YEARS:
            entry["marks"][year] += table[item["id"]]["marks"][year]
            entry["questions"][year] += table[item["id"]]["questions"][year]

    part_marks = {"DA": 85.0, "GA": 15.0}
    rows = []
    for entry in groups.values():
        marks = [round(entry["marks"][y], 3) for y in PAPER_YEARS]
        slope, label = trend_label(marks)
        rows.append({
            "part": entry["part"], "id": entry["id"], "section_id": entry["section_id"], "title": entry["title"],
            "items": entry["items"],
            **{f"marks_{y}": m for y, m in zip(PAPER_YEARS, marks)},
            **{f"questions_{y}": round(entry["questions"][y], 3) for y in PAPER_YEARS},
            "marks_total": round(sum(marks), 3),
            "marks_mean": round(sum(marks) / len(marks), 3),
            "marks_min": min(marks), "marks_max": max(marks),
            "share_of_part": round(sum(marks) / (len(marks) * part_marks[entry["part"]]), 4),
            "trend_marks_per_year": round(slope, 2), "trend": label,
        })
    return sorted(rows, key=lambda r: (r["part"] != "DA", -r["marks_total"]))


def item_rows(records: list[dict], items: list[dict], primary: dict, shared: dict) -> list[dict]:
    """One row per syllabus item: per-year primary marks, secondary use and coverage status."""
    secondary_uses = Counter()
    touched_years = defaultdict(set)
    for record in records:
        tags = record["syllabus_tags"]
        for item_id in tags["secondary"]:
            secondary_uses[item_id] += 1
        for item_id in (tags["primary"], *tags["secondary"]):
            touched_years[item_id].add(record["year"])
    rows = []
    for item in items:
        p = primary[item["id"]]
        primary_questions = sum(p["questions"].values())
        years = sorted(touched_years[item["id"]])
        if primary_questions:
            status = "asked"
        elif years:
            status = "only_secondary"
        else:
            status = "never_asked"
        rows.append({
            "part": item["part"], "section_id": item["section_id"], "section_title": item["section_title"],
            "cluster": item["cluster"], "item_id": item["id"], "label": item["label"],
            **{f"primary_marks_{y}": round(p["marks"][y], 3) for y in PAPER_YEARS},
            "primary_questions": round(primary_questions, 3),
            "primary_marks_total": round(sum(p["marks"].values()), 3),
            "shared_marks_total": round(sum(shared[item["id"]]["marks"].values()), 3),
            "secondary_uses": secondary_uses[item["id"]],
            "years_touched": len(years),
            "first_year": years[0] if years else None,
            "last_year": years[-1] if years else None,
            "status": status,
        })
    return rows


def type_mix(records: list[dict]) -> list[dict]:
    """Question count and marks by section, question type and mark value."""
    counts = Counter()
    for record in records:
        section = record["syllabus_tags"]["primary"].rsplit(".", 1)[0]
        counts[(record["section"], section, record["type"], record["marks"])] += 1
    return [
        {"part": part, "section_id": section, "type": qtype, "marks_each": marks, "questions": n, "marks": n * marks}
        for (part, section, qtype, marks), n in sorted(counts.items())
    ]


def cooccurrence(records: list[dict], items: list[dict]) -> list[dict]:
    """Pairs of items tagged on the same question, with how often they co-occur."""
    labels = {i["id"]: i["label"] for i in items}
    pairs = Counter()
    for record in records:
        tags = record["syllabus_tags"]
        for first, second in combinations(sorted({tags["primary"], *tags["secondary"]}), 2):
            pairs[(first, second)] += 1
    rows = [
        {"item_a": a, "label_a": labels[a], "item_b": b, "label_b": labels[b], "questions": n,
         "cross_section": a.rsplit(".", 1)[0] != b.rsplit(".", 1)[0]}
        for (a, b), n in pairs.items()
    ]
    return sorted(rows, key=lambda r: (-r["questions"], r["item_a"], r["item_b"]))


def yearly_coverage(records: list[dict], items: list[dict]) -> list[dict]:
    """Share of syllabus items touched (primary or secondary) in each paper."""
    rows = []
    for part in ("DA", "GA"):
        total = sum(i["part"] == part for i in items)
        for year in PAPER_YEARS:
            touched = {
                item for r in records if r["year"] == year and r["section"] == part
                for item in (r["syllabus_tags"]["primary"], *r["syllabus_tags"]["secondary"])
            }
            rows.append({"part": part, "year": year, "items_touched": len(touched), "items_total": total,
                         "share": round(len(touched) / total, 4)})
    return rows


def tag_sensitivity(records: list[dict], alternative: dict[str, dict]) -> dict:
    """Largest change in section marks per year if another tagger's primaries replaced the reference."""
    reference, swapped = Counter(), Counter()
    for record in records:
        guess = alternative.get(record["id"])
        if guess is None:
            continue
        reference[(record["year"], record["syllabus_tags"]["primary"].rsplit(".", 1)[0])] += record["marks"]
        swapped[(record["year"], guess["primary"].rsplit(".", 1)[0])] += record["marks"]
    keys = set(reference) | set(swapped)
    differences = {f"{year} {section}": swapped[(year, section)] - reference[(year, section)] for year, section in keys}
    largest = max(differences.items(), key=lambda kv: abs(kv[1])) if differences else ("", 0)
    return {
        "max_abs_change_marks": abs(largest[1]),
        "where": largest[0],
        "mean_abs_change_marks": round(sum(abs(v) for v in differences.values()) / max(len(differences), 1), 2),
    }
