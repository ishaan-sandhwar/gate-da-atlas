"""Merge parsed papers with answer keys into the question dataset and export it."""

import csv
import json
import logging
import re
from pathlib import Path

from gate_atlas.answer_key import KeyEntry, parse_key_pdf
from gate_atlas.config import CROPS_DIR, PAPER_CODE, PAPER_YEARS, PROCESSED_DIR, RAW_DIR, ROOT_DIR
from gate_atlas.paper import ParsedPaper, ParsedQuestion, parse_paper

log = logging.getLogger(__name__)

OPTION_LETTERS = ["A", "B", "C", "D"]
NEGATIVE_FRACTION_MCQ = 1 / 3  # GATE: wrong MCQ answer costs 1/3 of its marks; MSQ/NAT cost nothing
FIGURE_WORDS_RE = re.compile(r"(?i)\b(figure|diagram|as shown|shown (below|above|in))\b")
UNDERLINE_WORDS_RE = re.compile(r"(?i)underline")

# Why a question needs a human look. Order = order shown in needs_review.csv.
REVIEW_REASONS = {
    "option_labels": "MCQ/MSQ without exactly one each of (A)-(D), or a NAT with option labels",
    "empty_text": "stem or an option came out empty",
    "key_missing": "no answer-key row for this question",
    "figure": "contains an image or vector drawing; text alone is incomplete",
    "figure_referenced": "text refers to a figure that was not detected; check the crop",
    "table": "contains a table; extracted text flattens rows and columns",
    "display_math": "fractions, matrices, big operators or stacked math; linear text may be ambiguous",
    "unmapped_glyphs": "glyphs without a Unicode mapping (shown as private-use characters)",
    "formatting_semantics": "meaning depends on underlining (e.g. keys in a schema), which plain text loses",
}


def question_id(year: int, number: int) -> str:
    """Stable dataset id, for example DA2024-Q07."""
    return f"{PAPER_CODE}{year}-Q{number:02d}"


def review_reasons(question: ParsedQuestion, key: KeyEntry | None) -> list[str]:
    """List the reasons (from REVIEW_REASONS) why a question is not a clean parse."""
    features = question.features
    text = question.stem + " " + " ".join(question.options.values())
    reasons = []
    expects_options = key is not None and key.qtype in ("MCQ", "MSQ")
    if (expects_options and question.label_letters != OPTION_LETTERS) or (
        key is not None and key.qtype == "NAT" and question.label_letters
    ):
        reasons.append("option_labels")
    if not question.stem.strip() or any(not value.strip() for value in question.options.values()):
        reasons.append("empty_text")
    if key is None:
        reasons.append("key_missing")
    if features["has_figure"]:
        reasons.append("figure")
    elif FIGURE_WORDS_RE.search(text) and not features["has_table"]:
        reasons.append("figure_referenced")
    if features["has_table"]:
        reasons.append("table")
    math_layout = (
        "fraction_bars", "stacked_math_lines", "stacked_glyphs", "matrix_rows", "deep_scripts", "display_math_glyphs",
    )
    if any(features[name] for name in math_layout):
        reasons.append("display_math")
    if question.has_unmapped_glyphs:
        reasons.append("unmapped_glyphs")
    # Underlines matter when the text says so, or in code/schemas where they mark keys.
    underline_matters = UNDERLINE_WORDS_RE.search(text) or (features["has_code"] and not features["has_table"])
    if features["underline_rules"] and underline_matters:
        reasons.append("formatting_semantics")
    return reasons


def build_record(year: int, question: ParsedQuestion, key: KeyEntry | None) -> dict:
    """Build one dataset record from a parsed question and its key row."""
    reasons = review_reasons(question, key)
    is_mcq = key is not None and key.qtype == "MCQ"
    crop_path = CROPS_DIR / str(year) / f"{question_id(year, question.number)}.png"
    return {
        "id": question_id(year, question.number),
        "paper": PAPER_CODE,
        "year": year,
        "number": question.number,
        "session": key.session if key else None,
        "section": key.section if key else None,
        "marks": key.marks if key else None,
        "type": key.qtype if key else None,
        "negative_marks": round(key.marks * NEGATIVE_FRACTION_MCQ, 4) if is_mcq else 0.0,
        "stem": question.stem,
        "options": question.options or None,
        "answer": key.as_answer() if key else None,
        "answer_key_raw": key.raw if key else None,
        "status": "needs_review" if reasons else "clean",
        "review_reasons": reasons,
        "features": question.features,
        "source": {
            "paper_pdf": f"data/raw/{year}_{PAPER_CODE}_paper.pdf",
            "key_pdf": f"data/raw/{year}_{PAPER_CODE}_key.pdf",
            "pages": sorted({page + 1 for page, _ in question.regions}),
            "regions": [
                {"page": page + 1, "bbox": [round(v, 1) for v in box]} for page, box in question.regions
            ],
        },
        "crop": crop_path.relative_to(ROOT_DIR).as_posix(),
        "syllabus_tags": None,
    }


