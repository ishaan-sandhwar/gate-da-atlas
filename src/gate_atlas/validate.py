"""Invariants every build must satisfy, plus a human-readable validation report."""

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from gate_atlas.answer_key import KeyEntry
from gate_atlas.config import (
    EXPECTED_MARKS_PER_PAPER,
    EXPECTED_QUESTIONS_PER_PAPER,
    EXPECTED_SECTION_PATTERN,
    PROCESSED_DIR,
    ROOT_DIR,
)
from gate_atlas.dataset import REVIEW_REASONS
from gate_atlas.fetch import verify_raw_files
from gate_atlas.paper import ParsedPaper

GA_LAST_QUESTION = 10


@dataclass
class Check:
    """Outcome of one validation rule."""

    name: str
    passed: bool
    detail: str = ""
    level: str = "error"  # error = build fails; warning = reported only


def check_year(year: int, records: list[dict], paper: ParsedPaper, keys: list[KeyEntry]) -> list[Check]:
    """Validate one paper year against the official 65-question / 100-mark pattern."""
    expected_numbers = list(range(1, EXPECTED_QUESTIONS_PER_PAPER + 1))
    key_by_number = {entry.number: entry for entry in keys}
    checks = [
        Check(f"{year}: {EXPECTED_QUESTIONS_PER_PAPER} question numbers found in order",
              paper.anchor_numbers == expected_numbers, f"found {len(paper.anchor_numbers)}"),
        Check(f"{year}: answer key has one row per question",
              sorted(key_by_number) == expected_numbers and len(keys) == EXPECTED_QUESTIONS_PER_PAPER,
              f"{len(keys)} rows"),
    ]

    total = sum(entry.marks for entry in keys)
    checks.append(Check(f"{year}: total marks = {EXPECTED_MARKS_PER_PAPER}", total == EXPECTED_MARKS_PER_PAPER, f"total {total}"))
    for section, pattern in EXPECTED_SECTION_PATTERN.items():
        found = dict(Counter(entry.marks for entry in keys if entry.section == section))
        checks.append(Check(f"{year}: {section} has {pattern} (marks: count)", found == pattern, f"found {found}"))

    misplaced = [e.number for e in keys if e.section != ("GA" if e.number <= GA_LAST_QUESTION else "DA")]
    checks.append(Check(f"{year}: Q1-Q{GA_LAST_QUESTION} are GA and the rest DA", not misplaced, f"misplaced {misplaced}"))

    header_conflicts = [
        n for n, marks in paper.header_marks.items() if n in key_by_number and key_by_number[n].marks != marks
    ]
    checks.append(Check(
        f"{year}: mark headings printed in the paper agree with the key", not header_conflicts,
        f"headings cover {len(paper.header_marks)}/{EXPECTED_QUESTIONS_PER_PAPER} questions; conflicts {header_conflicts}",
    ))

    malformed = [e.number for e in keys if not _answer_well_formed(e)]
    checks.append(Check(f"{year}: every key answer is well-formed for its type", not malformed, f"malformed {malformed}"))

    outside_labels = [
        r["number"] for r in records
        if r["answer"] and r["answer"]["kind"] == "options" and r["options"]
        and not set(r["answer"]["options"]) <= set(r["options"])
    ]
    checks.append(Check(f"{year}: keyed options exist in the parsed question", not outside_labels, f"questions {outside_labels}"))

    missing_crops = [r["id"] for r in records if not (ROOT_DIR / r["crop"]).exists()]
    checks.append(Check(f"{year}: every question has a crop image", not missing_crops, f"missing {missing_crops}"))

    mta = [e.number for e in keys if e.is_mta]
    checks.append(Check(f"{year}: questions with marks-to-all (MTA)", True, f"{mta or 'none'}", level="warning"))
    return checks


