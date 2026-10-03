"""Run the Phase 3 analysis and write its tables to data/processed/analysis."""

import csv
import json
import logging
from collections import defaultdict
from pathlib import Path

from gate_atlas.analysis.forecast import backtest, forecast
from gate_atlas.analysis.weightage import (
    SCHEMES,
    aggregate,
    cooccurrence,
    group_rows,
    item_rows,
    tag_sensitivity,
    type_mix,
    yearly_coverage,
)
from gate_atlas.config import PAPER_YEARS, PROCESSED_DIR

log = logging.getLogger(__name__)

ANALYSIS_DIR = PROCESSED_DIR / "analysis"
TAGGING_DIR = PROCESSED_DIR / "tagging"
SENSITIVITY_SOURCES = ("llm_openai_gpt-oss-120b_full", "ml_fewshot_blend")


def write_csv(path: Path, rows: list[dict]) -> None:
    """Write rows (dicts with the same keys) to CSV."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def primary_counts(records: list[dict], items: list[dict], part: str) -> dict[str, list[int]]:
    """Questions per year whose primary item is each item of one paper part."""
    counts = {i["id"]: [0] * len(PAPER_YEARS) for i in items if i["part"] == part}
    for record in records:
        if record["section"] == part:
            counts[record["syllabus_tags"]["primary"]][PAPER_YEARS.index(record["year"])] += 1
    return counts


def marks_per_question(records: list[dict]) -> dict[str, float]:
    """Average marks of a question in each syllabus section (by primary item)."""
    marks, questions = defaultdict(int), defaultdict(int)
    for record in records:
        section = record["syllabus_tags"]["primary"].rsplit(".", 1)[0]
        marks[section] += record["marks"]
        questions[section] += 1
    return {section: marks[section] / questions[section] for section in questions}


def load_jsonl(path: Path) -> dict[str, dict]:
    """JSON lines keyed by id."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["id"]: row for row in rows}


def run_analysis(records: list[dict], items: list[dict]) -> dict:
    """Compute every Phase 3 table, write CSV/JSON outputs and return the analysis document."""
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    tables = {scheme: aggregate(records, items, scheme) for scheme in SCHEMES}
    sections = {scheme: group_rows(items, tables[scheme], "section") for scheme in SCHEMES}
    clusters = {scheme: group_rows(items, tables[scheme], "cluster") for scheme in SCHEMES}
    item_table = item_rows(records, items, tables["primary"], tables["shared"])

    per_question_marks = marks_per_question(records)
    fits, backtests = {}, {}
    forecasts: dict[str, dict] = {}
    for part in ("DA", "GA"):
        counts = primary_counts(records, items, part)
        fit, predicted = forecast(counts, per_question_marks)
        fits[part] = {"shape": round(fit.shape, 4), "section_rates": {k: round(v, 4) for k, v in fit.section_rates.items()}}
        backtests[part] = backtest(counts)
        forecasts.update(predicted)
        log.info("%s forecast: shape %.3f, expected questions next paper %.1f", part, fit.shape,
                 sum(p["expected_questions"] for p in predicted.values()))
    for row in item_table:
        row.update({f"forecast_{key}": value for key, value in forecasts[row["item_id"]].items()})

    sensitivity = {
        source: tag_sensitivity(records, load_jsonl(TAGGING_DIR / f"{source}.jsonl"))
        for source in SENSITIVITY_SOURCES if (TAGGING_DIR / f"{source}.jsonl").exists()
    }
    mix = type_mix(records)
    pairs = cooccurrence(records, items)
    coverage = yearly_coverage(records, items)

    write_csv(ANALYSIS_DIR / "section_weightage.csv", [{"scheme": s, **row} for s in SCHEMES for row in sections[s]])
    write_csv(ANALYSIS_DIR / "cluster_weightage.csv", [{"scheme": s, **row} for s in SCHEMES for row in clusters[s]])
    write_csv(ANALYSIS_DIR / "item_weightage.csv", item_table)
    write_csv(ANALYSIS_DIR / "never_asked.csv", [
        {k: row[k] for k in ("part", "section_id", "section_title", "cluster", "item_id", "label",
                             "forecast_p_asked", "forecast_expected_marks")}
        for row in item_table if row["status"] == "never_asked"
    ])
    write_csv(ANALYSIS_DIR / "type_mix.csv", mix)
    write_csv(ANALYSIS_DIR / "cooccurrence.csv", pairs)
    write_csv(ANALYSIS_DIR / "yearly_coverage.csv", coverage)

    document = {
        "years": list(PAPER_YEARS),
        "sections": sections,
        "clusters": clusters,
        "items": item_table,
        "type_mix": mix,
        "cooccurrence": pairs,
        "coverage": coverage,
        "forecast_prior": fits,
        "backtest": backtests,
        "tag_sensitivity": sensitivity,
    }
    (ANALYSIS_DIR / "analysis.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document
