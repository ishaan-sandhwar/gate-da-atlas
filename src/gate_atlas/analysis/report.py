"""ANALYSIS.md: findings, tables and charts generated from analysis.json.

Every sentence with a number is built from the computed tables, so the report cannot
drift from the data.
"""

from collections import defaultdict

from gate_atlas.analysis.charts import SHORT_TITLES

TOP_FORECAST_ROWS = 25
TOP_PAIRS = 12
NAT_HEAVY_SECTIONS = 2


def _picture(name: str, alt: str) -> str:
    """Markdown/HTML image that follows the reader's light/dark preference."""
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="analysis/charts/{name}_dark.png">\n'
        f'  <img alt="{alt}" src="analysis/charts/{name}_light.png" width="800">\n'
        "</picture>"
    )


def _pct(value: float) -> str:
    """Share as a percentage with one decimal."""
    return f"{100 * value:.1f}%"


def _num(value: float) -> str:
    """Compact number: integers without decimals, else one decimal."""
    return f"{value:.0f}" if abs(value - round(value)) < 1e-9 else f"{value:.1f}"


def key_findings(doc: dict) -> list[str]:
    """Data-driven headline findings."""
    years = doc["years"]
    sections = [r for r in doc["sections"]["primary"] if r["part"] == "DA"]
    by_mean = sorted(sections, key=lambda r: -r["marks_mean"])
    items = [i for i in doc["items"] if i["part"] == "DA"]
    never = [i for i in items if i["status"] == "never_asked"]
    only_secondary = [i for i in items if i["status"] == "only_secondary"]
    coverage = [c for c in doc["coverage"] if c["part"] == "DA"]
    rising = [r for r in sections if r["trend"] == "rising"]
    falling = [r for r in sections if r["trend"] == "falling"]
    evergreen = [i for i in items if all(i[f"primary_marks_{y}"] > 0 for y in years)]
    backtest = doc["backtest"]["DA"]
    sensitivity = doc["tag_sensitivity"].get("llm_openai_gpt-oss-120b_full")

    def series(row: dict) -> str:
        return " → ".join(_num(row[f"marks_{y}"]) for y in years)

    findings = [
        "**Three sections carry over half of the DA marks:** "
        + ", ".join(f"{SHORT_TITLES[r['section_id']]} ({_num(r['marks_mean'])} marks a paper, {_pct(r['share_of_part'])})" for r in by_mean[:3])
        + f"; together {_pct(sum(r['share_of_part'] for r in by_mean[:3]))} of the 85 DA marks.",
    ]
    if rising or falling:
        moves = [f"{SHORT_TITLES[r['section_id']]} {series(r)} (rising)" for r in rising]
        moves += [f"{SHORT_TITLES[r['section_id']]} {series(r)} (falling)" for r in falling]
        findings.append("**Clear moves across " + f"{years[0]}–{years[-1]}:** " + "; ".join(moves)
                        + ". Three papers make these descriptions of the past, not forecasts.")
    mixed = [r for r in sections if r["trend"] == "mixed"]
    if mixed:
        findings.append("**Volatile sections:** " + "; ".join(f"{SHORT_TITLES[r['section_id']]} {series(r)}" for r in mixed)
                        + ". Their weight swings from paper to paper.")
    findings.append(
        f"**{len(never)} of {len(items)} DA syllabus items were never asked** in any form, and {len(only_secondary)} more appear only "
        f"as secondary concepts. Each paper touches {min(c['items_touched'] for c in coverage)}–{max(c['items_touched'] for c in coverage)} "
        f"DA items ({_pct(min(c['share'] for c in coverage))}–{_pct(max(c['share'] for c in coverage))} of the syllabus)."
    )
    if evergreen:
        findings.append("**Asked as a primary topic in every paper:** "
                        + ", ".join(f"{i['label']} ({i['section_id'].split('.')[1]})" for i in evergreen) + ".")
    nat = defaultdict(lambda: [0, 0])
    for row in doc["type_mix"]:
        if row["part"] == "DA":
            nat[row["section_id"]][0] += row["questions"] if row["type"] == "NAT" else 0
            nat[row["section_id"]][1] += row["questions"]
    nat_heavy = sorted(nat.items(), key=lambda kv: -kv[1][0] / kv[1][1])[:NAT_HEAVY_SECTIONS]
    findings.append("**Numerical-answer heavy:** " + ", ".join(
        f"{SHORT_TITLES[section]} ({_pct(n / total)} NAT)" for section, (n, total) in nat_heavy
    ) + ". There are no options to eliminate there, so practise solving to the final number.")
    ga = sorted((r for r in doc["sections"]["primary"] if r["part"] == "GA"), key=lambda r: -r["marks_mean"])
    findings.append("**General Aptitude (15 marks):** " + "; ".join(
        f"{r['title']} {_num(r['marks_mean'])} marks a paper ({r['trend']})" for r in ga
    ) + ".")
    findings.append(
        f"**Item history helps only a little.** In a leave-one-paper-out backtest the Bayesian model scores Brier "
        f"{backtest['bayes']['brier']:.3f}, against {backtest['pooled']['brier']:.3f} when every item gets its section's "
        f"rate and {backtest['empirical']['brier']:.3f} when items are judged only by their own history. Which section an item "
        f"belongs to predicts most of what comes next; plan by section and cluster first."
    )
    if sensitivity:
        findings.append(
            f"**Robust to tagging choices:** replacing the reference tags with the LLM's changes any section's marks in any "
            f"paper by at most {sensitivity['max_abs_change_marks']} marks (mean {sensitivity['mean_abs_change_marks']})."
        )
    return findings


