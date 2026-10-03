"""LLM tagger on Groq: batched calls, strict JSON schema, cached results.

Two modes:
* full   - the model sees every syllabus item of the questions' part (GA or DA);
* hybrid - each question comes with only its top candidates from the ML ranking
           (retrieve with ML, decide with the LLM), which cuts prompt size.

Questions are sent in batches so the syllabus list is paid for once per batch; this
keeps a full run inside the free-tier budget (8K tokens/minute). Every result is cached
in data/processed/tagging/llm_<model>_<mode>.jsonl, so evaluation and rebuilds never
need the API key, and an interrupted run resumes where it stopped.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

from gate_atlas.config import ROOT_DIR
from gate_atlas.tagging.ml import TAGGING_DIR, TOP_K
from gate_atlas.tagging.reference import CONFIDENCES, FITS, MAX_SECONDARY, Tag
from gate_atlas.tagging.text import question_text

log = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"
REASONING_EFFORT = "low"
TEMPERATURE = 0.0
BATCH_SIZE = 10
MAX_COMPLETION_TOKENS = 8192
MAX_RETRIES = 8
MIN_PAUSE_SECONDS = 2.0
SECONDS_PER_MINUTE = 60.0
PROMPT_VERSION = "v2-batch"

SYSTEM_PROMPT = """You are an expert GATE Data Science and AI (DA) examiner. Tag each exam question with items of the official GATE syllabus.

Rules for every question:
- primary: the ONE syllabus item whose concept the question mainly tests, i.e. what a student must know to answer it. Prefer the most specific item.
- secondary: up to 3 other items the solution genuinely needs; use an empty list if none.
- fit: "direct" if an item explicitly covers the concept, "indirect" if the concept is related but not named in the syllabus, "outside" if no item covers it (still give the nearest item as primary).
- confidence: "high", "medium" or "low".
- rationale: one short sentence.
Use only the allowed item ids. Return exactly one result per question id. The question text was extracted from a PDF; fractions, matrices and figures may be garbled, so infer the topic from the readable parts."""


class DailyLimitReached(RuntimeError):
    """Raised when Groq refuses requests because a per-day quota is used up."""


def output_path(model: str, mode: str):
    """Cache file of one model/mode combination."""
    return TAGGING_DIR / f"llm_{model.replace('/', '_')}_{mode}.jsonl"


def response_schema(question_ids: list[str], item_ids: list[str]) -> dict:
    """Strict JSON schema for one batch; enums keep ids valid."""
    result = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "enum": question_ids},
            "primary": {"type": "string", "enum": item_ids},
            "secondary": {"type": "array", "items": {"type": "string", "enum": item_ids}},
            "fit": {"type": "string", "enum": list(FITS)},
            "confidence": {"type": "string", "enum": list(CONFIDENCES)},
            "rationale": {"type": "string"},
        },
        "required": ["id", "primary", "secondary", "fit", "confidence", "rationale"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"results": {"type": "array", "items": result}},
        "required": ["results"],
        "additionalProperties": False,
    }


def format_items(items: list[dict]) -> str:
    """Syllabus items grouped under their section titles."""
    lines, section = [], None
    for item in items:
        if item["section_title"] != section:
            section = item["section_title"]
            lines.append(f"## {section}")
        lines.append(f"{item['id']} {item['label']}")
    return "\n".join(lines)


def format_question(record: dict) -> str:
    """Header and text of one question."""
    marks = f"{record['marks']} mark{'s' if record['marks'] > 1 else ''}"
    return f"### {record['id']} ({record['type']}, {marks})\n{question_text(record)}"


def build_messages(batch: list[dict], items: list[dict], candidates: dict[str, list[dict]] | None) -> list[dict]:
    """Prompt for one batch. Hybrid batches list each question's own candidate items."""
    if candidates is None:
        body = f"Allowed syllabus items:\n{format_items(items)}\n\nQuestions:\n\n" + "\n\n".join(
            format_question(r) for r in batch
        )
    else:
        blocks = []
        for record in batch:
            options = "; ".join(f"{i['id']} {i['label']}" for i in candidates[record["id"]])
            blocks.append(f"{format_question(record)}\nCandidate items for this question: {options}")
        body = (
            "For each question choose primary and secondary items ONLY from that question's own candidate list.\n\n"
            "Questions:\n\n" + "\n\n".join(blocks)
        )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": body}]


def parse_tag(payload: dict, allowed: set[str]) -> Tag:
    """Turn one schema-valid result into a Tag, dropping duplicate or disallowed secondaries."""
    secondary = [s for s in dict.fromkeys(payload["secondary"]) if s != payload["primary"] and s in allowed]
    return Tag(
        payload["id"], payload["primary"], tuple(secondary[:MAX_SECONDARY]), payload["fit"], payload["confidence"],
        payload["rationale"].strip(),
    )


def make_client():
    """Groq client using GROQ_API_KEY from the environment or .env."""
    from dotenv import load_dotenv
    from groq import Groq

    load_dotenv(ROOT_DIR / ".env")
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set; add it to .env (see .env.example)")
    return Groq(max_retries=MAX_RETRIES)