def build_year(year: int) -> tuple[list[dict], ParsedPaper, list[KeyEntry]]:
    """Parse one year's paper and key, render crops and return records."""
    paper = parse_paper(
        RAW_DIR / f"{year}_{PAPER_CODE}_paper.pdf",
        crops_dir=CROPS_DIR / str(year),
        id_prefix=f"{PAPER_CODE}{year}-",
    )
    keys = parse_key_pdf(RAW_DIR / f"{year}_{PAPER_CODE}_key.pdf")
    key_by_number = {entry.number: entry for entry in keys}
    records = [build_record(year, q, key_by_number.get(q.number)) for q in paper.questions]
    log.info(
        "%d: %d questions, %d clean, %d need review",
        year, len(records), sum(r["status"] == "clean" for r in records),
        sum(r["status"] == "needs_review" for r in records),
    )
    return records, paper, keys


def answer_text(answer: dict | None) -> str:
    """Flat, human-readable answer for CSV."""
    if not answer:
        return ""
    if answer["kind"] == "mta":
        return "MTA"
    if answer["kind"] == "range":
        return f"{answer['low']:g} to {answer['high']:g}"
    return ";".join(answer["options"])


def write_outputs(records: list[dict]) -> None:
    """Write questions.jsonl, questions.csv and needs_review.csv."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with (PROCESSED_DIR / "questions.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    columns = [
        "id", "year", "number", "section", "marks", "type", "negative_marks", "answer",
        "primary_item", "secondary_items", "tag_fit",
        "stem", "option_a", "option_b", "option_c", "option_d", "status", "review_reasons",
        "has_math", "has_code", "has_figure", "has_table", "pages", "crop",
    ]
    with (PROCESSED_DIR / "questions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            options = record["options"] or {}
            tags = record["syllabus_tags"] or {}
            writer.writerow({
                "id": record["id"], "year": record["year"], "number": record["number"],
                "section": record["section"], "marks": record["marks"], "type": record["type"],
                "negative_marks": record["negative_marks"], "answer": answer_text(record["answer"]),
                "primary_item": tags.get("primary", ""), "secondary_items": ";".join(tags.get("secondary", [])),
                "tag_fit": tags.get("fit", ""),
                "stem": record["stem"],
                **{f"option_{letter.lower()}": options.get(letter, "") for letter in OPTION_LETTERS},
                "status": record["status"], "review_reasons": ";".join(record["review_reasons"]),
                "has_math": record["features"]["has_math"], "has_code": record["features"]["has_code"],
                "has_figure": record["features"]["has_figure"], "has_table": record["features"]["has_table"],
                "pages": ";".join(str(p) for p in record["source"]["pages"]), "crop": record["crop"],
            })

    flagged = [r for r in records if r["status"] == "needs_review"]
    with (PROCESSED_DIR / "needs_review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "year", "number", "section", "type", "marks", "reasons", "what_to_check", "pages", "crop", "stem_preview"])
        for record in flagged:
            writer.writerow([
                record["id"], record["year"], record["number"], record["section"], record["type"], record["marks"],
                ";".join(record["review_reasons"]),
                " | ".join(REVIEW_REASONS[reason] for reason in record["review_reasons"]),
                ";".join(str(p) for p in record["source"]["pages"]), record["crop"],
                " ".join(record["stem"].split())[:160],
            ])
    log.info("wrote %d records (%d need review) to %s", len(records), len(flagged), PROCESSED_DIR)


def build_questions() -> tuple[list[dict], dict[int, tuple[ParsedPaper, list[KeyEntry]]]]:
    """Build records for every paper year; return them with per-year parse artefacts."""
    all_records: list[dict] = []
    artefacts = {}
    for year in PAPER_YEARS:
        records, paper, keys = build_year(year)
        all_records.extend(records)
        artefacts[year] = (paper, keys)
    return all_records, artefacts


def attach_tags(records: list[dict], tags: dict) -> None:
    """Put each question's reference syllabus tags into its record (in place)."""
    for record in records:
        tag = tags.get(record["id"])
        record["syllabus_tags"] = {**tag.as_dict(), "source": "reference"} if tag else None


def load_questions(path: Path = PROCESSED_DIR / "questions.jsonl") -> list[dict]:
    """Read the question dataset back from JSONL."""
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