def _section_table(doc: dict, part: str) -> list[str]:
    """Per-section marks table (primary attribution) with the shared-scheme mean beside it."""
    years = doc["years"]
    shared = {r["id"]: r for r in doc["sections"]["shared"]}
    rows = [r for r in doc["sections"]["primary"] if r["part"] == part]
    header = "| Section | Items | " + " | ".join(str(y) for y in years) + " | Mean | Share | Trend (marks/yr) | Mean, shared attribution |"
    lines = [header, "|---|---|" + "---|" * len(years) + "---|---|---|---|"]
    for row in rows:
        lines.append(
            f"| {row['title']} | {row['items']} | " + " | ".join(_num(row[f'marks_{y}']) for y in years)
            + f" | {_num(row['marks_mean'])} | {_pct(row['share_of_part'])} | {row['trend']} ({row['trend_marks_per_year']:+.1f})"
            + f" | {shared[row['id']]['marks_mean']:.1f} |"
        )
    return lines


def _cluster_table(doc: dict) -> list[str]:
    """DA clusters by mean marks."""
    years = doc["years"]
    rows = [r for r in doc["clusters"]["primary"] if r["part"] == "DA"]
    lines = ["| Section | Cluster | Items | " + " | ".join(str(y) for y in years) + " | Mean |", "|---|---|---|" + "---|" * len(years) + "---|"]
    for row in sorted(rows, key=lambda r: -r["marks_mean"]):
        lines.append(f"| {row['section_id'].split('.')[1]} | {row['title']} | {row['items']} | "
                     + " | ".join(_num(row[f'marks_{y}']) for y in years) + f" | {_num(row['marks_mean'])} |")
    return lines


def _never_asked(doc: dict) -> list[str]:
    """Never-asked items grouped by section, with the model's chance of appearing next."""
    grouped = defaultdict(list)
    for item in doc["items"]:
        if item["status"] == "never_asked":
            grouped[(item["part"], item["section_title"])].append(item)
    lines = ["| Section | Never-asked items (chance of appearing in the next paper) |", "|---|---|"]
    for (part, title), items in sorted(grouped.items(), key=lambda kv: (kv[0][0] != "DA", kv[0][1])):
        cells = ", ".join(f"{i['label']} ({_pct(i['forecast_p_asked'])})" for i in items)
        lines.append(f"| {part}: {title} | {cells} |")
    return lines


