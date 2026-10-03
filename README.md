# GATE DA Atlas

An open, reproducible dataset of **GATE Data Science & Artificial Intelligence (DA)** previous-year
questions (2024, 2025, 2026). Every question is extracted only from the official master question
papers and answer keys, and is tagged against individual items of the official syllabus. Machine
learning and an LLM are used as automatic taggers, measured against the reference tags. The
analysis (weightage, trends, never-asked topics) and an adaptive study planner build on the dataset.

| Phase | Scope | Status |
|---|---|---|
| 1 | Official sources, syllabus items, question dataset, validation | **done** |
| 2 | Syllabus tags for every question; ML, LLM and hybrid taggers with evaluation | **done** |
| 3 | Analysis: weightage, year-on-year trends, topics never asked | planned |
| 4 | Adaptive study planner (exam date + daily hours + weak topics → weekly plan) | planned |
| 5 | Web "atlas" to explore the data and run the planner | planned |

## Quick start

Requires Python 3.11+.

```bash
py -m venv .venv                      # Windows; use python3 -m venv .venv elsewhere
.venv\Scripts\activate                # source .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"               # core + ML (sentence-transformers, scikit-learn) + LLM (groq)

python -m gate_atlas fetch            # optional: re-download official PDFs and verify checksums
python -m gate_atlas build            # rebuild data/processed from data/raw, attach tags, validate
python -m gate_atlas tag-ml           # ML taggers (downloads BAAI/bge-small-en-v1.5 once)
python -m gate_atlas tag-llm          # LLM tagger on Groq; add --mode hybrid --parts DA for ML+LLM
python -m gate_atlas evaluate-tags    # score every tagger -> data/processed/TAGGING.md
pytest                                # unit tests + dataset invariants
```

`build` exits with a non-zero status if any validation check fails. Only `tag-llm` needs a key:
copy `.env.example` to `.env` and set `GROQ_API_KEY`. LLM responses are cached in
`data/processed/tagging/`, so `evaluate-tags` and `build` run without a key.

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

## What Phase 2 adds

| File | Contents |
|---|---|
| `data/curation/reference_tags.csv` | Reference tags of all 195 questions: primary item, secondary items, fit, confidence, one-line rationale |
| `questions.jsonl` → `syllabus_tags` | The reference tags attached to every record (also `primary_item`, `secondary_items`, `tag_fit` in the CSV) |
| `data/processed/tagging/ml_*.jsonl` | ML rankings: zero-shot embeddings and cross-validated few-shot kNN blend |
| `data/processed/tagging/ml_section_classifier.json` | Section classifiers with 5-fold CV: reports and per-question predictions |
| `data/processed/tagging/llm_*.jsonl` | Cached Groq LLM tags (full syllabus list, and hybrid ML-candidates mode) |
| `data/processed/TAGGING.md` | Scores of every tagger, paired significance tests, LLM–ML agreement |
| `data/processed/tag_disagreements.csv` | Questions where the LLM and the reference disagree, side by side, for human review |

### Phase 2 numbers

| Tagger (scored against reference tags) | Questions | Primary item | Acceptable | Section |
|---|---|---|---|---|
| ML: zero-shot embeddings (`bge-small-en-v1.5`) | 195 | 39.0% | 49.7% | 80.0% |
| ML: few-shot kNN blend (nested 5-fold CV) | 195 | 39.5% | 51.3% | 84.6% |
| AI: `openai/gpt-oss-120b`, full syllabus list | 195 | 65.6% | 80.5% | 93.3% |
| **AI + ML: same LLM choosing among the ML top-15 (DA only)** | 165 | **75.8%** | **87.3%** | 95.2% |

On the same 165 DA questions the full-list LLM gets 65.4%, so retrieval by ML lifts the LLM by
10 points (exact McNemar test: 36 vs 19 discordant questions, p = 0.03). The DA section classifier
(sentence embeddings + logistic regression, 5-fold stratified CV) reaches 92.7% accuracy and 0.924
macro-F1, against 78.2% for TF-IDF and 20.6% for the majority class.

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

## Methodology — Phase 2: syllabus tagging

### 7. Reference tags

Every question has one **primary** item (the concept the question mainly tests: what a student must
know to answer it, using the most specific item available) and up to three **secondary** items (other
concepts the solution genuinely needs). GA questions take GA items, DA questions take DA items.
Each tag also records:

* `fit`: `direct` (an item names the concept), `indirect` (related but not named, e.g. topological sort
  under graph traversals, the perceptron rule under MLP) or `outside` (no item covers it; the nearest
  item is given);
* `confidence`: `high`, `medium` or `low`;
* `rationale`: one line.

The reference tags were written by Claude (the AI assistant that built this repository): clean
questions from their verified text, flagged questions from their crops. `reference_tags.csv` was
complete **before any tagger was run**, so no model output could influence it. They are a single annotator's judgement, not ground truth. `tag_disagreements.csv` lists every
place where the LLM disagrees, so a human can review them. Totals: 183 `direct`, 10 `indirect`,
2 `outside` (2026 Q35, an infinite double series, and 2026 Q47, precision/recall); 151 high,
43 medium, 1 low confidence; 91 questions have secondary items.

`build` rejects tags with unknown ids, items from the wrong paper part, a primary repeated as
secondary, more than three secondaries or an invalid fit/confidence.

### 8. ML taggers (scikit-learn + sentence-transformers)

