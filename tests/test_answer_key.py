"""Tests for answer-key parsing."""

from gate_atlas.answer_key import parse_key_text

SAMPLE_KEY = """
Q. No. Session Question Type Section Key/Range Mark
1 1 MCQ GA D 1
28 1 MSQ DA A;B;C 1
29
1
MSQ
DA
B; D
2
58 8 NAT DA 8  to 8 2
59 1 NAT DA MTA 2
60 1 NAT DA -0.5 to -0.25 2
Page 1 of 2
"""


def test_rows_are_parsed_across_line_breaks_and_spacing() -> None:
    """Rows split over lines and with odd spacing are still read."""
    entries = {entry.number: entry for entry in parse_key_text(SAMPLE_KEY)}
    assert sorted(entries) == [1, 28, 29, 58, 59, 60]
    assert entries[1].qtype == "MCQ" and entries[1].section == "GA" and entries[1].marks == 1
    assert entries[29].options == ["B", "D"]
    assert entries[58].numeric_range == (8.0, 8.0)


def test_answer_shapes() -> None:
    """Answers serialize to the dataset's three shapes."""
    entries = {entry.number: entry for entry in parse_key_text(SAMPLE_KEY)}
    assert entries[28].as_answer() == {"kind": "options", "options": ["A", "B", "C"]}
    assert entries[59].as_answer() == {"kind": "mta"}
    assert entries[60].as_answer() == {"kind": "range", "low": -0.5, "high": -0.25}
