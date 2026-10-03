"""Classical ML taggers evaluated against the reference tags.

1. Zero-shot retrieval: rank syllabus items by cosine similarity between sentence
   embeddings of the question and of each item. Needs no labels.
2. Few-shot blend: mix that similarity with votes from the most similar *labelled*
   questions, so past tags inform new ones. Scored with 5-fold cross-validation, so a
   question never sees its own label.
3. Section classifier: predict the syllabus section of DA questions with a scikit-learn
   Pipeline, compared with a majority-class and a TF-IDF baseline, 5-fold stratified CV.
"""

import json
import logging
import os
import random
from dataclasses import dataclass

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

from gate_atlas.config import PROCESSED_DIR
from gate_atlas.tagging.reference import Tag
from gate_atlas.tagging.text import item_text, question_text

log = logging.getLogger(__name__)

TAGGING_DIR = PROCESSED_DIR / "tagging"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge retrieval instruction
RANDOM_SEED = 42
CV_FOLDS = 5
TOP_K = 15
KNN_NEIGHBOURS = 5
INNER_FOLDS = 4
# (weight of item similarity, softmax temperature); picked per outer fold by inner CV.
BLEND_GRID = [(w, t) for w in (0.25, 0.5, 0.75, 1.0) for t in (0.02, 0.05)]


@dataclass
class Embeddings:
    """Unit-normalised embeddings of questions and syllabus items."""

    question_ids: list[str]
    questions: np.ndarray  # (n_questions, dim)
    item_ids: list[str]
    items: np.ndarray  # (n_items, dim)


def set_seeds() -> None:
    """Make every stochastic step reproducible."""
    import torch

    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    torch.manual_seed(RANDOM_SEED)


def compute_embeddings(records: list[dict], items: list[dict], model_name: str = EMBED_MODEL) -> Embeddings:
    """Embed questions (as queries) and syllabus items (as passages)."""
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # Windows without developer mode
    from sentence_transformers import SentenceTransformer

    set_seeds()
    model = SentenceTransformer(model_name, device="cpu")
    question_vectors = model.encode(
        [QUERY_PREFIX + question_text(r) for r in records], normalize_embeddings=True, batch_size=32
    )
    item_vectors = model.encode([item_text(i) for i in items], normalize_embeddings=True, batch_size=32)
    return Embeddings([r["id"] for r in records], question_vectors, [i["id"] for i in items], item_vectors)


def _part_mask(item_ids: list[str], part: str) -> np.ndarray:
    """Boolean mask of items belonging to a paper part (GA or DA)."""
    return np.array([item_id.startswith(f"{part}.") for item_id in item_ids])


def zero_shot_rankings(emb: Embeddings, records: list[dict]) -> dict[str, list[tuple[str, float]]]:
    """Top-K items per question by cosine similarity, restricted to the question's part."""
    similarity = emb.questions @ emb.items.T  # cosine, since rows are unit vectors
    rankings = {}
    for row, record in enumerate(records):
        mask = _part_mask(emb.item_ids, record["section"])
        scores = np.where(mask, similarity[row], -np.inf)
        order = np.argsort(-scores)[:TOP_K]
        rankings[record["id"]] = [(emb.item_ids[k], float(scores[k])) for k in order]
    return rankings


def cv_folds(records: list[dict]) -> np.ndarray:
    """Fold number of each question: 5 folds stratified by paper part."""
    labels = [r["section"] for r in records]
    folds = np.zeros(len(records), dtype=int)
    splitter = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)
    for fold, (_, test_index) in enumerate(splitter.split(np.zeros(len(labels)), labels)):
        folds[test_index] = fold
    return folds


def blend_scores(
    row: int, train: list[int], emb: Embeddings, records: list[dict], reference: dict[str, Tag],
    weight: float, temperature: float,
) -> np.ndarray:
    """Mixture of two distributions over the items of the question's part.

    P_sim(item)  = softmax(cos(q, item) / temperature)
    P_knn(item)  = similarity-weighted share of the K nearest labelled questions whose
                   primary is item (uniform when no neighbour is similar)
    score(item)  = weight * P_sim(item) + (1 - weight) * P_knn(item)
    Both terms are probabilities, so neither swamps the other because of its scale.
    """
    mask = _part_mask(emb.item_ids, records[row]["section"])
    similarity = emb.items @ emb.questions[row]
    logits = np.where(mask, similarity / temperature, -np.inf)
    p_sim = np.exp(logits - logits[mask].max())  # subtract max for numerical stability
    p_sim /= p_sim.sum()

    question_similarity = emb.questions[train] @ emb.questions[row]
    nearest = np.argsort(-question_similarity)[:KNN_NEIGHBOURS]
    p_knn = np.zeros(len(emb.item_ids))
    for k in nearest:
        p_knn[emb.item_ids.index(reference[records[train[k]]["id"]].primary)] += max(question_similarity[k], 0.0)
    p_knn = p_knn / p_knn.sum() if p_knn.sum() > 0 else mask / mask.sum()
    return np.where(mask, weight * p_sim + (1 - weight) * p_knn, -np.inf)


def _top1_accuracy(
    rows: list[int], pool: list[int], emb: Embeddings, records: list[dict], reference: dict[str, Tag],
    weight: float, temperature: float,
) -> float:
    """Top-1 accuracy on rows when neighbours come only from pool (same part)."""
    hits = 0
    for row in rows:
        train = [p for p in pool if p != row and records[p]["section"] == records[row]["section"]]
        scores = blend_scores(row, train, emb, records, reference, weight, temperature)
        hits += emb.item_ids[int(np.argmax(scores))] == reference[records[row]["id"]].primary
    return hits / max(len(rows), 1)