def _answer_well_formed(entry: KeyEntry) -> bool:
    """True when the key's answer matches its question type."""
    if entry.is_mta:
        return True
    if entry.qtype == "MCQ":
        return len(entry.options) == 1 and entry.options[0] in "ABCD"
    if entry.qtype == "MSQ":
        return 1 <= len(entry.options) <= 4 and set(entry.options) <= set("ABCD")
    numeric = entry.numeric_range
    return numeric is not None and numeric[0] <= numeric[1]


def check_global(records: list[dict], syllabus: dict) -> list[Check]:
    """Checks that span all years: provenance, ids and syllabus editions."""
    raw_problems = verify_raw_files()
    ids = [r["id"] for r in records]
    checks = [
        Check("raw PDFs match MANIFEST.json checksums", not raw_problems, "; ".join(raw_problems)),
        Check("question ids are unique", len(ids) == len(set(ids)), f"{len(ids)} ids"),
        Check("syllabus curation covers every official phrase (checked during build)", True,
              f"{sum(len(s['items']) for p in syllabus['papers'].values() for s in p['sections'])} items"),
    ]
    for code, paper in syllabus["papers"].items():
        changed = [year for year, report in paper["editions"].items() if not report["identical_to_canonical"]]
        checks.append(Check(
            f"{code} syllabus identical across editions {', '.join(paper['editions'])}", not changed,
            f"changed editions: {changed or 'none'}", level="warning",
        ))
    return checks


def summarize(records: list[dict]) -> dict:
    """Counts by year, type, section, status and review reason."""
    summary = {}
    for year in sorted({r["year"] for r in records}):
        rows = [r for r in records if r["year"] == year]
        summary[str(year)] = {
            "questions": len(rows),
            "marks": sum(r["marks"] or 0 for r in rows),
            "by_type": dict(Counter(r["type"] for r in rows)),
            "by_section": dict(Counter(r["section"] for r in rows)),
            "clean": sum(r["status"] == "clean" for r in rows),
            "needs_review": sum(r["status"] == "needs_review" for r in rows),
            "review_reasons": dict(Counter(reason for r in rows for reason in r["review_reasons"])),
        }
    return summary


def write_report(checks: list[Check], records: list[dict]) -> dict:
    """Write validation_report.json and VALIDATION.md; return the report."""
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "passed": all(c.passed for c in checks if c.level == "error"),
        "checks": [asdict(c) for c in checks],
        "summary": summarize(records),
    }
    (PROCESSED_DIR / "validation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (PROCESSED_DIR / "VALIDATION.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict) -> str:
    """Render the validation report as Markdown."""
    lines = [
        "# Validation report",
        "",
        f"Generated by `python -m gate_atlas build` at {report['generated_at']}.",
        f"Overall: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for check in report["checks"]:
        result = "pass" if check["passed"] else ("FAIL" if check["level"] == "error" else "warn")
        if check["level"] == "warning" and check["passed"]:
            result = "info"
        lines.append(f"| {check['name']} | {result} | {check['detail']} |")
    lines += ["", "## Questions per year", "", "| Year | Qs | Marks | MCQ | MSQ | NAT | GA | DA | Clean | Needs review |", "|---|---|---|---|---|---|---|---|---|---|"]
    for year, row in report["summary"].items():
        types, sections = row["by_type"], row["by_section"]
        lines.append(
            f"| {year} | {row['questions']} | {row['marks']} | {types.get('MCQ', 0)} | {types.get('MSQ', 0)} | "
            f"{types.get('NAT', 0)} | {sections.get('GA', 0)} | {sections.get('DA', 0)} | {row['clean']} | {row['needs_review']} |"
        )
    lines += ["", "## Review reasons", "", "| Reason | Meaning | " + " | ".join(report["summary"]) + " |",
              "|---|---|" + "---|" * len(report["summary"])]
    for reason, meaning in REVIEW_REASONS.items():
        counts = [str(row["review_reasons"].get(reason, 0)) for row in report["summary"].values()]
        lines.append(f"| `{reason}` | {meaning} | " + " | ".join(counts) + " |")
    return "\n".join(lines) + "\n"
