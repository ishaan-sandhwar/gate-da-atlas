# GATE DA Atlas

An open, reproducible dataset of **GATE Data Science & Artificial Intelligence (DA)** previous-year
questions (2024, 2025, 2026). Every question is extracted only from the official master question
papers and answer keys, and will be tagged against individual items of the official syllabus.
The analysis (weightage, trends, never-asked topics) and an adaptive study planner will be built
on top of the dataset.

| Phase | Scope | Status |
|---|---|---|
| 1 | Official sources, syllabus items, question dataset, validation | **done** |
| 2 | Tag every question with syllabus items | planned |
| 3 | Analysis: weightage, year-on-year trends, topics never asked | planned |
| 4 | Adaptive study planner (exam date + daily hours + weak topics → weekly plan) | planned |
| 5 | Web "atlas" to explore the data and run the planner | planned |

## Quick start

Requires Python 3.11+. No environment variables or API keys are needed.

```bash
py -m venv .venv                      # Windows; use python3 -m venv .venv elsewhere
.venv\Scripts\activate                # source .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"

python -m gate_atlas fetch            # optional: re-download official PDFs and verify checksums
python -m gate_atlas build            # rebuild data/processed from data/raw and validate
pytest                                # unit tests + dataset invariants
```

`build` exits with a non-zero status if any validation check fails.

## What Phase 1 produces

| File | Contents |
|---|---|
| `data/raw/*.pdf` | 14 official PDFs: DA papers and answer keys 2024–2026, DA and GA syllabi 2024–2027 |
| `data/raw/MANIFEST.json` | For every PDF: source URLs, SHA-256, size, and whether every official mirror served identical bytes |
| `data/processed/syllabus.json` | Syllabus as sections → items, each item carrying its verbatim official text |
| `data/processed/syllabus_items.csv` | The same items, one row each (136 items: 119 DA + 17 GA) |
| `data/processed/questions.jsonl` | 195 question records (schema below) |
| `data/processed/questions.csv` | Flat version of the same records for spreadsheets |
| `data/processed/needs_review.csv` | The 84 questions whose text extraction is not reliable on its own, with reasons |
| `data/processed/crops/<year>/*.png` | Image of every question cut from the official paper — the visual ground truth |
| `data/processed/VALIDATION.md` | Human-readable validation report (`validation_report.json` is the same in JSON) |

### Phase 1 numbers

| Year | Questions | Marks | MCQ | MSQ | NAT | GA | DA | Clean | Needs review |
|---|---|---|---|---|---|---|---|---|---|
| 2024 | 65 | 100 | 37 | 12 | 16 | 10 | 55 | 33 | 32 |
| 2025 | 65 | 100 | 35 | 18 | 12 | 10 | 55 | 34 | 31 |
| 2026 | 65 | 100 | 33 | 14 | 18 | 10 | 55 | 44 | 21 |

## Methodology

### 1. Sources and provenance

The papers were not available locally, so they are downloaded from the official websites of the
GATE organising institutes: IISc Bengaluru (2024), IIT Roorkee (2025), IIT Guwahati (2026) and
IIT Madras (2027 syllabus). Each later organiser re-hosts earlier papers, so every paper and key is
downloaded from **all** official copies (2 to 4 URLs each; each syllabus has one official URL) and
the fetch refuses a document whose copies differ. All copies agreed byte-for-byte. `MANIFEST.json`
records every URL and SHA-256 hash, and the validation re-checks the files against it on every
build.

Answer keys: 2024 and 2025 are labelled *Final Answer Key* by their organisers. The 2026 key is the
one IIT Guwahati lists on its question-paper page, which says the challenge window (25–28 Feb 2026)
has closed; that page does not label it "final".

No question, option or answer is ever written from memory or generated: everything in the dataset
comes from these PDFs.

### 2. Syllabus → taggable items

