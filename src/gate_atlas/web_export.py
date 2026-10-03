"""Export the dataset, analysis and planner inputs as static JSON for the web atlas.

Writes (generated, git-ignored):
* web/src/data/atlas.json     - syllabus, per-item/section statistics, forecast, planner units,
                                provenance, validation and tagging summaries;
* web/src/data/questions.json - every question with its tags, answer, crop path and the five most
                                similar questions (cosine similarity of the bge-small embeddings);
* web/public/crops/<year>/*.png - the official question crops.
Also writes golden planner fixtures for the TypeScript port's parity tests.
"""

import json
import logging
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from gate_atlas.config import CROPS_DIR, MANIFEST_PATH, PAPER_YEARS, PROCESSED_DIR, ROOT_DIR
from gate_atlas.dataset import load_questions
from gate_atlas.planner.allocate import estimate_mastery
from gate_atlas.planner.profile import Profile, load_profile
from gate_atlas.planner.schedule import make_plan
from gate_atlas.planner.units import Unit, load_units
from gate_atlas.tagging.text import load_items

log = logging.getLogger(__name__)

WEB_DIR = ROOT_DIR / "web"
PUBLIC_DIR = WEB_DIR / "public"
FIXTURES_DIR = WEB_DIR / "src" / "planner" / "fixtures"
TAGGING_DIR = PROCESSED_DIR / "tagging"
ANALYSIS_PATH = PROCESSED_DIR / "analysis" / "analysis.json"
SIMILAR_COUNT = 5


def similar_questions(records: list[dict]) -> dict[str, list[list]]:
    """Five most similar questions of the same part, by cosine similarity of embeddings."""
    vectors = np.load(TAGGING_DIR / "question_embeddings.npy")
    ids = json.loads((TAGGING_DIR / "question_embeddings_ids.json").read_text(encoding="utf-8"))
    index = {qid: k for k, qid in enumerate(ids)}
    part = {r["id"]: r["section"] for r in records}
    similarity = vectors @ vectors.T  # rows are unit vectors
    out = {}
    for qid in ids:
        row = similarity[index[qid]]
        ranked = [ids[k] for k in np.argsort(-row) if ids[k] != qid and part[ids[k]] == part[qid]]
        out[qid] = [[other, round(float(row[index[other]]), 3)] for other in ranked[:SIMILAR_COUNT]]
    return out


def _load_jsonl(path: Path) -> dict[str, dict]:
    """JSON lines keyed by id (empty when the file is absent)."""
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["id"]: row for row in rows}


def question_rows(records: list[dict]) -> list[dict]:
    """Compact question records for the browser."""
    similar = similar_questions(records)
    llm_full = _load_jsonl(TAGGING_DIR / "llm_openai_gpt-oss-120b_full.jsonl")
    llm_hybrid = _load_jsonl(TAGGING_DIR / "llm_openai_gpt-oss-120b_hybrid.jsonl")
    rows = []
    for record in records:
        rows.append({
            "id": record["id"], "year": record["year"], "number": record["number"], "part": record["section"],
            "marks": record["marks"], "type": record["type"], "negative": record["negative_marks"],
            "answer": record["answer"], "stem": record["stem"], "options": record["options"],
            "status": record["status"], "reasons": record["review_reasons"], "tags": record["syllabus_tags"],
            "crop": record["crop"].replace("data/processed/", ""), "pages": record["source"]["pages"],
            "similar": similar.get(record["id"], []),
            "ai": {
                "llm": llm_full.get(record["id"], {}).get("primary"),
                "hybrid": llm_hybrid.get(record["id"], {}).get("primary"),
            },
        })
    return rows


