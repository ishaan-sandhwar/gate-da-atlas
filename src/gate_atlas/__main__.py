"""Command-line entry point: python -m gate_atlas <command>."""

import argparse
import logging
import shutil
import sys

from gate_atlas import fetch
from gate_atlas.config import CROPS_DIR, PAPER_YEARS, PROCESSED_DIR


def build() -> int:
    """Build syllabus + question dataset from data/raw and validate it."""
    from gate_atlas.dataset import build_questions
    from gate_atlas.syllabus import build_syllabus, write_syllabus_outputs
    from gate_atlas.validate import check_global, check_year, write_report

    shutil.rmtree(CROPS_DIR, ignore_errors=True)
    syllabus = build_syllabus()
    write_syllabus_outputs(syllabus, PROCESSED_DIR)
    records, artefacts = build_questions()

    checks = []
    for year in PAPER_YEARS:
        paper, keys = artefacts[year]
        checks += check_year(year, [r for r in records if r["year"] == year], paper, keys)
    checks += check_global(records, syllabus)
    report = write_report(checks, records)

    for check in checks:
        status = "PASS" if check.passed else ("FAIL" if check.level == "error" else "WARN")
        logging.info("[%s] %s (%s)", status, check.name, check.detail)
    logging.info("validation %s", "PASSED" if report["passed"] else "FAILED")
    return 0 if report["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run one pipeline command."""
    parser = argparse.ArgumentParser(prog="gate_atlas", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="download official PDFs into data/raw")
    commands.add_parser("verify-raw", help="check data/raw against MANIFEST.json")
    commands.add_parser("build", help="build syllabus + questions from data/raw and validate")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "fetch":
        fetch.fetch_all()
    elif args.command == "verify-raw":
        problems = fetch.verify_raw_files()
        for problem in problems:
            logging.error(problem)
        return 1 if problems else 0
    elif args.command == "build":
        return build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
