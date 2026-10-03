"""Text views of questions and syllabus items shared by the ML and LLM taggers."""

import json
import re

from gate_atlas.config import PROCESSED_DIR

SYLLABUS_PATH = PROCESSED_DIR / "syllabus.json"


def load_items() -> list[dict]:
    """All syllabus items, each with its paper part and section title attached."""
    syllabus = json.loads(SYLLABUS_PATH.read_text(encoding="utf-8"))
    items = []
    for part, paper in syllabus["papers"].items():
        for section in paper["sections"]:
            for item in section["items"]:
                items.append({**item, "part": part, "section_id": section["id"], "section_title": section["title"]})
    return items


def item_text(item: dict) -> str:
    """Description of a syllabus item used for embedding."""
    return f"{item['section_title']}: {item['label']}. {item['official_text']}."


def question_text(record: dict) -> str:
    """Stem plus options on one line, with script markup removed."""
    parts = [record["stem"]]
    for letter, option in (record["options"] or {}).items():
        parts.append(f"({letter}) {option}")
    text = " ".join(parts)
    text = re.sub(r"[\^_]\{([^{}]*)\}", r" \1 ", text)  # x^{2} -> x 2 : embeddings ignore layout
    return re.sub(r"\s+", " ", text).strip()