def atlas_document(records: list[dict], items: list[dict], units: list[Unit]) -> dict:
    """Everything except the questions: syllabus, statistics, forecast, planner units, provenance."""
    analysis = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
    syllabus = json.loads((PROCESSED_DIR / "syllabus.json").read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    validation = json.loads((PROCESSED_DIR / "validation_report.json").read_text(encoding="utf-8"))
    evaluation = json.loads((TAGGING_DIR / "evaluation.json").read_text(encoding="utf-8"))

    primary_questions: dict[str, list[str]] = {i["id"]: [] for i in items}
    secondary_questions: dict[str, list[str]] = {i["id"]: [] for i in items}
    for record in sorted(records, key=lambda r: (-r["year"], r["number"])):
        tags = record["syllabus_tags"]
        primary_questions[tags["primary"]].append(record["id"])
        for item_id in tags["secondary"]:
            secondary_questions[item_id].append(record["id"])

    item_stats = {}
    for row in analysis["items"]:
        item_stats[row["item_id"]] = {
            "marks": [row[f"primary_marks_{y}"] for y in PAPER_YEARS],
            "shared_marks": row["shared_marks_total"],
            "secondary_uses": row["secondary_uses"],
            "status": row["status"],
            "forecast": {
                "expected_marks": row["forecast_expected_marks"], "p_asked": row["forecast_p_asked"],
                "rate_low": row["forecast_rate_low"], "rate_high": row["forecast_rate_high"],
                "expected_questions": row["forecast_expected_questions"],
            },
            "questions": primary_questions[row["item_id"]],
            "secondary_questions": secondary_questions[row["item_id"]],
        }

    parts = []
    for code, paper in syllabus["papers"].items():
        parts.append({
            "code": code, "title": paper["title"],
            "sections": [
                {"id": s["id"], "title": s["title"], "official_text": s["official_text"],
                 "items": [{k: i[k] for k in ("id", "label", "cluster", "official_text", "note")} for i in s["items"]]}
                for s in paper["sections"]
            ],
        })

    methods = {
        name: {"label": m["method"], "n": m["n"], **{k: m["subsets"]["all"][k] for k in ("primary", "primary_in_reference_items", "section")}}
        for name, m in evaluation["methods"].items()
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "years": list(PAPER_YEARS),
        "syllabus": parts,
        "items": item_stats,
        "sections": analysis["sections"],
        "clusters": analysis["clusters"]["primary"],
        "type_mix": analysis["type_mix"],
        "coverage": analysis["coverage"],
        "cooccurrence": analysis["cooccurrence"][:40],
        "forecast": {"prior": analysis["forecast_prior"], "backtest": analysis["backtest"]},
        "tag_sensitivity": analysis["tag_sensitivity"],
        "units": [_unit_json(u) for u in units],
        "tagging": {"methods": methods, "paired_tests": evaluation.get("paired_tests", {})},
        "validation": {"passed": validation["passed"], "summary": validation["summary"],
                       "checks": [{k: c[k] for k in ("name", "passed", "detail", "level")} for c in validation["checks"]]},
        "sources": [
            {"filename": d["filename"], "kind": d["kind"], "year": d["year"], "subject": d["subject"],
             "url": d["primary_url"], "sha256": d["sha256"], "mirrors": sum(c["ok"] for c in d["url_checks"])}
            for d in manifest["documents"]
        ],
    }


def _unit_json(unit: Unit) -> dict:
    """Planner unit as JSON (full float precision so the TypeScript port matches)."""
    return {
        "id": unit.id, "part": unit.part, "section_id": unit.section_id, "section_title": unit.section_title,
        "title": unit.title, "items": unit.items, "hours": unit.hours, "prereqs": unit.prereqs,
        "expected_marks": unit.expected_marks, "questions": unit.questions,
    }


def _profile_json(profile: Profile) -> dict:
    """Profile as JSON (dates as ISO strings)."""
    return {
        "name": profile.name, "exam_date": profile.exam_date.isoformat(), "start_date": profile.start_date.isoformat(),
        "hours_per_day": profile.hours_per_day, "study_days_per_week": profile.study_days_per_week,
        "final_weeks": profile.final_weeks, "reserve_papers_for_mocks": profile.reserve_papers_for_mocks,
        "ratings": profile.ratings, "progress": profile.progress, "mocks": profile.mocks,
    }


def planner_fixtures(units: list[Unit]) -> list[dict]:
    """Python plans for a few profiles; the TypeScript planner must reproduce them."""
    example = load_profile(ROOT_DIR / "examples" / "profile_gate2027.toml")
    variants = [
        example,
        Profile(name="weak, 2 h/day", exam_date=date(2027, 2, 13), start_date=date(2026, 11, 2), hours_per_day=2.0,
                study_days_per_week=5, ratings={"default": "weak", "GA": "okay"}),
        Profile(name="after a mock", exam_date=date(2027, 2, 6), start_date=date(2026, 12, 21), hours_per_day=4.0,
                study_days_per_week=6, reserve_papers_for_mocks=[2025, 2026],
                ratings={"default": "basic", "DA.LA": "good", "DA.PD:Python programming": "strong"},
                progress=[{"unit": "DA.DB:Relational databases", "hours": 20}],
                mocks=[{"date": "2026-12-20", "results": {"DA.PS": [3, 10], "DA.DB": [8, 10]}}]),
        Profile(name="lots of time", exam_date=date(2027, 2, 6), start_date=date(2026, 6, 1), hours_per_day=6.0,
                study_days_per_week=7, ratings={"default": "okay"}),
    ]
    fixtures = []
    for profile in variants:
        mastery, notes = estimate_mastery(units, profile)
        plan = make_plan(units, mastery, profile, notes)
        fixtures.append({
            "profile": _profile_json(profile),
            "mastery": mastery,
            "hours": plan.hours,
            "lambda": plan.lam,
            "weeks": [
                {"index": w.index, "start": w.start.isoformat(), "end": w.end.isoformat(), "capacity": w.capacity,
                 "phase": w.phase, "learning": w.learning, "revision": w.revision, "targeted": w.targeted,
                 "mocks": w.mocks, "practice": w.practice, "finished": w.finished}
                for w in plan.weeks
            ],
            "notes": plan.notes,
        })
    return fixtures


def export_web(out_dir: Path = PUBLIC_DIR) -> None:
    """Write atlas.json, questions.json, crops and planner fixtures."""
    records, items = load_questions(), load_items()
    units = load_units(records, items)
    data_dir = WEB_DIR / "src" / "data"  # imported by the app, so the first frame needs no fetch
    data_dir.mkdir(parents=True, exist_ok=True)
    atlas = json.dumps(atlas_document(records, items, units), ensure_ascii=False)
    (data_dir / "atlas.json").write_text(atlas, encoding="utf-8", newline="\n")
    questions = json.dumps(question_rows(records), ensure_ascii=False)
    (data_dir / "questions.json").write_text(questions, encoding="utf-8", newline="\n")
    crops_out = out_dir / "crops"
    shutil.rmtree(crops_out, ignore_errors=True)
    shutil.copytree(CROPS_DIR, crops_out)
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = {"units": [_unit_json(u) for u in units], "cases": planner_fixtures(units)}
    (FIXTURES_DIR / "plans.json").write_text(json.dumps(fixtures, indent=1) + "\n", encoding="utf-8", newline="\n")
    log.info("exported %d questions, %d units and %d crops to %s", len(records), len(units),
             sum(1 for _ in crops_out.rglob("*.png")), out_dir)
