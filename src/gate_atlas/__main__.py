"""Command-line entry point: python -m gate_atlas <command>."""

import argparse
import logging
import shutil
import sys

from gate_atlas import fetch
from gate_atlas.config import CROPS_DIR, PAPER_YEARS, PROCESSED_DIR


def build() -> int:
    """Build syllabus + question dataset from data/raw, attach reference tags and validate."""
    from gate_atlas.dataset import attach_tags, build_questions, write_outputs
    from gate_atlas.syllabus import build_syllabus, flat_items, write_syllabus_outputs
    from gate_atlas.tagging.reference import load_reference, validate_tags
    from gate_atlas.validate import check_global, check_tags, check_year, write_report

    shutil.rmtree(CROPS_DIR, ignore_errors=True)
    syllabus = build_syllabus()
    write_syllabus_outputs(syllabus, PROCESSED_DIR)
    records, artefacts = build_questions()
    reference = load_reference()
    tag_problems = validate_tags(reference, records, {row["item_id"] for row in flat_items(syllabus)})
    attach_tags(records, reference)
    write_outputs(records)

    checks = []
    for year in PAPER_YEARS:
        paper, keys = artefacts[year]
        checks += check_year(year, [r for r in records if r["year"] == year], paper, keys)
    checks += check_global(records, syllabus)
    checks += check_tags(records, tag_problems)
    report = write_report(checks, records)

    for check in checks:
        status = "PASS" if check.passed else ("FAIL" if check.level == "error" else "WARN")
        logging.info("[%s] %s (%s)", status, check.name, check.detail)
    logging.info("validation %s", "PASSED" if report["passed"] else "FAILED")
    return 0 if report["passed"] else 1


def tagging_inputs() -> tuple[list[dict], list[dict], dict]:
    """Questions, syllabus items and reference tags from the built dataset."""
    from gate_atlas.dataset import load_questions
    from gate_atlas.tagging.reference import load_reference
    from gate_atlas.tagging.text import load_items

    return load_questions(), load_items(), load_reference()


def tag_ml() -> int:
    """Run the ML taggers (embeddings, few-shot blend, section classifier)."""
    from gate_atlas.tagging.ml import run_ml

    records, items, reference = tagging_inputs()
    run_ml(records, items, reference)
    return 0


def tag_llm(model: str, mode: str, limit: int | None, force: bool, parts: list[str]) -> int:
    """Run the Groq LLM tagger in full or hybrid mode on the chosen paper parts."""
    from gate_atlas.tagging.evaluate import load_predictions
    from gate_atlas.tagging.llm import run_llm
    from gate_atlas.tagging.ml import TAGGING_DIR

    records, items, _ = tagging_inputs()
    records = [r for r in records if r["section"] in parts]
    candidates = None
    if mode == "hybrid":
        ranking = load_predictions(TAGGING_DIR / "ml_fewshot_blend.jsonl")
        candidates = {qid: [item for item, _ in row["ranking"]] for qid, row in ranking.items()}
    run_llm(records, items, model=model, mode=mode, candidates=candidates, limit=limit, force=force)
    return 0


def evaluate_tags() -> int:
    """Score all taggers against the reference tags."""
    from gate_atlas.tagging.evaluate import evaluate_all

    records, items, reference = tagging_inputs()
    evaluate_all(records, reference, items)
    logging.info("wrote %s", PROCESSED_DIR / "TAGGING.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run one pipeline command."""
    from gate_atlas.tagging.llm import DEFAULT_MODEL

    parser = argparse.ArgumentParser(prog="gate_atlas", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="download official PDFs into data/raw")
    commands.add_parser("verify-raw", help="check data/raw against MANIFEST.json")
    commands.add_parser("build", help="build syllabus + questions from data/raw, attach tags, validate")
    commands.add_parser("tag-ml", help="run embedding / kNN / classifier taggers")
    llm = commands.add_parser("tag-llm", help="run the Groq LLM tagger (needs GROQ_API_KEY)")
    llm.add_argument("--model", default=DEFAULT_MODEL)
    llm.add_argument("--mode", choices=["full", "hybrid"], default="full")
    llm.add_argument("--limit", type=int, default=None, help="tag at most this many uncached questions")
    llm.add_argument("--force", action="store_true", help="ignore cached responses")
    llm.add_argument("--parts", default="GA,DA", help="comma-separated paper parts to tag (GA, DA)")
    commands.add_parser("evaluate-tags", help="score taggers against reference tags")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "sentence_transformers", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.command == "fetch":
        fetch.fetch_all()
    elif args.command == "verify-raw":
        problems = fetch.verify_raw_files()
        for problem in problems:
            logging.error(problem)
        return 1 if problems else 0
    elif args.command == "build":
        return build()
    elif args.command == "tag-ml":
        return tag_ml()
    elif args.command == "tag-llm":
        return tag_llm(args.model, args.mode, args.limit, args.force, args.parts.split(","))
    elif args.command == "evaluate-tags":
        return evaluate_tags()
    return 0


if __name__ == "__main__":
    sys.exit(main())
