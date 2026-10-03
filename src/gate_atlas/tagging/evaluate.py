"""Score every tagger against the reference tags and write TAGGING.md."""

import csv
import json
from collections import Counter
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

from gate_atlas.config import PROCESSED_DIR
from gate_atlas.tagging.ml import TAGGING_DIR
from gate_atlas.tagging.reference import Tag

RANK_CUTOFFS = (1, 3, 5, 10, 15)
REPORT_PATH = PROCESSED_DIR / "TAGGING.md"
DISAGREEMENTS_PATH = PROCESSED_DIR / "tag_disagreements.csv"


def section_of(item_id: str) -> str:
    """Section id of an item id: DA.PS.07 -> DA.PS."""
    return item_id.rsplit(".", 1)[0]


def load_predictions(path: Path) -> dict[str, dict]:
    """Prediction file (one JSON object per line) keyed by question id."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["id"]: row for row in rows}


def score_method(predictions: dict[str, dict], reference: dict[str, Tag], records: list[dict], clusters: dict[str, str]) -> dict:
    """Accuracy-style metrics of one tagger, overall and by subset."""
    scored = [r for r in records if r["id"] in predictions]
    subsets = {
        "all": scored,
        "GA": [r for r in scored if r["section"] == "GA"],
        "DA": [r for r in scored if r["section"] == "DA"],
        "clean": [r for r in scored if r["status"] == "clean"],
        "needs_review": [r for r in scored if r["status"] == "needs_review"],
    }
    result = {"n": len(scored), "subsets": {}}
    for name, rows in subsets.items():
        if rows:
            result["subsets"][name] = _metrics(rows, predictions, reference, clusters)
    da = [r for r in scored if r["section"] == "DA"]
    if da:
        truth = [section_of(reference[r["id"]].primary) for r in da]
        guess = [section_of(predictions[r["id"]]["primary"]) for r in da]
        result["da_section_kappa"] = round(float(cohen_kappa_score(truth, guess)), 3)
    return result


def _metrics(rows: list[dict], predictions: dict[str, dict], reference: dict[str, Tag], clusters: dict[str, str]) -> dict:
    """Metrics over one subset of questions."""
    n = len(rows)
    out = {"n": n}
    hits = Counter()
    set_tp = set_fp = set_fn = 0
    for row in rows:
        truth = reference[row["id"]]
        prediction = predictions[row["id"]]
        primary = prediction["primary"]
        hits["primary"] += primary == truth.primary
        hits["primary_in_reference_items"] += primary in truth.items
        hits["section"] += section_of(primary) == section_of(truth.primary)
        hits["cluster"] += clusters[primary] == clusters[truth.primary]
        if "ranking" in prediction:
            ranked = [item for item, _ in prediction["ranking"]]
            for k in RANK_CUTOFFS:
                hits[f"recall@{k}"] += truth.primary in ranked[:k]
            reciprocal = next((1 / (rank + 1) for rank, item in enumerate(ranked) if item == truth.primary), 0.0)
            hits["mrr"] += reciprocal
        else:
            predicted_items = {primary, *prediction.get("secondary", [])}
            reference_items = set(truth.items)
            set_tp += len(predicted_items & reference_items)
            set_fp += len(predicted_items - reference_items)
            set_fn += len(reference_items - predicted_items)
    for key, value in hits.items():
        out[key] = round(value / n, 4)
    if set_tp + set_fp + set_fn:
        precision = set_tp / max(set_tp + set_fp, 1)
        recall = set_tp / max(set_tp + set_fn, 1)
        out["item_set_precision"] = round(precision, 4)
        out["item_set_recall"] = round(recall, 4)
        out["item_set_f1"] = round(2 * precision * recall / max(precision + recall, 1e-9), 4)
    return out


def agreement(first: dict[str, dict], second: dict[str, dict], reference: dict[str, Tag]) -> dict:
    """How often two taggers agree on the primary item, and accuracy when they agree or not."""
    shared = sorted(set(first) & set(second))
    agree = [q for q in shared if first[q]["primary"] == second[q]["primary"]]
    disagree = [q for q in shared if q not in set(agree)]

    def accuracy(ids: list[str], source: dict[str, dict]) -> float | None:
        return round(sum(source[q]["primary"] == reference[q].primary for q in ids) / len(ids), 4) if ids else None

    return {
        "n": len(shared),
        "agreement_rate": round(len(agree) / len(shared), 4) if shared else None,
        "accuracy_when_agree": accuracy(agree, first),
        "first_accuracy_when_disagree": accuracy(disagree, first),
        "second_accuracy_when_disagree": accuracy(disagree, second),
        "disagreements": disagree,
    }


def mcnemar(first: dict[str, dict], second: dict[str, dict], reference: dict[str, Tag]) -> dict:
    """Exact McNemar test on questions both taggers labelled: is one more often right?

    Only discordant questions (one right, the other wrong) carry information; under the
    null hypothesis each discordant question favours either tagger with probability 1/2.
    """
    from scipy.stats import binomtest

    shared = sorted(set(first) & set(second))
    only_first = sum(first[q]["primary"] == reference[q].primary != second[q]["primary"] for q in shared)
    only_second = sum(second[q]["primary"] == reference[q].primary != first[q]["primary"] for q in shared)
    discordant = only_first + only_second
    p_value = binomtest(only_first, discordant, 0.5).pvalue if discordant else 1.0
    return {"n": len(shared), "only_first_right": only_first, "only_second_right": only_second, "p_value": round(float(p_value), 4)}


def llm_cost(predictions: dict[str, dict]) -> dict:
    """Token and time totals recorded for an LLM run."""
    usages = [p["usage"] for p in predictions.values() if p.get("usage")]
    if not usages:
        return {}
    return {
        "questions": len(usages),
        "prompt_tokens": sum(u["prompt_tokens"] for u in usages),
        "completion_tokens": sum(u["completion_tokens"] for u in usages),
        "mean_seconds_per_question": round(sum(u["seconds"] for u in usages) / len(usages), 2),
    }


def evaluate_all(records: list[dict], reference: dict[str, Tag], items: list[dict]) -> dict:
    """Score every prediction file present in data/processed/tagging."""
    clusters = {i["id"]: f"{i['section_id']}:{i['cluster']}" for i in items}
    methods = {}
    loaded = {}
    for path in sorted(TAGGING_DIR.glob("*.jsonl")):
        predictions = load_predictions(path)
        loaded[path.stem] = predictions
        method = next(iter(predictions.values()))["method"]
        methods[path.stem] = {"method": method, **score_method(predictions, reference, records, clusters)}
        if path.stem.startswith("llm_"):
            methods[path.stem]["cost"] = llm_cost(predictions)

    agreements = {}
    for llm_name in (name for name in loaded if name.startswith("llm_")):
        for ml_name in (name for name in loaded if name.startswith("ml_")):
            agreements[f"{llm_name} vs {ml_name}"] = agreement(loaded[llm_name], loaded[ml_name], reference)

    names = sorted(loaded)
    paired = {
        f"{a} vs {b}": mcnemar(loaded[a], loaded[b], reference)
        for index, a in enumerate(names) for b in names[index + 1:]
    }

    classifier_path = TAGGING_DIR / "ml_section_classifier.json"
    classifier = json.loads(classifier_path.read_text(encoding="utf-8")) if classifier_path.exists() else None
    report = {"n_reference": len(reference), "methods": methods, "agreements": agreements, "paired_tests": paired}
    if classifier:
        report["section_classifier"] = {
            name: {k: v for k, v in model.items() if k in ("accuracy", "macro_f1")}
            for name, model in classifier["models"].items()
        }
        report["section_classifier_meta"] = {k: classifier[k] for k in ("labels", "n_questions", "folds")}
    (TAGGING_DIR / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(report), encoding="utf-8")
    write_disagreements(records, reference, items, loaded)
    return report


def write_disagreements(records: list[dict], reference: dict[str, Tag], items: list[dict], loaded: dict[str, dict]) -> None:
    """List questions where the main LLM tagger and the reference differ, for human review."""
    llm_name = next((name for name in sorted(loaded) if name.startswith("llm_") and name.endswith("_full")), None)
    if llm_name is None:
        return
    labels = {i["id"]: i["label"] for i in items}
    llm, ml = loaded[llm_name], loaded.get("ml_fewshot_blend", {})
    with DISAGREEMENTS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "id", "reference_primary", "reference_label", "llm_primary", "llm_label", "ml_primary",
            "llm_primary_in_reference_items", "reference_rationale", "llm_rationale", "crop",
        ])
        for record in records:
            truth, guess = reference[record["id"]], llm.get(record["id"])
            if guess is None or guess["primary"] == truth.primary:
                continue
            writer.writerow([
                record["id"], truth.primary, labels[truth.primary], guess["primary"], labels[guess["primary"]],
                ml.get(record["id"], {}).get("primary", ""), guess["primary"] in truth.items,
                truth.rationale, guess["rationale"], record["crop"],
            ])


def _pct(value: float | None) -> str:
    """Format a share as a percentage."""
    return "–" if value is None else f"{100 * value:.1f}%"


def render_markdown(report: dict) -> str:
    """Human-readable tagging report."""
    lines = [
        "# Tagging evaluation",
        "",
        f"All taggers are scored against the {report['n_reference']} reference tags in `data/curation/reference_tags.csv`.",
        "*Primary* = predicted primary item equals the reference primary. *Acceptable* = predicted primary is",
        "the reference primary or one of its secondary items. Section/cluster = the predicted primary falls in",
        "the same syllabus section/cluster.",
        "",
        "## Primary-item accuracy",
        "",
        "| Tagger | n | Primary | Acceptable | Cluster | Section | DA section κ |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, method in report["methods"].items():
        overall = method["subsets"]["all"]
        lines.append(
            f"| {method['method']} | {method['n']} | {_pct(overall['primary'])} | {_pct(overall['primary_in_reference_items'])} | "
            f"{_pct(overall['cluster'])} | {_pct(overall['section'])} | {method.get('da_section_kappa', '–')} |"
        )
    lines += ["", "## By subset (primary accuracy)", "", "| Tagger | GA | DA | clean text | needs_review text |", "|---|---|---|---|---|"]
    for method in report["methods"].values():
        subsets = method["subsets"]
        cells = [_pct(subsets[s]["primary"]) if s in subsets else "–" for s in ("GA", "DA", "clean", "needs_review")]
        lines.append(f"| {method['method']} | " + " | ".join(cells) + " |")

    ranked = {name: m for name, m in report["methods"].items() if "recall@1" in m["subsets"]["all"]}
    if ranked:
        lines += ["", "## ML rankings: is the reference primary in the top k?", "", "| Tagger | " + " | ".join(f"top-{k}" for k in RANK_CUTOFFS) + " | MRR |", "|---|" + "---|" * (len(RANK_CUTOFFS) + 1)]
        for method in ranked.values():
            overall = method["subsets"]["all"]
            lines.append(f"| {method['method']} | " + " | ".join(_pct(overall[f'recall@{k}']) for k in RANK_CUTOFFS) + f" | {overall['mrr']:.3f} |")

    llms = {name: m for name, m in report["methods"].items() if name.startswith("llm_")}
    if llms:
        lines += ["", "## LLM item sets and cost", "", "| Tagger | Item-set precision | Item-set recall | Item-set F1 | Questions | Prompt tokens | Completion tokens | Mean s/question |", "|---|---|---|---|---|---|---|---|"]
        for method in llms.values():
            overall, cost = method["subsets"]["all"], method.get("cost", {})
            lines.append(
                f"| {method['method']} | {_pct(overall.get('item_set_precision'))} | {_pct(overall.get('item_set_recall'))} | "
                f"{_pct(overall.get('item_set_f1'))} | {cost.get('questions', '–')} | {cost.get('prompt_tokens', '–')} | "
                f"{cost.get('completion_tokens', '–')} | {cost.get('mean_seconds_per_question', '–')} |"
            )

    if report.get("section_classifier"):
        meta = report["section_classifier_meta"]
        lines += ["", f"## DA section classifier ({meta['folds']}-fold stratified CV, {meta['n_questions']} questions, {len(meta['labels'])} sections)", "", "| Model | Accuracy | Macro-F1 |", "|---|---|---|"]
        for name, scores in report["section_classifier"].items():
            lines.append(f"| {name} | {_pct(scores['accuracy'])} | {scores['macro_f1']:.3f} |")

    if report.get("paired_tests"):
        lines += ["", "## Paired comparison (exact McNemar test on questions both taggers labelled)", "",
                  "| Pair | n | Only first right | Only second right | p-value |", "|---|---|---|---|---|"]
        for pair, stats in report["paired_tests"].items():
            lines.append(f"| {pair} | {stats['n']} | {stats['only_first_right']} | {stats['only_second_right']} | {stats['p_value']} |")

    if report["agreements"]:
        lines += ["", "## LLM vs ML agreement", "", "When the LLM and an ML ranker pick the same primary item, how often is it right?", "", "| Pair | Agree | Accuracy when agree | LLM accuracy when disagree | ML accuracy when disagree |", "|---|---|---|---|---|"]
        for pair, stats in report["agreements"].items():
            lines.append(
                f"| {pair} | {_pct(stats['agreement_rate'])} | {_pct(stats['accuracy_when_agree'])} | "
                f"{_pct(stats['first_accuracy_when_disagree'])} | {_pct(stats['second_accuracy_when_disagree'])} |"
            )
    return "\n".join(lines) + "\n"