* **Zero-shot retrieval.** Questions and items are embedded with `BAAI/bge-small-en-v1.5`, the
  questions with the model's retrieval instruction. Items of the question's own part are ranked by
  cosine similarity. No labels are used.
* **Few-shot kNN blend.** The score is `w·softmax(cos(q, item)/T) + (1−w)·P_kNN(item)`, where `P_kNN` is
  the similarity-weighted share of the 5 nearest labelled questions whose primary is that item. Both
  terms are probability distributions, so neither swamps the other. Scoring uses 5-fold CV. Inside
  each training set, an inner 4-fold CV picks `(w, T)` from a grid of 8, so the chosen setting never
  sees the test questions (nested CV). Chosen settings: w = 0.5–0.75, T = 0.02–0.05.
* **Section classifier.** DA questions are classified into the 7 syllabus sections with
  scikit-learn `Pipeline`s, using stratified 5-fold CV and `cross_val_predict`. Embeddings +
  `LogisticRegression` are compared with TF-IDF + `LogisticRegression` and a majority-class
  baseline; `classification_report` is stored for each.
* Seeds are fixed (`random`, `numpy`, `torch` = 42).

### 9. LLM tagger (Groq, `openai/gpt-oss-120b`)

* A system prompt carries the same rules as the reference guideline. Questions go in batches of 10,
  so the syllabus list is paid for once per batch. `temperature = 0`, `reasoning_effort = low`.
* **Strict JSON-schema output** (Groq constrained decoding) with item ids as an `enum`, so every answer
  is a valid syllabus id. Duplicates and items from outside the allowed set are dropped.
* **Hybrid mode (AI + ML).** Each question comes with only its top-15 items from the few-shot ML
  ranking, and the LLM chooses among them. The ML ranking contains the reference primary in its
  top 15 for 89.7% of questions; that is the ceiling. Hybrid mode was run on the 165 DA questions;
  GA's whole list is only 17 items.
* Rate limits (free tier: 8K tokens/min) are respected by pacing from the response headers. Every
  result is cached with its token usage. Totals: full run 103,770 tokens for 195 questions; hybrid
  run 92,555 tokens for 165.

### 10. Evaluation

`evaluate-tags` scores each tagger on primary-item accuracy, *acceptable* accuracy (predicted
primary is any reference item), cluster and section accuracy, top-k recall and MRR for rankings,
item-set precision/recall/F1 for the LLM, and Cohen's κ for DA sections. It breaks scores down by
GA/DA and by clean vs needs_review text, and compares every pair of taggers with an exact McNemar
test. Findings:

* LLM ≫ ML on the exact item (65.6% vs 39.5%), but ML's top-15 almost always contains the answer
  (89.7%).
* Giving the LLM only the ML candidates beats the full list: 75.8% vs 65.4% on DA, p = 0.03.
* When the LLM and the ML ranker agree (41% of DA questions in hybrid mode), the shared answer is
  right ~90% of the time. When they disagree, the hybrid LLM is right 66% of the time and ML 5%.
  For a future paper (e.g. GATE DA 2027): auto-accept agreements, route disagreements to review.
* Lossy PDF text (needs_review) costs the full-list LLM 7 points (61.9% vs 68.5%). Hybrid mode
  narrows the gap (74.7% vs 76.6%).
* The few-shot blend is not significantly better than zero-shot (20 vs 19 discordant, p = 1.0). With
  ~1.4 labelled questions per item, there are too few neighbours to help.

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
  "syllabus_tags": {"primary": "DA.DB.06", "secondary": [], "fit": "indirect", "confidence": "medium",
                    "rationale": "Derive functional dependencies with Armstrong's axioms.", "source": "reference"}
}
```

* `answer.kind` is `options` (MCQ/MSQ), `range` (NAT, inclusive `low`/`high`) or `mta`.
* `source.regions` gives the 1-based page and the clip box (PDF points) used for the crop.
* `syllabus_tags` ids refer to `syllabus_items.csv` (`DA.DB.06` = Normal forms).

## Repository layout

```
data/raw/               official PDFs + MANIFEST.json (never edited by hand)
data/curation/          hand-curated inputs: syllabus.toml, reference_tags.csv
data/processed/         everything generated by the pipeline (tagging/ holds tagger outputs)
src/gate_atlas/
  sources.py            registry of official URLs (organiser + mirrors)
  fetch.py              download, mirror agreement, checksums
  syllabus.py           syllabus parsing, edition comparison, coverage check
  layout.py             glyph/graphic extraction, watermark detection
  paper.py              question segmentation, text rebuilding, feature detection, crops
  answer_key.py         answer-key parsing
  dataset.py            merge, review reasons, tags, exports
  validate.py           invariants and the validation report
  tagging/
    reference.py        reference tags: loading and validation
    text.py             shared question/item text for the taggers
    ml.py               embeddings, few-shot kNN blend (nested CV), section classifiers
    llm.py              Groq tagger: batching, strict schema, caching, rate-limit pacing
    evaluate.py         metrics, McNemar tests, agreement analysis, TAGGING.md
tests/                  unit tests and dataset invariants
```

## Attribution and licence

The question papers, answer keys and syllabi are published by the GATE organising institutes
(IISc Bengaluru, IIT Roorkee, IIT Guwahati, IIT Madras) and remain theirs. This repository
redistributes them only for study and research, with links to the originals in `MANIFEST.json`.
A licence for the code and derived data has not been chosen yet.
