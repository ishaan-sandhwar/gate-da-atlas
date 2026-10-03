# Data licence

This repository holds three kinds of material, under three different terms.

| Material | Terms |
| --- | --- |
| **Code**: `src/`, `web/` (except the generated data below), `tests/`, build and config files | [MIT](LICENSE) |
| **The project's own data and analysis** (see the list below) | [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/) |
| **Official GATE material and anything copied from it** (see the exclusions below) | Not licensed by this project; it remains the property of its owners |

## Covered by CC BY 4.0

Copyright (c) 2026 Ishaan Sandhwar. Licensed under CC BY 4.0: you may share and adapt this material for any purpose,
including commercially, as long as you give appropriate credit, link to the licence and say if you changed it. The
full legal code is at <https://creativecommons.org/licenses/by/4.0/legalcode>.

- The syllabus segmentation in `data/curation/syllabus.toml` and its exports (item ids, labels, clusters and notes;
  not the official wording itself)
- The reference tags in `data/curation/reference_tags.csv` and the `syllabus_tags` field of the question records
- The study-hour assumptions in `data/curation/study_hours.toml`
- Tagger outputs and evaluations in `data/processed/tagging/`, `TAGGING.md` and `tag_disagreements.csv`
- The analysis in `data/processed/analysis/` and `ANALYSIS.md`, including the charts and the forecast
- Validation reports, `needs_review` flags and the derived features of each question record
- Planner examples in `examples/`, and the README images in `docs/`

Suggested credit: *GATE DA Atlas by Ishaan Sandhwar, CC BY 4.0*, with a link to this repository.

## Not covered

The question papers, answer keys and syllabi are published by the GATE organising institutes (IISc Bengaluru,
IIT Roorkee, IIT Guwahati and IIT Madras). This project does not own them and cannot license them. That covers:

- the PDFs in `data/raw/`
- question text, options and answer keys in `data/processed/questions.jsonl`, `questions.csv`, `needs_review.csv` and
  the exported web data
- the question images in `data/processed/crops/` and `web/public/crops/`
- the verbatim official syllabus wording stored with each syllabus item

They are included only for study and research, with links to the official sources in `data/raw/MANIFEST.json`. If you
reuse them, check the terms of the organising institutes.