* The official DA and GA syllabi of 2024, 2025, 2026 and 2027 were compared word by word after
  repairing broken glyphs (the 2024 PDF encodes "ti" as "Ɵ") and line-break hyphens.
  **The syllabus text is identical in all four editions**, so all three papers are measured against
  one syllabus. The 2027 edition (IIT Madras) is the canonical copy.
* The official syllabus is a run-on list, not lines. `data/curation/syllabus.toml` splits each
  section into items that can be tagged, for example `DA.PS.20` = "Poisson". Each item stores the
  **verbatim official phrase** it comes from; official sub-headings ("Search algorithms:") are kept
  as headings, not items.
* The build checks that the items and headings, read in order, cover the whole official section,
  leaving only punctuation and the word "and". So no item can be invented and no official phrase can
  be dropped silently.
* `label` (readable name) and `cluster` (roll-up group such as "Distributions") are editorial and
  marked as such. Two official quirks are noted on the items: Poisson is listed among the continuous
  distributions, and "normalization" appears in two senses (relational normal forms `DA.DB.06` and
  data scaling `DA.DB.10`).

### 3. Questions

Parsing uses the positions of characters, fonts and drawings in the PDF (PyMuPDF), not plain text:

1. Running headers/footers, watermarks and logos are removed. A graphic counts as page furniture
   when the same placement repeats on at least half of the pages; watermark images are re-embedded
   on each page, so they are matched by size and position instead of object id.
2. Question numbers (`Q.17`, `Q. 17`) are found in the left margin. Every other piece of text
   belongs to the last question number whose top lies above the bottom of that piece. This keeps
   a tall first line (for example a fraction) with its own question.
3. Option labels `(A)`–`(D)` — or a bare `A`–`D` in the margin, as in 2024 Q55 — split the
   question into stem and options. The same ownership rule assigns option text to labels.
4. Text is rebuilt line by line. Smaller raised/lowered glyphs become `^{...}` / `_{...}`. In code,
   indentation is kept from glyph positions, because indentation carries meaning in Python.
   Combining marks are re-attached to the right letter (`T̄`, `≠`), math-italic letters are mapped
   to plain letters, and a Wingdings arrow (checked against the crop of 2026 Q17) is mapped to `→`.
5. Every question is rendered to a PNG crop from the official page. **The crop is the reference
   whenever text and crop disagree.**
6. Marks, type (MCQ/MSQ/NAT) and section come from the answer key. Marks are cross-checked against
   the "Q.11 – Q.35 carry one mark each" headings printed in the paper. The 2024 paper omits the
   heading for Q36–Q65, so for those questions the key is the only source. Negative marking follows
   the GATE rule: 1/3 of the marks for a wrong MCQ, nothing for MSQ/NAT.

### 4. needs_review policy

A question is `clean` only when its text alone carries the whole question. Otherwise it is
`needs_review`, with one or more reasons:

| Reason | Meaning | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| `figure` | image or vector drawing; text alone is incomplete | 9 | 8 | 5 |
| `table` | table; extracted text flattens rows and columns | 9 | 4 | 5 |
| `display_math` | fractions, matrices/vectors, binomials, limits, roots or n-ary operators: linear text is ambiguous | 19 | 21 | 15 |
| `unmapped_glyphs` | glyphs without a Unicode mapping (TeX extensible brackets) | 0 | 3 | 0 |
| `formatting_semantics` | meaning depends on underlining (keys in a schema) | 2 | 1 | 0 |
| `empty_text` | an option is only a picture | 2 | 0 | 0 |
| `option_labels`, `key_missing`, `figure_referenced` | structural failures (none at present) | 0 | 0 | 0 |

Flagged questions keep their best-effort text and are fully usable through their crops; Phase 2
tagging reads every question's crop, not only its text.

### 5. Validation (all checks pass)