def blend_rankings(emb: Embeddings, records: list[dict], reference: dict[str, Tag]) -> tuple[dict, list[dict]]:
    """Few-shot rankings with nested cross-validation.

    Outer 5-fold CV scores the method. Inside each outer training set, an inner 4-fold
    CV picks (weight, temperature) from a small grid, so the chosen setting never sees
    the outer test questions.
    """
    folds = cv_folds(records)
    rankings = {}
    chosen = []
    for fold in range(CV_FOLDS):
        train_rows = [k for k in range(len(records)) if folds[k] != fold]
        test_rows = [k for k in range(len(records)) if folds[k] == fold]
        shuffled = np.random.default_rng(RANDOM_SEED + fold).permutation(train_rows)  # rows are ordered by year
        inner = np.array_split(shuffled, INNER_FOLDS)
        best = max(
            BLEND_GRID,
            key=lambda setting: np.mean([
                _top1_accuracy(list(part), [k for k in train_rows if k not in set(part)], emb, records, reference, *setting)
                for part in inner
            ]),
        )
        chosen.append({"fold": fold, "weight": best[0], "temperature": best[1]})
        for row in test_rows:
            train = [k for k in train_rows if records[k]["section"] == records[row]["section"]]
            scores = blend_scores(row, train, emb, records, reference, *best)
            order = np.argsort(-scores)[:TOP_K]
            rankings[records[row]["id"]] = [(emb.item_ids[k], float(scores[k])) for k in order]
    log.info("few-shot blend settings chosen by inner CV: %s", chosen)
    return {r["id"]: rankings[r["id"]] for r in records}, chosen


def section_classifier_cv(emb: Embeddings, records: list[dict], reference: dict[str, Tag]) -> dict:
    """5-fold stratified CV of section classifiers for DA questions."""
    rows = [k for k, r in enumerate(records) if r["section"] == "DA"]
    texts = [question_text(records[k]) for k in rows]
    vectors = emb.questions[rows]
    labels = np.array([reference[records[k]["id"]].primary.rsplit(".", 1)[0] for k in rows])
    splitter = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)
    identity = FunctionTransformer()  # embeddings are already unit-normalised features

    candidates = {
        "majority_class": (Pipeline([("identity", identity), ("model", DummyClassifier(strategy="most_frequent"))]), vectors),
        "tfidf_logreg": (
            Pipeline([
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
                ("model", LogisticRegression(max_iter=5000, class_weight="balanced", random_state=RANDOM_SEED)),
            ]),
            texts,
        ),
        "embedding_logreg": (
            Pipeline([
                ("identity", identity),
                ("model", LogisticRegression(max_iter=5000, C=10.0, class_weight="balanced", random_state=RANDOM_SEED)),
            ]),
            vectors,
        ),
    }
    results = {}
    for name, (pipeline, features) in candidates.items():
        predicted = cross_val_predict(pipeline, features, labels, cv=splitter)
        results[name] = {
            "accuracy": round(float(accuracy_score(labels, predicted)), 4),
            "macro_f1": round(float(f1_score(labels, predicted, average="macro", zero_division=0)), 4),
            "report": classification_report(labels, predicted, zero_division=0, output_dict=True),
            "predictions": {records[k]["id"]: str(p) for k, p in zip(rows, predicted)},
        }
        log.info("section classifier %-16s accuracy %.3f macro-F1 %.3f", name, results[name]["accuracy"], results[name]["macro_f1"])
    return {"labels": sorted(set(labels)), "n_questions": len(rows), "folds": CV_FOLDS, "models": results}


def write_rankings(path_name: str, method: str, rankings: dict[str, list[tuple[str, float]]]) -> None:
    """Write one JSON line per question: method, ranked items and scores."""
    TAGGING_DIR.mkdir(parents=True, exist_ok=True)
    with (TAGGING_DIR / path_name).open("w", encoding="utf-8", newline="\n") as handle:
        for question_id, ranking in rankings.items():
            line = {
                "id": question_id,
                "method": method,
                "primary": ranking[0][0],
                "ranking": [[item, round(score, 4)] for item, score in ranking],
            }
            handle.write(json.dumps(line) + "\n")


def run_ml(records: list[dict], items: list[dict], reference: dict[str, Tag]) -> dict:
    """Run every ML tagger and write their predictions to data/processed/tagging."""
    emb = compute_embeddings(records, items)
    zero_shot = zero_shot_rankings(emb, records)
    blend, chosen = blend_rankings(emb, records, reference)
    write_rankings("ml_zero_shot.jsonl", f"zero-shot {EMBED_MODEL}", zero_shot)
    write_rankings("ml_fewshot_blend.jsonl", f"few-shot kNN blend (k={KNN_NEIGHBOURS}, nested {CV_FOLDS}-fold CV)", blend)
    (TAGGING_DIR / "ml_fewshot_blend_settings.json").write_text(json.dumps(chosen, indent=2) + "\n", encoding="utf-8")
    sections = section_classifier_cv(emb, records, reference)
    (TAGGING_DIR / "ml_section_classifier.json").write_text(json.dumps(sections, indent=2) + "\n", encoding="utf-8")
    np.save(TAGGING_DIR / "question_embeddings.npy", emb.questions.astype(np.float32))
    (TAGGING_DIR / "question_embeddings_ids.json").write_text(json.dumps(emb.question_ids) + "\n", encoding="utf-8")
    return {"zero_shot": zero_shot, "blend": blend, "sections": sections}
