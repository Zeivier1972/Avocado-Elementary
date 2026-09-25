"""District Topic Assessment Administration Schedule (2026-2027), loaded from
data/topic_assessment_schedule.json. Lets the calendar/pacing anchor each Topic
Assessment to its real 'administer-by' date."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name("data") / "topic_assessment_schedule.json"
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}


def _roman_to_int(s: str) -> int:
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = _ROMAN.get(ch, 0)
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def topic_key(code: str) -> str:
    """Normalise a topic label to a comparable key: 'TOPIC 1'->'1',
    'Topic 2/3'->'2/3', 'TOPIC IX'->'9'."""
    c = re.sub(r"(topic|chapter)", "", (code or ""), flags=re.I).strip().upper()
    if re.fullmatch(r"[IVXL]+", c):
        return str(_roman_to_int(c))
    m = re.match(r"(\d+(?:\s*/\s*\d+)?)", c)
    return m.group(1).replace(" ", "") if m else c


@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        return json.loads(_PATH.read_text())
    except Exception:
        return {"by_grade": {}}


def schedule_for_grade(grade: str) -> list[dict]:
    """All scheduled topics for a grade, each with available / recommended /
    administer_by ISO dates."""
    return _data().get("by_grade", {}).get(str(grade), [])


def lookup(grade: str, topic_code: str) -> dict | None:
    """Assessment dates for a specific topic in a grade (fuzzy-matched by number),
    or None if the schedule has no matching topic."""
    key = topic_key(topic_code)
    for row in schedule_for_grade(grade):
        if topic_key(row.get("topic", "")) == key:
            return row
    return None