Per year: 65 question numbers found in order; 65 key rows; total marks = 100; GA = 5×1 + 5×2 marks;
DA = 25×1 + 30×2 marks; Q1–Q10 are GA; printed mark headings agree with the key; every key answer is
well-formed for its type (one letter for MCQ, letters for MSQ, `low ≤ high` for NAT, or MTA); keyed
letters exist among the parsed options; every question has a crop. Global: raw files match the
manifest checksums; ids are unique; the syllabus curation covers every official phrase. Only
2024 Q59 is *marks-to-all* (MTA) in the official key.

### 6. Manual audit

* The extracted text of **every** question first marked clean (121) was read in full. That found
  11 false-clean questions (flattened matrices, column vectors, binomial coefficients, case braces,
  limits under `max`/`lim`/sums, a square root) and a few text defects (misplaced overline and
  negation marks, missing spaces after math). A detector was added for each pattern; all 11
  questions are now flagged, and the text defects are fixed in every record.
* A seeded random sample of 12 clean questions (`random.seed(42)`) was compared with the crops:
  12/12 faithful. One has a minor notation loss: a subscript nested inside a superscript is flattened
  (2026 Q4 reads `n^{log10(m)}` for n^(log₁₀ m)).
* 2026 Q17 became clean after the Wingdings arrow fix; its text was compared with its crop.

### Known limitations

* Sub/superscripts are rebuilt heuristically. Nested scripts are flattened, and a subscript drawn
  at full font size (2025 Q55, `µred` = μ_red) is not marked.
* Text inside figures (node labels, chart values) ends up in the stem or options of flagged
  questions.
* The detectors are tuned to flag rather than miss, so some flagged questions may read fine as text.

## Record schema (`questions.jsonl`)

```json
{
  "id": "DA2024-Q46", "paper": "DA", "year": 2024, "number": 46, "session": 1,
  "section": "DA", "marks": 2, "type": "MSQ", "negative_marks": 0.0,
  "stem": "Given the relational schema R = (U,V, W, X, Y, Z) and the set of functional\ndependencies: ...",
  "options": {"A": "VW → YZ", "B": "WX → YZ", "C": "VW → U", "D": "VW → Y"},
  "answer": {"kind": "options", "options": ["A", "B", "D"]},
  "answer_key_raw": "A;B;D",
  "status": "clean", "review_reasons": [],
  "features": {"has_math": true, "has_code": false, "has_figure": false, "has_table": false, "...": 0},
  "source": {"paper_pdf": "data/raw/2024_DA_paper.pdf", "key_pdf": "data/raw/2024_DA_key.pdf",
             "pages": [29], "regions": [{"page": 29, "bbox": [52.0, 80.6, 545.0, 372.2]}]},
  "crop": "data/processed/crops/2024/DA2024-Q46.png",
  "syllabus_tags": []
}
```

* `answer.kind` is `options` (MCQ/MSQ), `range` (NAT, inclusive `low`/`high`) or `mta`.
* `source.regions` gives the 1-based page and the clip box (PDF points) used for the crop.
* `syllabus_tags` is filled in Phase 2.

## Repository layout

```
data/raw/               official PDFs + MANIFEST.json (never edited by hand)
data/curation/          hand-curated inputs: syllabus.toml
data/processed/         everything generated by `python -m gate_atlas build`
src/gate_atlas/
  sources.py            registry of official URLs (organiser + mirrors)
  fetch.py              download, mirror agreement, checksums
  syllabus.py           syllabus parsing, edition comparison, coverage check
  layout.py             glyph/graphic extraction, watermark detection
  paper.py              question segmentation, text rebuilding, feature detection, crops
  answer_key.py         answer-key parsing
  dataset.py            merge, review reasons, exports
  validate.py           invariants and the validation report
tests/                  unit tests and dataset invariants
```

## Attribution and licence

The question papers, answer keys and syllabi are published by the GATE organising institutes
(IISc Bengaluru, IIT Roorkee, IIT Guwahati, IIT Madras) and remain theirs. This repository
redistributes them only for study and research, with links to the originals in `MANIFEST.json`.
A licence for the code and derived data has not been chosen yet.
