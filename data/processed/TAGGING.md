# Tagging evaluation

All taggers are scored against the 195 reference tags in `data/curation/reference_tags.csv`.
*Primary* = predicted primary item equals the reference primary. *Acceptable* = predicted primary is
the reference primary or one of its secondary items. Section/cluster = the predicted primary falls in
the same syllabus section/cluster.

## Primary-item accuracy

| Tagger | n | Primary | Acceptable | Cluster | Section | DA section κ |
|---|---|---|---|---|---|---|
| openai/gpt-oss-120b (full, reasoning=low) | 195 | 65.6% | 80.5% | 85.6% | 93.3% | 0.943 |
| openai/gpt-oss-120b (hybrid, reasoning=low) | 165 | 75.8% | 87.3% | 88.5% | 95.2% | 0.943 |
| few-shot kNN blend (k=5, nested 5-fold CV) | 195 | 39.5% | 51.3% | 61.5% | 84.6% | 0.856 |
| zero-shot BAAI/bge-small-en-v1.5 | 195 | 39.0% | 49.7% | 59.0% | 80.0% | 0.806 |

## By subset (primary accuracy)

| Tagger | GA | DA | clean text | needs_review text |
|---|---|---|---|---|
| openai/gpt-oss-120b (full, reasoning=low) | 66.7% | 65.5% | 68.5% | 61.9% |
| openai/gpt-oss-120b (hybrid, reasoning=low) | – | 75.8% | 76.6% | 74.7% |
| few-shot kNN blend (k=5, nested 5-fold CV) | 36.7% | 40.0% | 40.5% | 38.1% |
| zero-shot BAAI/bge-small-en-v1.5 | 40.0% | 38.8% | 40.5% | 36.9% |

## ML rankings: is the reference primary in the top k?

| Tagger | top-1 | top-3 | top-5 | top-10 | top-15 | MRR |
|---|---|---|---|---|---|---|
| few-shot kNN blend (k=5, nested 5-fold CV) | 39.5% | 62.6% | 73.9% | 86.2% | 89.7% | 0.544 |
| zero-shot BAAI/bge-small-en-v1.5 | 39.0% | 66.7% | 71.3% | 80.0% | 86.7% | 0.541 |

## LLM item sets and cost

| Tagger | Item-set precision | Item-set recall | Item-set F1 | Questions | Prompt tokens | Completion tokens | Mean s/question |
|---|---|---|---|---|---|---|---|
| openai/gpt-oss-120b (full, reasoning=low) | 73.6% | 60.5% | 66.4% | 195 | 78285 | 25485 | 0.35 |
| openai/gpt-oss-120b (hybrid, reasoning=low) | 62.5% | 76.6% | 68.8% | 165 | 68400 | 24155 | 0.4 |

## DA section classifier (5-fold stratified CV, 165 questions, 7 sections)

| Model | Accuracy | Macro-F1 |
|---|---|---|
| majority_class | 20.6% | 0.049 |
| tfidf_logreg | 78.2% | 0.766 |
| embedding_logreg | 92.7% | 0.924 |

## Paired comparison (exact McNemar test on questions both taggers labelled)

| Pair | n | Only first right | Only second right | p-value |
|---|---|---|---|---|
| llm_openai_gpt-oss-120b_full vs llm_openai_gpt-oss-120b_hybrid | 165 | 19 | 36 | 0.03 |
| llm_openai_gpt-oss-120b_full vs ml_fewshot_blend | 195 | 70 | 19 | 0.0 |
| llm_openai_gpt-oss-120b_full vs ml_zero_shot | 195 | 73 | 21 | 0.0 |
| llm_openai_gpt-oss-120b_hybrid vs ml_fewshot_blend | 165 | 64 | 5 | 0.0 |
| llm_openai_gpt-oss-120b_hybrid vs ml_zero_shot | 165 | 66 | 5 | 0.0 |
| ml_fewshot_blend vs ml_zero_shot | 195 | 20 | 19 | 1.0 |

## LLM vs ML agreement

When the LLM and an ML ranker pick the same primary item, how often is it right?

| Pair | Agree | Accuracy when agree | LLM accuracy when disagree | ML accuracy when disagree |
|---|---|---|---|---|
| llm_openai_gpt-oss-120b_full vs ml_fewshot_blend | 32.8% | 90.6% | 53.4% | 14.5% |
| llm_openai_gpt-oss-120b_full vs ml_zero_shot | 32.3% | 87.3% | 55.3% | 15.9% |
| llm_openai_gpt-oss-120b_hybrid vs ml_fewshot_blend | 41.2% | 89.7% | 66.0% | 5.1% |
| llm_openai_gpt-oss-120b_hybrid vs ml_zero_shot | 40.6% | 88.1% | 67.3% | 5.1% |