def call_batch(client, model: str, batch: list[dict], items: list[dict], candidates: dict[str, list[dict]] | None) -> tuple[list[dict], dict]:
    """One API call for a batch; returns raw results and usage/rate-limit metadata."""
    import groq

    if candidates is None:
        allowed_ids = [i["id"] for i in items]
    else:
        allowed_ids = sorted({i["id"] for r in batch for i in candidates[r["id"]]})
    schema = response_schema([r["id"] for r in batch], allowed_ids)
    started = time.perf_counter()
    try:
        raw = client.chat.completions.with_raw_response.create(
            model=model,
            messages=build_messages(batch, items, candidates),
            response_format={"type": "json_schema", "json_schema": {"name": "syllabus_tags", "strict": True, "schema": schema}},
            temperature=TEMPERATURE,
            reasoning_effort=REASONING_EFFORT,
            include_reasoning=False,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
        )
    except groq.RateLimitError as error:
        if "per day" in str(error).lower() or "tpd" in str(error).lower() or "rpd" in str(error).lower():
            raise DailyLimitReached(str(error)) from error
        raise
    completion = raw.parse()
    payload = json.loads(completion.choices[0].message.content)
    meta = {
        "seconds": round(time.perf_counter() - started, 2),
        "prompt_tokens": completion.usage.prompt_tokens,
        "completion_tokens": completion.usage.completion_tokens,
        "tokens_per_minute_limit": int(raw.headers.get("x-ratelimit-limit-tokens") or 0),
        "batch_size": len(batch),
    }
    return payload["results"], meta


def load_cached(model: str, mode: str) -> dict[str, dict]:
    """Previously stored results keyed by question id (current prompt version only)."""
    path = output_path(model, mode)
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["id"]: row for row in rows if row.get("prompt_version") == PROMPT_VERSION}


def run_llm(
    records: list[dict],
    items: list[dict],
    *,
    model: str = DEFAULT_MODEL,
    mode: str = "full",
    candidates: dict[str, list[str]] | None = None,
    limit: int | None = None,
    force: bool = False,
) -> dict[str, dict]:
    """Tag questions in batches, appending results to the cache file after every call."""
    if mode == "hybrid" and not candidates:
        raise ValueError("hybrid mode needs ML candidate rankings (run `tag-ml` first)")
    cached = {} if force else load_cached(model, mode)
    todo = [r for r in records if r["id"] not in cached][:limit]
    log.info("%s/%s: %d cached, %d to tag", model, mode, len(cached), len(todo))
    if not todo:
        return cached

    client = make_client()
    by_id = {i["id"]: i for i in items}
    candidate_items = (
        {qid: [by_id[item_id] for item_id in ranked[:TOP_K]] for qid, ranked in candidates.items()} if candidates else None
    )
    path = output_path(model, mode)
    TAGGING_DIR.mkdir(parents=True, exist_ok=True)
    rows = dict(cached)
    for part in ("GA", "DA"):
        part_items = [i for i in items if i["part"] == part]
        pending = [r for r in todo if r["section"] == part]
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start:start + BATCH_SIZE]
            try:
                results, meta = call_batch(client, model, batch, part_items, candidate_items)
            except DailyLimitReached as error:
                log.warning("daily quota reached; %d results cached, rerun later to resume: %s", len(rows), error)
                return rows
            got = _store_results(rows, results, batch, meta, model, mode, candidate_items, part_items)
            _write_all(path, rows, records)
            log.info("%s batch %d: %d/%d tagged (%d tokens in, %d out, %.1fs)", part, start // BATCH_SIZE + 1, got, len(batch),
                     meta["prompt_tokens"], meta["completion_tokens"], meta["seconds"])
            _pace(meta)
    return rows


def _store_results(rows: dict, results: list[dict], batch: list[dict], meta: dict, model: str, mode: str,
                   candidate_items: dict | None, part_items: list[dict]) -> int:
    """Validate a batch's results and add them to rows; return how many were stored."""
    expected = {r["id"] for r in batch}
    stored = 0
    share = {k: round(meta[k] / len(batch)) for k in ("prompt_tokens", "completion_tokens")}
    for result in results:
        question_id = result["id"]
        if question_id not in expected or question_id in rows:
            continue  # duplicate or foreign id: ignore, a later run retries anything missing
        allowed = {i["id"] for i in (candidate_items[question_id] if candidate_items else part_items)}
        tag = parse_tag(result, allowed)
        rows[question_id] = {
            "id": question_id,
            "method": f"{model} ({mode}, reasoning={REASONING_EFFORT})",
            "prompt_version": PROMPT_VERSION,
            **tag.as_dict(),
            "primary_in_own_candidates": tag.primary in allowed,
            "candidates": sorted(allowed) if candidate_items else None,
            "usage": {**share, "seconds": round(meta["seconds"] / len(batch), 2), "batch_size": len(batch)},
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        stored += 1
    return stored


def _pace(meta: dict) -> None:
    """Sleep long enough that the next call stays under the tokens-per-minute limit."""
    used = meta["prompt_tokens"] + meta["completion_tokens"]
    limit = meta["tokens_per_minute_limit"] or 0
    pause = used / limit * SECONDS_PER_MINUTE if limit else MIN_PAUSE_SECONDS
    time.sleep(max(pause, MIN_PAUSE_SECONDS))


def _write_all(path, rows: dict[str, dict], records: list[dict]) -> None:
    """Rewrite the cache in question order so the file diff stays stable."""
    order = {r["id"]: k for k, r in enumerate(records)}
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in sorted(rows.values(), key=lambda row: order.get(row["id"], 10**6)):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