def _type_mix(doc: dict) -> list[str]:
    """MCQ/MSQ/NAT counts per DA section over all papers."""
    counts = defaultdict(lambda: defaultdict(int))
    for row in doc["type_mix"]:
        if row["part"] == "DA":
            counts[row["section_id"]][row["type"]] += row["questions"]
    lines = ["| Section | MCQ | MSQ | NAT | NAT share |", "|---|---|---|---|---|"]
    for section, by_type in sorted(counts.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(by_type.values())
        lines.append(f"| {SHORT_TITLES[section]} | {by_type['MCQ']} | {by_type['MSQ']} | {by_type['NAT']} | {_pct(by_type['NAT'] / total)} |")
    return lines


def _forecast_table(doc: dict) -> list[str]:
    """Top DA items by expected marks in the next paper."""
    items = sorted((i for i in doc["items"] if i["part"] == "DA"), key=lambda i: -i["forecast_expected_marks"])
    lines = ["| Item | Section | Asked 2024–26 (primary) | Expected marks next paper | P(asked) | 80% interval, questions |", "|---|---|---|---|---|---|"]
    for item in items[:TOP_FORECAST_ROWS]:
        lines.append(
            f"| {item['label']} | {item['section_id'].split('.')[1]} | {item['primary_questions']:g} | "
            f"{item['forecast_expected_marks']:.2f} | {_pct(item['forecast_p_asked'])} | "
            f"{item['forecast_rate_low']:.2f}–{item['forecast_rate_high']:.2f} |"
        )
    return lines


def _pairs(doc: dict) -> list[str]:
    """Most frequent cross-section concept pairs."""
    pairs = [p for p in doc["cooccurrence"] if p["cross_section"]][:TOP_PAIRS]
    lines = ["| Concept | Often needed with | Questions |", "|---|---|---|"]
    for pair in pairs:
        lines.append(f"| {pair['label_a']} ({pair['item_a']}) | {pair['label_b']} ({pair['item_b']}) | {pair['questions']} |")
    return lines


def render_report(doc: dict) -> str:
    """Full ANALYSIS.md."""
    prior = doc["forecast_prior"]["DA"]
    backtest = doc["backtest"]
    lines = [
        "# GATE DA Atlas — analysis of the 2024–2026 papers",
        "",
        "Generated by `python -m gate_atlas analyze` from the reference syllabus tags (Phase 2). Marks go to each",
        "question's **primary** syllabus item unless a table says *shared* (primary weight 1, each secondary 0.5,",
        "normalised). Every paper has 85 DA + 15 GA marks. Three papers is a small sample: read trends as history.",
        "",
        "## Key findings",
        "",
        *[f"- {finding}" for finding in key_findings(doc)],
        "",
        "## DA weightage by section",
        "",
        _picture("section_marks", "Grouped bars of DA marks per syllabus section for 2024, 2025 and 2026"),
        "",
        *_section_table(doc, "DA"),
        "",
        "## GA weightage by section",
        "",
        *_section_table(doc, "GA"),
        "",
        "## DA weightage by cluster",
        "",
        *_cluster_table(doc),
        "",
        "## Topics never asked",
        "",
        _picture("coverage", "Stacked bars of DA syllabus items asked at least once versus never asked, per section"),
        "",
        *_never_asked(doc),
        "",
        "## Question types by section",
        "",
        *_type_mix(doc),
        "",
        "## Forecast for the next paper",
        "",
        _picture("forecast", "Dot and interval plot of expected marks in the next paper for the top 20 DA items"),
        "",
        *_forecast_table(doc),
        "",
        "Model: per-item yearly question counts are Poisson with a Gamma prior centred on the item's section rate; the",
        f"shared Gamma shape is fitted by maximum marginal likelihood (DA shape = {prior['shape']}; GA's fit runs to the",
        "upper bound, i.e. GA items within a section are indistinguishable and get their section rate). Expected marks",
        "use the section's average marks per question. Items differ in size (\"Programming in Python\" vs \"z-test\"), so",
        "compare items within a section and plan time by section and cluster.",
        "",
        "| Backtest (leave one paper out) | Brier ↓ | Log loss ↓ | Count RMSE ↓ |",
        "|---|---|---|---|",
    ]
    for part in ("DA", "GA"):
        for name in ("pooled", "empirical", "bayes"):
            scores = backtest[part][name]
            lines.append(f"| {part} — {name} | {scores['brier']:.4f} | {scores['log_loss']:.4f} | {scores['count_rmse']:.4f} |")
    lines += [
        "",
        "## Concepts that travel together",
        "",
        "Cross-section pairs tagged on the same question (primary or secondary). Study them together.",
        "",
        *_pairs(doc),
        "",
    ]
    return "\n".join(lines)
